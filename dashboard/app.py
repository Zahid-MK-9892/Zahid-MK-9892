"""
dashboard/app.py — FRIDAY Web Dashboard Backend v2
Run: python dashboard/app.py
Open: http://localhost:5000

FIXED: Added /api/trades/all route (HTML was calling this, not /api/all-trades)
FIXED: fast_info price fetch uses getattr() not .get()
FIXED: squeeze() scalar handled before .iloc call
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
    log_scan, log_trade, close_position,
    get_closed_trades, get_all_trades, get_recent_scans
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
        import pandas as pd
        yf_sym = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        tk = yf.Ticker(yf_sym)

        # fast_info is an OBJECT, not a dict — use getattr()
        try:
            fi = tk.fast_info
            for attr in ("last_price", "lastPrice", "regularMarketPrice"):
                val = getattr(fi, attr, None)
                if val is not None:
                    price = float(val)
                    if price > 0:
                        _price_cache[ticker] = price
                        _price_ts[ticker]    = now
                        return price
        except Exception:
            pass

        # Fallback: history — handle scalar squeeze result
        hist = tk.history(period="3d", auto_adjust=True)
        if hist is not None and not hist.empty:
            close_data = hist["Close"].squeeze()
            price = float(close_data.iloc[-1]) if hasattr(close_data, 'iloc') else float(close_data)
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


# ── Trade History routes ───────────────────────────────────────────────────────
@app.route("/api/trade-history")
def trade_history():
    return jsonify(get_closed_trades(limit=100))


@app.route("/api/all-trades")
def all_trades_old():
    return jsonify(get_all_trades(limit=100))


# ── /api/trades/all — what the HTML loadHistory() actually calls ───────────────
@app.route("/api/trades/all")
def trades_all():
    try:
        trades = get_all_trades(limit=200)
        return jsonify(trades)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify([])


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
            p["current_price"]      = current
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
        period = request.args.get("period", "3mo")
        yf_sym = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        df     = yf.download(yf_sym, period=period, interval="1d",
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

    api_key = getattr(cfg, "ANTHROPIC_API_KEY", "")
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
    except Exception:
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

# ── Telegram ───────────────────────────────────────────────────────────────────
@app.route("/api/telegram/test", methods=["POST"])
def telegram_test():
    from notifications.telegram import send_custom_message
    result = send_custom_message(
        "🤖 FRIDAY test message — Telegram alerts are working!"
    )
    return jsonify(result)


@app.route("/api/telegram/config", methods=["GET"])
def telegram_config():
    import os
    token   = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    placeholders = {"your_telegram_bot_token_here", "your_chat_id_here", ""}
    configured = bool(token) and token not in placeholders and \
                 bool(chat_id) and chat_id not in placeholders
    return jsonify({
        "configured": configured,
        "chat_id":    chat_id if configured else "",
    })


# ── Analytics ──────────────────────────────────────────────────────────────────
@app.route("/api/analytics")
def analytics():
    """
    Computes advanced performance metrics from the journal DB.
    No schema changes — reads existing trades table only.

    Returns:
      sharpe_ratio       — annualised risk-adjusted return (needs 10+ trades)
      max_drawdown_pct   — largest peak-to-trough % decline in equity curve
      profit_factor      — total wins / abs(total losses). >1.5 = good
      avg_holding_days   — average days a position was held
      win_rate_stocks    — win rate for STOCK asset_type only
      win_rate_crypto    — win rate for CRYPTO asset_type only
      best_ticker        — ticker with highest cumulative P&L
      worst_ticker       — ticker with lowest cumulative P&L
      monthly_pnl        — list of {month, pnl} for bar chart
      total_trades       — total closed trades (for context)
    """
    import sqlite3
    import math
    from pathlib import Path

    db_path = Path(__file__).parent.parent / "friday_journal.db"

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT ticker, asset_type, pnl, outcome,
                   opened_at, closed_at
            FROM trades
            WHERE closed_at IS NOT NULL
            ORDER BY closed_at ASC
        """).fetchall()
        conn.close()
    except Exception as e:
        return jsonify({"error": str(e)})

    if not rows:
        return jsonify({
            "sharpe_ratio":     None,
            "max_drawdown_pct": 0,
            "profit_factor":    None,
            "avg_holding_days": 0,
            "win_rate_stocks":  0,
            "win_rate_crypto":  0,
            "best_ticker":      {"ticker": "—", "pnl": 0},
            "worst_ticker":     {"ticker": "—", "pnl": 0},
            "monthly_pnl":      [],
            "total_trades":     0,
        })

    trades = [dict(r) for r in rows]

    # ── Profit Factor ─────────────────────────────────────────────────────────
    total_wins   = sum(t["pnl"] for t in trades if (t["pnl"] or 0) > 0)
    total_losses = sum(t["pnl"] for t in trades if (t["pnl"] or 0) < 0)
    profit_factor = (
        round(total_wins / abs(total_losses), 2)
        if total_losses != 0 else None
    )

    # ── Max Drawdown ──────────────────────────────────────────────────────────
    equity   = 0.0
    peak     = 0.0
    max_dd   = 0.0
    for t in trades:
        equity += (t["pnl"] or 0)
        if equity > peak:
            peak = equity
        if peak > 0:
            dd = (peak - equity) / peak * 100
            if dd > max_dd:
                max_dd = dd
    max_drawdown_pct = round(max_dd, 2)

    # ── Sharpe Ratio ──────────────────────────────────────────────────────────
    # Computed from daily P&L series. Needs 10+ trades for meaning.
    sharpe_ratio = None
    pnl_series   = [t["pnl"] or 0 for t in trades]
    if len(pnl_series) >= 10:
        avg_r  = sum(pnl_series) / len(pnl_series)
        var    = sum((x - avg_r) ** 2 for x in pnl_series) / len(pnl_series)
        std_r  = math.sqrt(var)
        if std_r > 0:
            sharpe_ratio = round((avg_r / std_r) * math.sqrt(252), 2)

    # ── Average Holding Days ──────────────────────────────────────────────────
    holding_days = []
    for t in trades:
        try:
            from datetime import datetime as dt
            opened = dt.fromisoformat(t["opened_at"])
            closed = dt.fromisoformat(t["closed_at"])
            days   = (closed - opened).days
            holding_days.append(days)
        except Exception:
            continue
    avg_holding_days = (
        round(sum(holding_days) / len(holding_days), 1)
        if holding_days else 0
    )

    # ── Win Rate by Asset Type ────────────────────────────────────────────────
    def _wr(asset_type):
        subset = [t for t in trades if (t["asset_type"] or "STOCK") == asset_type]
        if not subset:
            return 0
        wins = sum(1 for t in subset if t["outcome"] == "WIN")
        return round(wins / len(subset) * 100, 1)

    win_rate_stocks = _wr("STOCK")
    win_rate_crypto = _wr("CRYPTO")

    # ── Best / Worst Ticker ───────────────────────────────────────────────────
    ticker_pnl = {}
    for t in trades:
        tk = t["ticker"]
        ticker_pnl[tk] = ticker_pnl.get(tk, 0) + (t["pnl"] or 0)

    if ticker_pnl:
        best_tk  = max(ticker_pnl, key=ticker_pnl.get)
        worst_tk = min(ticker_pnl, key=ticker_pnl.get)
        best_ticker  = {"ticker": best_tk,  "pnl": round(ticker_pnl[best_tk],  2)}
        worst_ticker = {"ticker": worst_tk, "pnl": round(ticker_pnl[worst_tk], 2)}
    else:
        best_ticker  = {"ticker": "—", "pnl": 0}
        worst_ticker = {"ticker": "—", "pnl": 0}

    # ── Monthly P&L ───────────────────────────────────────────────────────────
    monthly = {}
    for t in trades:
        try:
            month = t["closed_at"][:7]   # "YYYY-MM"
            monthly[month] = monthly.get(month, 0) + (t["pnl"] or 0)
        except Exception:
            continue
    monthly_pnl = [
        {"month": m, "pnl": round(v, 2)}
        for m, v in sorted(monthly.items())
    ]

    return jsonify({
        "sharpe_ratio":     sharpe_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "profit_factor":    profit_factor,
        "avg_holding_days": avg_holding_days,
        "win_rate_stocks":  win_rate_stocks,
        "win_rate_crypto":  win_rate_crypto,
        "best_ticker":      best_ticker,
        "worst_ticker":     worst_ticker,
        "monthly_pnl":      monthly_pnl,
        "total_trades":     len(trades),
    })

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
            from main import run_scan_cycle
            _log("Starting full market scan...")
            run_scan_cycle()
            _log("Scan complete.", "INFO")
        except Exception as e:
            _log(f"Scan error: {e}", "ERROR")
        finally:
            is_running = False

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"message": "Scan started"})


