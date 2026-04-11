"""
dashboard/app.py — FRIDAY Web Dashboard Backend v2
Run: python dashboard/app.py
Open: http://localhost:5000
"""

import sys, os, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import config as cfg
from trading.journal import (
    init_db, get_open_positions, get_performance_summary,
    log_scan, log_trade, close_position
)

app = Flask(__name__, static_folder="static")
CORS(app)

scan_log   = []
is_running = False
_price_cache = {}
_price_ts    = {}
CACHE_TTL    = 30  # seconds


# ── Helpers ────────────────────────────────────────────────────────────────────
def _log(msg, level="INFO"):
    scan_log.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level})
    if len(scan_log) > 200:
        scan_log.pop(0)


def _current_price(ticker: str) -> float:
    now = time.time()
    if ticker in _price_cache and (now - _price_ts.get(ticker, 0)) < CACHE_TTL:
        return _price_cache[ticker]
    try:
        import yfinance as yf
        yf_sym = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        data = yf.download(yf_sym, period="2d", interval="1d", progress=False, auto_adjust=True)
        if not data.empty:
            if isinstance(data.columns, __import__("pandas").MultiIndex):
                data.columns = data.columns.get_level_values(0)
            price = float(data["Close"].squeeze().iloc[-1])
            _price_cache[ticker] = price
            _price_ts[ticker]    = now
            return price
    except Exception:
        pass
    return _price_cache.get(ticker, 0)


# ── Static ─────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Status ─────────────────────────────────────────────────────────────────────
@app.route("/api/status")
def status():
    return jsonify({
        "running": is_running,
        "mock_mode": cfg.MOCK_MODE,
        "scan_interval": cfg.SCAN_INTERVAL_MINUTES,
        "capital_per_trade": cfg.CAPITAL_PER_TRADE,
        "max_risk_pct": cfg.MAX_RISK_PERCENT,
        "stop_loss_pct": cfg.STOP_LOSS_PERCENT,
        "take_profit_pct": cfg.TAKE_PROFIT_PERCENT,
        "stock_watchlist": cfg.STOCK_WATCHLIST,
        "crypto_watchlist": cfg.CRYPTO_WATCHLIST,
        "timestamp": datetime.now().isoformat(),
    })


# ── Performance ────────────────────────────────────────────────────────────────
@app.route("/api/performance")
def performance():
    return jsonify(get_performance_summary())


# ── Positions with live P&L ────────────────────────────────────────────────────
@app.route("/api/positions")
def positions():
    pos = get_open_positions()
    for p in pos:
        current = _current_price(p["ticker"])
        entry   = float(p.get("entry_price") or 0)
        shares  = float(p.get("shares") or 0)
        if current and entry and shares:
            pnl     = round((current - entry) * shares, 2)
            pnl_pct = round(((current - entry) / entry) * 100, 2) if entry else 0
            p["current_price"] = current
            p["unrealized_pnl"]     = pnl
            p["unrealized_pnl_pct"] = pnl_pct
        else:
            p["current_price"]      = entry
            p["unrealized_pnl"]     = 0
            p["unrealized_pnl_pct"] = 0
    return jsonify(pos)


# ── Close position ─────────────────────────────────────────────────────────────
@app.route("/api/close-position/<int:trade_id>", methods=["POST"])
def close_pos(trade_id):
    pos = get_open_positions()
    trade = next((p for p in pos if p["id"] == trade_id), None)
    if not trade:
        return jsonify({"error": "Position not found"}), 404

    current = _current_price(trade["ticker"])
    if not current:
        return jsonify({"error": "Could not fetch current price"}), 400

    # Try to close on Alpaca if keys set
    if not cfg.MOCK_MODE and trade.get("asset_type") == "STOCK":
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import ClosePositionRequest
            client = TradingClient(cfg.ALPACA_API_KEY if hasattr(cfg, "ALPACA_API_KEY") else "",
                                   cfg.ALPACA_SECRET_KEY if hasattr(cfg, "ALPACA_SECRET_KEY") else "",
                                   paper=True)
            client.close_position(trade["ticker"])
        except Exception as e:
            _log(f"Alpaca close error: {e} — closing in journal only", "WARN")

    result = close_position(trade_id, current)
    _log(f"Closed {trade['ticker']} @ ${current} | P&L: ${result.get('pnl', 0)}", "INFO")
    return jsonify({"message": f"Position closed", "exit_price": current, **result})


