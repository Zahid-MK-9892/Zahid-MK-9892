"""
trading/position_manager.py — Automatic position exit manager.
Runs on every scan cycle and closes positions that hit SL or TP.
"""

from datetime import datetime
from trading.journal import get_open_positions, close_position
from data.market_data import get_stock_data, get_crypto_data


def check_and_close_positions() -> list:
    """
    Called every scan cycle.
    Checks every open position against current price.
    Closes automatically if stop-loss or take-profit is hit.
    Returns list of closed position summaries.
    """
    open_positions = get_open_positions()
    closed = []

    for pos in open_positions:
        ticker     = pos.get("ticker", "")
        entry      = float(pos.get("entry_price") or 0)
        stop_loss  = float(pos.get("stop_loss") or 0)
        take_profit= float(pos.get("take_profit") or 0)
        shares     = float(pos.get("shares") or 0)
        trade_id   = pos.get("id")

        if not ticker or not entry or not stop_loss or not take_profit:
            continue

        # Fetch current price
        current = _get_current_price(ticker)
        if not current or current <= 0:
            continue

        exit_reason = None

        # Check stop-loss
        if current <= stop_loss:
            exit_reason = "STOP_LOSS"

        # Check take-profit
        elif current >= take_profit:
            exit_reason = "TAKE_PROFIT"

        if exit_reason:
            result = close_position(trade_id, current)
            pnl    = result.get("pnl", 0) if result else 0
            outcome= result.get("outcome", "?") if result else "?"

            summary = {
                "ticker":      ticker,
                "exit_reason": exit_reason,
                "entry":       entry,
                "exit":        current,
                "pnl":         pnl,
                "outcome":     outcome,
                "shares":      shares,
                "timestamp":   datetime.now().isoformat(),
            }
            closed.append(summary)

            # Also close on broker if Alpaca
            _close_on_broker(pos, current)

    return closed


def _get_current_price(ticker: str) -> float:
    """Fetch latest price for any ticker."""
    try:
        is_crypto = "/" in ticker or ticker.endswith("-USD")
        if is_crypto:
            data = get_crypto_data(ticker)
        else:
            data = get_stock_data(ticker, period="5d", interval="1d")

        if "error" not in data and data.get("price"):
            return float(data["price"])
    except Exception:
        pass
    return 0.0


def _close_on_broker(pos: dict, exit_price: float):
    """
    Attempt to close the position on the actual broker (Alpaca).
    Silently ignores errors — journal is the source of truth.
    """
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
