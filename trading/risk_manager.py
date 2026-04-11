"""
trading/risk_manager.py — FRIDAY's hard risk rules.
Enforced BEFORE any trade reaches the executor.
"""

from config import (
    CAPITAL_PER_TRADE, MAX_RISK_PERCENT,
    STOP_LOSS_PERCENT, TAKE_PROFIT_PERCENT
)

MIN_CONFIDENCE_THRESHOLD = 62   # Minimum AI/rule confidence to trade
MAX_OPEN_POSITIONS       = 5    # Max concurrent open trades


def approve_trade(analysis: dict, market_data: dict, open_positions: list) -> tuple:
    """
    Runs all risk checks. Returns (approved: bool, reason: str).
    """
    action = analysis.get("action", "HOLD")

    if action != "BUY":
        return False, f"Action is {action} — only BUY signals are traded."

    confidence = analysis.get("confidence", 0)
    if confidence < MIN_CONFIDENCE_THRESHOLD:
        return False, f"Confidence {confidence}% is below minimum ({MIN_CONFIDENCE_THRESHOLD}%)."

    if analysis.get("risk_level") == "HIGH":
        return False, "Risk level flagged as HIGH — skipping."

    ticker = market_data.get("ticker", "")
    if len(open_positions) >= MAX_OPEN_POSITIONS:
        return False, f"Max open positions ({MAX_OPEN_POSITIONS}) reached."

    open_tickers = [p.get("ticker", "") for p in open_positions]
    if ticker in open_tickers:
        return False, f"Already have an open position in {ticker}."

    price = market_data.get("price")
    if not price or float(price) <= 0:
        return False, "Invalid or missing price data."

    # Block if source is error
    if analysis.get("source") == "error":
        return False, "Analysis failed — not trading."

    return True, "All risk checks passed."


def calculate_position(price: float, analysis: dict) -> dict:
    """
    Calculates shares, stop-loss, take-profit, and total cost.
    """
    price = float(price)

    stop_loss   = analysis.get("suggested_stop_loss")   or round(price * (1 - STOP_LOSS_PERCENT / 100), 4)
    take_profit = analysis.get("suggested_take_profit") or round(price * (1 + TAKE_PROFIT_PERCENT / 100), 4)

    stop_loss   = float(stop_loss)
    take_profit = float(take_profit)

    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        risk_per_share = price * (STOP_LOSS_PERCENT / 100)

    max_dollar_risk = float(CAPITAL_PER_TRADE) * (float(MAX_RISK_PERCENT) / 100)
    shares = max(1, int(max_dollar_risk / risk_per_share))

    total_cost  = round(shares * price, 2)
    rr_ratio    = round((take_profit - price) / (price - stop_loss), 2) if (price - stop_loss) > 0 else 0

    return {
        "shares":            shares,
        "entry_price":       round(price, 4),
        "stop_loss":         round(stop_loss, 4),
        "take_profit":       round(take_profit, 4),
        "total_cost":        total_cost,
        "risk_per_share":    round(risk_per_share, 4),
        "max_dollar_risk":   round(max_dollar_risk, 2),
        "risk_reward_ratio": rr_ratio,
    }