# ── Chart data ─────────────────────────────────────────────────────────────────
@app.route("/api/chart/<path:ticker>")
def chart_data(ticker):
    try:
        import yfinance as yf
        import pandas as pd
        period   = request.args.get("period", "3mo")
        yf_sym   = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        df       = yf.download(yf_sym, period=period, interval="1d",
                               progress=False, auto_adjust=True)
        if df.empty:
            return jsonify({"error": "No data"}), 404
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.dropna(inplace=True)

        import ta
        close = df["Close"].squeeze()
        df["rsi"]    = ta.momentum.RSIIndicator(close).rsi()
        df["sma_20"] = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        df["sma_50"] = ta.trend.SMAIndicator(close, window=50).sma_indicator()

        candles = []
        for idx, row in df.iterrows():
            candles.append({
                "time":   str(idx)[:10],
                "open":   round(float(row["Open"]), 4),
                "high":   round(float(row["High"]), 4),
                "low":    round(float(row["Low"]),  4),
                "close":  round(float(row["Close"]), 4),
                "volume": int(float(row["Volume"])),
                "rsi":    round(float(row["rsi"]),    2) if row["rsi"]==row["rsi"] else None,
                "sma20":  round(float(row["sma_20"]), 4) if row["sma_20"]==row["sma_20"] else None,
                "sma50":  round(float(row["sma_50"]), 4) if row["sma_50"]==row["sma_50"] else None,
            })
        return jsonify({"ticker": ticker, "candles": candles})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Backtest ───────────────────────────────────────────────────────────────────
@app.route("/api/backtest", methods=["POST"])
def backtest():
    data     = request.json or {}
    ticker   = data.get("ticker", "AAPL")
    period   = data.get("period", "1y")
    stop_pct = float(data.get("stop_pct", cfg.STOP_LOSS_PERCENT))
    tgt_pct  = float(data.get("target_pct", cfg.TAKE_PROFIT_PERCENT))
    capital  = float(data.get("capital", cfg.CAPITAL_PER_TRADE))

    from analysis.backtester import run_backtest
    result = run_backtest(ticker, period, stop_pct, tgt_pct, capital)
    return jsonify(result)


# ── FRIDAY Chat ────────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
def chat():
    data     = request.json or {}
    message  = data.get("message", "")
    history  = data.get("history", [])

    positions = get_open_positions()
    pos_text  = "\n".join(
        f"- {p['ticker']}: entry ${p['entry_price']}, SL ${p['stop_loss']}, TP ${p['take_profit']}"
        for p in positions
    ) or "No open positions."

    system = f"""You are FRIDAY, an expert AI swing trading assistant.
Current date: {datetime.now().strftime('%Y-%m-%d')}
Watchlist stocks: {cfg.STOCK_WATCHLIST}
Watchlist crypto: {cfg.CRYPTO_WATCHLIST}
Capital per trade: ${cfg.CAPITAL_PER_TRADE}
Stop loss: {cfg.STOP_LOSS_PERCENT}% | Take profit: {cfg.TAKE_PROFIT_PERCENT}%

Open positions:
{pos_text}

Answer trading questions concisely and helpfully. Be direct. Use data when possible."""

    api_key = cfg.ANTHROPIC_API_KEY if hasattr(cfg, "ANTHROPIC_API_KEY") else ""
    if not api_key or api_key == "your_anthropic_key_here":
        return jsonify({"reply": _rule_chat(message, positions)})

    try:
        import anthropic
        client   = anthropic.Anthropic(api_key=api_key)
        messages = history[-10:] + [{"role": "user", "content": message}]
        resp     = client.messages.create(
            model=cfg.AI_MODEL, max_tokens=600,
            system=system, messages=messages,
        )
        return jsonify({"reply": resp.content[0].text})
    except Exception as e:
        return jsonify({"reply": _rule_chat(message, positions)})


