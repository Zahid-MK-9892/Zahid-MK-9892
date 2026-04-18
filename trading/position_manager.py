"""
trading/position_manager.py — Automatic position exit manager.
Uses real-time quotes (not daily candles) to check stop-loss / take-profit.
"""

from datetime import datetime
from trading.journal import get_open_positions, close_position


def _get_realtime_price(ticker: str) -> float:
    """
    Fetches the latest real-time price using yfinance fast_info.
    Falls back to daily data if fast_info fails.
    """
    try:
        import yfinance as yf
        # Handle crypto ticker format
        yf_sym = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        t = yf.Ticker(yf_sym)

        # Try fast_info first (real-time, no rate limit issues)
        try:
            price = t.fast_info.get("last_price") or t.fast_info.get("regularMarketPrice")
            if price and float(price) > 0:
                return float(round(price, 4))
        except Exception:
            pass

        # Fallback: latest daily close
        import pandas as pd
        df = t.history(period="2d", interval="1d")
        if df is None or df.empty:
            return 0.0
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return float(df["Close"].squeeze().iloc[-1])

    except Exception as e:
        print(f"[EXIT] Price fetch failed for {ticker}: {e}")
        return 0.0


def check_and_close_positions() -> list:
    """
    Called every scan cycle.
    Checks every open position against real-time price.
    Closes automatically if stop-loss or take-profit is hit.
    """
    open_positions = get_open_positions()
    closed = []

    for pos in open_positions:
        ticker      = pos.get("ticker", "")
        entry       = float(pos.get("entry_price") or 0)
        stop_loss   = float(pos.get("stop_loss") or 0)
        take_profit = float(pos.get("take_profit") or 0)
        shares      = float(pos.get("shares") or 0)
        trade_id    = pos.get("id")

        if not ticker or not entry or not stop_loss or not take_profit:
            continue

        current = _get_realtime_price(ticker)
        if not current or current <= 0:
            print(f"[EXIT] Could not get price for {ticker}, skipping")
            continue

        print(f"[EXIT] {ticker} | Entry: ${entry} | Current: ${current} | "
              f"SL: ${stop_loss} | TP: ${take_profit}")

        exit_reason = None
        if current <= stop_loss:
            exit_reason = "STOP_LOSS"
        elif current >= take_profit:
            exit_reason = "TAKE_PROFIT"

        if exit_reason:
            result = close_position(trade_id, current)
            pnl    = result.get("pnl", 0) if result else 0
            outcome= result.get("outcome", "?") if result else "?"

            closed.append({
                "ticker":      ticker,
                "exit_reason": exit_reason,
                "entry":       entry,
                "exit":        current,
                "pnl":         pnl,
                "outcome":     outcome,
                "shares":      shares,
                "timestamp":   datetime.now().isoformat(),
            })

            _close_on_broker(pos, current)

    return closed


def _close_on_broker(pos: dict, exit_price: float):
    """Attempt to close on Alpaca. Silently ignores errors."""
    try:
        import config as cfg
        if cfg.MOCK_MODE:
            return
        if pos.get("asset_type") == "STOCK":
            from alpaca.trading.client import TradingClient
            client = TradingClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY, paper=True)
            client.close_position(pos["ticker"])
    except Exception:
        pass
