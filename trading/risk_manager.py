"""
trading/risk_manager.py — FRIDAY's hard risk rules.
These rules are enforced BEFORE any trade is sent to the executor.
"""

from config import (
    CAPITAL_PER_TRADE, MAX_RISK_PERCENT,
    STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT
)


# Minimum AI confidence required to place a trade (%)
MIN_CONFIDENCE_THRESHOLD = 65

# Maximum number of open positions at once
MAX_OPEN_POSITIONS = 5


def approve_trade(analysis: dict, market_data: dict, open_positions: list) -> tuple[bool, str]:
    """
    Runs all risk checks on a proposed trade.
    Returns (approved: bool, reason: str).
    """
    action = analysis.get("action", "HOLD")

    # Only evaluate BUY signals (we support long-only for now)
    if action != "BUY":
        return False, f"Action is {action}, not BUY."

    # Confidence gate
    confidence = analysis.get("confidence", 0)
    if confidence < MIN_CONFIDENCE_THRESHOLD:
        return False, f"Confidence {confidence}% is below threshold ({MIN_CONFIDENCE_THRESHOLD}%)."

    # Too many open positions
    ticker = market_data.get("ticker", "")
    if len(open_positions) >= MAX_OPEN_POSITIONS:
        return False, f"Max open positions ({MAX_OPEN_POSITIONS}) reached."

    # Don't re-enter an already open position
    open_tickers = [p["ticker"] for p in open_positions]
    if ticker in open_tickers:
        return False, f"Already have an open position in {ticker}."

    # High risk analysis — skip
    if analysis.get("risk_level") == "HIGH":
        return False, "Risk level flagged as HIGH by AI. Skipping."

    # Price must be available
    price = market_data.get("price")
    if not price or price <= 0:
        return False, "Invalid price data."

    return True, "All risk checks passed."


def calculate_position(price: float, analysis: dict) -> dict:
    """
    Calculates position size, stop-loss price, and take-profit price.
    Returns a dict with execution parameters.
    """
    # Use AI suggested levels if provided, else use config defaults
    stop_pct   = STOP_LOSS_PERCENT / 100
    target_pct = TAKE_PROFIT_PERCENT / 100

    stop_loss    = analysis.get("suggested_stop_loss")  or round(price * (1 - stop_pct), 4)
    take_profit  = analysis.get("suggested_take_profit") or round(price * (1 + target_pct), 4)

    # Risk per share
    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        risk_per_share = price * stop_pct

    # Position size based on capital at risk
    max_dollar_risk = CAPITAL_PER_TRADE * (MAX_RISK_PERCENT / 100)
    shares = int(max_dollar_risk / risk_per_share)
    shares = max(1, shares)  # at least 1 share

    total_cost     = round(shares * price, 2)
    risk_reward    = round((take_profit - price) / (price - stop_loss), 2) if (price - stop_loss) > 0 else 0

    return {
        "shares": shares,
        "entry_price": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "total_cost": total_cost,
        "risk_per_share": round(risk_per_share, 4),
        "max_dollar_risk": round(max_dollar_risk, 2),
        "risk_reward_ratio": risk_reward,
    }
