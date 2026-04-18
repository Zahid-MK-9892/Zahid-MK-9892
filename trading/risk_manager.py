"""
trading/risk_manager.py — Dynamic risk manager with conviction-based sizing.
Position size scales with analysis score — higher conviction = larger position.
"""

import config


MIN_CONFIDENCE   = 62    # Minimum confidence % to trade
MAX_POSITIONS    = 14     # Max concurrent open positions


def approve_trade(analysis: dict, market_data: dict,
                  open_positions: list) -> tuple:
    """All risk checks. Returns (approved: bool, reason: str)."""

    if analysis.get("action") != "BUY":
        return False, f"Action is {analysis.get('action')} — only BUY signals traded."

    confidence = analysis.get("confidence", 0)
    if confidence < MIN_CONFIDENCE:
        return False, f"Confidence {confidence}% below minimum ({MIN_CONFIDENCE}%)."

    if analysis.get("risk_level") == "HIGH":
        return False, "Risk level HIGH — skipping."

    if analysis.get("source") == "error":
        return False, "Analysis errored — not trading."

    ticker = market_data.get("ticker", "")
    if len(open_positions) >= MAX_POSITIONS:
        return False, f"Max positions ({MAX_POSITIONS}) reached."

    open_tickers = {p.get("ticker", "") for p in open_positions}
    if ticker in open_tickers:
        return False, f"Already in {ticker}."

    price = market_data.get("price")
    if not price or float(price) <= 0:
        return False, "Invalid price."

    # Block penny stocks
    if float(price) < 5:
        return False, f"Price ${price} too low — avoiding penny stocks."

    return True, "All checks passed."


def calculate_position(price: float, analysis: dict,
                       total_capital: float = None) -> dict:
    """
    Dynamic position sizing based on conviction score.
    
    Score 7-8 (very high) → risk 3% of capital per trade
    Score 5-6 (high)      → risk 2% of capital per trade  
    Score 3-4 (moderate)  → risk 1.5% of capital per trade
    Score 1-2 (low)       → risk 1% of capital per trade
    """
    price = float(price)
    score = analysis.get("score", 2)

    # Capital base
    cap = float(total_capital or config.CAPITAL_PER_TRADE)

    # Conviction-based risk allocation
    if score >= 7:
        risk_pct  = 3.0
        size_label= "HIGH conviction"
    elif score >= 5:
        risk_pct  = 2.0
        size_label= "MEDIUM conviction"
    elif score >= 3:
        risk_pct  = 1.5
        size_label= "MODERATE conviction"
    else:
        risk_pct  = 1.0
        size_label= "LOW conviction"

    # Use ATR-based stop if available, else config default
    sl  = analysis.get("suggested_stop_loss")  or round(price*(1-config.STOP_LOSS_PERCENT/100), 4)
    tp  = analysis.get("suggested_take_profit") or round(price*(1+config.TAKE_PROFIT_PERCENT/100), 4)
    sl  = float(sl)
    tp  = float(tp)

    risk_per_share = max(price - sl, price * 0.01)
    max_risk       = cap * (risk_pct / 100)
    shares         = max(1, int(max_risk / risk_per_share))

    # Cap at configured capital per trade
    max_shares_by_cap = max(1, int(config.CAPITAL_PER_TRADE / price))
    shares = min(shares, max_shares_by_cap)

    total_cost = round(shares * price, 2)
    rr         = round((tp - price) / (price - sl), 2) if (price - sl) > 0 else 0

    return {
        "shares":            shares,
        "entry_price":       round(price, 4),
        "stop_loss":         round(sl, 4),
        "take_profit":       round(tp, 4),
        "total_cost":        total_cost,
        "risk_per_share":    round(risk_per_share, 4),
        "max_dollar_risk":   round(max_risk, 2),
        "risk_reward_ratio": rr,
        "risk_pct":          risk_pct,
        "size_label":        size_label,
    }