def _rule_chat(msg: str, positions: list) -> str:
    msg_l = msg.lower()
    if any(w in msg_l for w in ["position", "open", "holding", "trade"]):
        if not positions:
            return "You currently have no open positions."
        lines = [f"**{p['ticker']}** — Entry: ${p['entry_price']} | SL: ${p['stop_loss']} | TP: ${p['take_profit']}" for p in positions]
        return "Your open positions:\n" + "\n".join(lines)
    if any(w in msg_l for w in ["scan", "analyse", "analyze", "buy", "sell"]):
        return "Run a scan from the Scan & Trade page to get my latest analysis on all watchlisted assets."
    if any(w in msg_l for w in ["risk", "stop", "loss"]):
        return f"Your current stop-loss is set to {cfg.STOP_LOSS_PERCENT}% and take-profit to {cfg.TAKE_PROFIT_PERCENT}%. You can adjust these in Settings."
    if any(w in msg_l for w in ["hello", "hi", "hey"]):
        return f"Hey! I'm FRIDAY, your AI trading assistant. I'm watching {len(cfg.STOCK_WATCHLIST)} stocks and {len(cfg.CRYPTO_WATCHLIST)} crypto pairs. How can I help?"
    return "I'm running in rule-based mode (no Anthropic credits). Add credits at console.anthropic.com to enable full AI chat. I can still help with positions, settings, and scan results!"


# ── WhatsApp ───────────────────────────────────────────────────────────────────
@app.route("/api/whatsapp/test", methods=["POST"])
def whatsapp_test():
    from notifications.whatsapp import send_custom_message
    result = send_custom_message("🤖 FRIDAY test message — WhatsApp alerts are working!")
    return jsonify(result)


@app.route("/api/whatsapp/config", methods=["GET"])
def whatsapp_config():
    import os
    return jsonify({
        "configured": bool(os.getenv("TWILIO_ACCOUNT_SID") and os.getenv("WHATSAPP_TO")),
        "to": os.getenv("WHATSAPP_TO", ""),
    })


# ── Scan trigger ───────────────────────────────────────────────────────────────
@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    global is_running
    if is_running:
        return jsonify({"error": "Scan already running"}), 400

    def run():
        global is_running
        is_running = True
        try:
            from main import scan_asset
            for t in cfg.STOCK_WATCHLIST:
                _log(f"Scanning {t}...")
                try: scan_asset(t)
                except Exception as e: _log(f"Error: {t}: {e}", "ERROR")
            for t in cfg.CRYPTO_WATCHLIST:
                _log(f"Scanning {t}...")
                try: scan_asset(t)
                except Exception as e: _log(f"Error: {t}: {e}", "ERROR")
            _log("Scan complete.", "INFO")
        except Exception as e:
            _log(f"Scan error: {e}", "ERROR")
        finally:
            is_running = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"message": "Scan started"})


# ── Settings ───────────────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}
    if "capital_per_trade"  in data: cfg.CAPITAL_PER_TRADE    = float(data["capital_per_trade"])
    if "max_risk_pct"       in data: cfg.MAX_RISK_PERCENT      = float(data["max_risk_pct"])
    if "stop_loss_pct"      in data: cfg.STOP_LOSS_PERCENT     = float(data["stop_loss_pct"])
    if "take_profit_pct"    in data: cfg.TAKE_PROFIT_PERCENT   = float(data["take_profit_pct"])
    if "scan_interval"      in data: cfg.SCAN_INTERVAL_MINUTES = int(data["scan_interval"])
    if "mock_mode"          in data: cfg.MOCK_MODE             = bool(data["mock_mode"])
    if "stock_watchlist"    in data: cfg.STOCK_WATCHLIST       = [t.strip().upper() for t in data["stock_watchlist"] if t.strip()]
    if "crypto_watchlist"   in data: cfg.CRYPTO_WATCHLIST      = [t.strip().upper() for t in data["crypto_watchlist"] if t.strip()]
    _log(f"Settings updated: {list(data.keys())}")
    return jsonify({"message": "Settings saved"})


# ── Logs ───────────────────────────────────────────────────────────────────────
@app.route("/api/logs")
def logs():
    return jsonify(scan_log[-150:])


if __name__ == "__main__":
    init_db()
    print("\n🤖 FRIDAY Dashboard v2 → http://localhost:5000\n")
    app.run(debug=False, port=5000, threaded=True)