# ── Scans history ──────────────────────────────────────────────────────────────
@app.route("/api/scans/recent")
def recent_scans():
    try:
        scans = get_recent_scans(limit=50)
        return jsonify(scans)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify([])


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
    """
    Returns combined logs: file logs from main.py --loop + in-memory dashboard logs.
    main.py writes to friday.log in the project root.
    """
    combined = []

    # ── Read from friday.log (written by main.py --loop) ──────────────────────
    try:
        log_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "friday.log"
        )
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            for line in lines[-300:]:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                # Parse lines like: [10:12:34] [INFO] message
                import re
                m = re.match(r"\[(\d{2}:\d{2}:\d{2})\]\s*\[(\w+)\]\s*(.*)", line)
                if m:
                    combined.append({"time": m.group(1), "level": m.group(2), "msg": m.group(3), "source": "bot"})
                else:
                    combined.append({"time": "", "level": "INFO", "msg": line, "source": "bot"})
    except Exception as e:
        combined.append({"time": "", "level": "ERROR", "msg": f"Could not read friday.log: {e}", "source": "bot"})

    # ── Append in-memory logs from dashboard-triggered scans ──────────────────
    for entry in scan_log:
        combined.append({**entry, "source": "dashboard"})

    # Sort by time string (both use HH:MM:SS format so string sort works)
    combined.sort(key=lambda x: x.get("time", ""))

    return jsonify(combined[-300:])


if __name__ == "__main__":
    init_db()
    print("\n🤖 FRIDAY Dashboard v2 → http://localhost:5000\n")
    app.run(debug=False, port=5000, threaded=True)
