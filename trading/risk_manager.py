"""
trading/risk_manager.py — Dynamic risk manager with conviction-based sizing.
Position size scales with analysis score — higher conviction = larger position.

WEEK 2 (new):
  + SECTOR_MAP          — maps every supported ticker to its sector
  + get_sector()        — looks up sector for any ticker
  + MAX_SECTOR_POSITIONS — max 2 positions per sector at once
  + approve_trade()     — now checks sector concentration + cooling-off period
"""

import config

MIN_CONFIDENCE      = 62   # Minimum confidence % to trade
MAX_POSITIONS       = 14   # Max concurrent open positions
MAX_SECTOR_POSITIONS = 2   # Max positions in the same sector at once


# ══════════════════════════════════════════════════════════════════
#  WEEK 2 — SECTOR MAP
# ══════════════════════════════════════════════════════════════════

SECTOR_MAP = {
    # ── Technology ────────────────────────────────────────────────
    "AAPL":"Technology",  "MSFT":"Technology",  "NVDA":"Technology",
    "GOOGL":"Technology", "META":"Technology",  "ADBE":"Technology",
    "CRM":"Technology",   "AMD":"Technology",   "INTC":"Technology",
    "QCOM":"Technology",  "TXN":"Technology",   "IBM":"Technology",
    "INTU":"Technology",  "NOW":"Technology",   "SNOW":"Technology",
    "PLTR":"Technology",  "PANW":"Technology",  "CRWD":"Technology",
    "DDOG":"Technology",  "NET":"Technology",   "ZS":"Technology",
    "AVGO":"Technology",  "ORCL":"Technology",  "MDB":"Technology",
    "GTLB":"Technology",  "RBLX":"Technology",  "COIN":"Technology",
    # NSE Tech
    "TCS.NS":"Technology",    "INFY.NS":"Technology",  "WIPRO.NS":"Technology",
    "HCLTECH.NS":"Technology","TECHM.NS":"Technology",
    # LSE Tech
    # HKEX Tech
    "0700.HK":"Technology",   "1810.HK":"Technology",

    # ── Finance ───────────────────────────────────────────────────
    "JPM":"Finance",  "BAC":"Finance",  "WFC":"Finance",
    "GS":"Finance",   "MS":"Finance",   "C":"Finance",
    "BLK":"Finance",  "AXP":"Finance",  "V":"Finance",
    "MA":"Finance",   "SPGI":"Finance", "MCO":"Finance",
    # NSE Finance
    "HDFCBANK.NS":"Finance",  "ICICIBANK.NS":"Finance", "SBIN.NS":"Finance",
    "KOTAKBANK.NS":"Finance", "AXISBANK.NS":"Finance",  "BAJFINANCE.NS":"Finance",
    # LSE Finance
    "HSBA.L":"Finance",  "BARC.L":"Finance", "LLOY.L":"Finance", "STAN.L":"Finance",
    # HKEX Finance
    "0005.HK":"Finance", "1299.HK":"Finance", "0388.HK":"Finance",
    "2318.HK":"Finance", "1398.HK":"Finance", "0939.HK":"Finance",

    # ── Healthcare ────────────────────────────────────────────────
    "UNH":"Healthcare",  "JNJ":"Healthcare",  "LLY":"Healthcare",
    "ABBV":"Healthcare", "MRK":"Healthcare",  "PFE":"Healthcare",
    "AMGN":"Healthcare", "GILD":"Healthcare", "VRTX":"Healthcare",
    "REGN":"Healthcare", "ISRG":"Healthcare", "MDT":"Healthcare",
    "BSX":"Healthcare",  "ELV":"Healthcare",  "CI":"Healthcare",
    "HUM":"Healthcare",  "CVS":"Healthcare",  "ZTS":"Healthcare",
    "DXCM":"Healthcare",
    # NSE Healthcare
    "SUNPHARMA.NS":"Healthcare", "DRREDDY.NS":"Healthcare", "CIPLA.NS":"Healthcare",
    # LSE Healthcare
    "AZN.L":"Healthcare", "GSK.L":"Healthcare",

    # ── Consumer ──────────────────────────────────────────────────
    "HD":"Consumer",   "MCD":"Consumer",  "SBUX":"Consumer",
    "NKE":"Consumer",  "TGT":"Consumer",  "COST":"Consumer",
    "WMT":"Consumer",  "PG":"Consumer",   "KO":"Consumer",
    "PEP":"Consumer",  "PM":"Consumer",   "MO":"Consumer",
    "MNST":"Consumer", "CMG":"Consumer",  "YUM":"Consumer",
    "DPZ":"Consumer",  "AMZN":"Consumer",
    # NSE Consumer
    "HINDUNILVR.NS":"Consumer", "ITC.NS":"Consumer",      "NESTLEIND.NS":"Consumer",
    "ASIANPAINT.NS":"Consumer", "MARUTI.NS":"Consumer",   "TITAN.NS":"Consumer",
    "TATAMOTORS.NS":"Consumer",
    # LSE Consumer
    "ULVR.L":"Consumer", "DGE.L":"Consumer", "ABF.L":"Consumer",
    "CPG.L":"Consumer",
    # HKEX Consumer
    "9988.HK":"Consumer", "3690.HK":"Consumer",

    # ── Industrial ────────────────────────────────────────────────
    "HON":"Industrial", "CAT":"Industrial", "DE":"Industrial",
    "RTX":"Industrial", "GE":"Industrial",  "ETN":"Industrial",
    "EMR":"Industrial", "ITW":"Industrial", "NSC":"Industrial",
    "UPS":"Industrial", "FDX":"Industrial",
    # NSE Industrial
    "LT.NS":"Industrial", "JSWSTEEL.NS":"Industrial", "ULTRACEMCO.NS":"Industrial",
    # LSE Industrial
    "RIO.L":"Industrial", "AAL.L":"Industrial",

    # ── Energy ────────────────────────────────────────────────────
    "XOM":"Energy", "CVX":"Energy", "SLB":"Energy",
    "EOG":"Energy", "COP":"Energy",
    # NSE Energy
    "RELIANCE.NS":"Energy", "ONGC.NS":"Energy", "COALINDIA.NS":"Energy",
    # LSE Energy
    "SHEL.L":"Energy", "BP.L":"Energy",
    # HKEX Energy
    "0883.HK":"Energy",

    # ── Utilities ─────────────────────────────────────────────────
    "NEE":"Utilities", "SO":"Utilities", "DUK":"Utilities",
    # NSE Utilities
    "NTPC.NS":"Utilities", "POWERGRID.NS":"Utilities",
    # LSE Utilities
    "NG.L":"Utilities",

    # ── Real Estate ───────────────────────────────────────────────
    "PLD":"Real Estate", "AMT":"Real Estate",
    "EQIX":"Real Estate", "PSA":"Real Estate",

    # ── Telecom ───────────────────────────────────────────────────
    "BHARTIARTL.NS":"Telecom",
    "VOD.L":"Telecom", "BT-A.L":"Telecom",
    "0941.HK":"Telecom",

    # ── Conglomerate ──────────────────────────────────────────────
    "BRK-B":"Conglomerate",

    # ── Crypto (own sector — max 2 crypto at once) ────────────────
    "BTC-USD":"Crypto",  "ETH-USD":"Crypto",  "BNB-USD":"Crypto",
    "SOL-USD":"Crypto",  "ADA-USD":"Crypto",  "AVAX-USD":"Crypto",
    "DOT-USD":"Crypto",  "LINK-USD":"Crypto", "XRP-USD":"Crypto",
    "LTC-USD":"Crypto",  "BCH-USD":"Crypto",  "ALGO-USD":"Crypto",
}


def get_sector(ticker: str) -> str:
    """Look up sector for a ticker. Returns 'Unknown' if not mapped."""
    return SECTOR_MAP.get(ticker, "Unknown")


# ══════════════════════════════════════════════════════════════════
#  APPROVE TRADE  (Week 2: sector + cooling-off checks added)
# ══════════════════════════════════════════════════════════════════

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

    if float(price) < 5:
        return False, f"Price ${price} too low — avoiding penny stocks."

    # ── WEEK 2: Sector concentration check ────────────────────────
    sector = get_sector(ticker)
    if sector != "Unknown":
        sector_count = sum(
            1 for p in open_positions
            if get_sector(p.get("ticker", "")) == sector
        )
        if sector_count >= MAX_SECTOR_POSITIONS:
            return False, (f"Sector limit reached — already have {sector_count} "
                           f"{sector} positions (max {MAX_SECTOR_POSITIONS}).")

    # ── WEEK 2: Cooling-off period check ──────────────────────────
    try:
        from trading.journal import is_in_cooling_off
        if is_in_cooling_off(ticker, days=5):
            return False, f"{ticker} in 5-day cooling-off period after recent stop-loss."
    except Exception:
        pass  # If journal check fails, don't block the trade

    return True, "All checks passed."


# ══════════════════════════════════════════════════════════════════
#  POSITION SIZING  (unchanged from original)
# ══════════════════════════════════════════════════════════════════

def calculate_position(price: float, analysis: dict,
                        total_capital: float = None) -> dict:
    """
    Dynamic position sizing based on conviction score.
    Score 7-8 → risk 3% | Score 5-6 → risk 2% | Score 3-4 → risk 1.5% | Score 1-2 → risk 1%
    """
    price = float(price)
    score = analysis.get("score", 2)
    cap   = float(total_capital or config.CAPITAL_PER_TRADE)

    if score >= 7:
        risk_pct, size_label = 3.0, "HIGH conviction"
    elif score >= 5:
        risk_pct, size_label = 2.0, "MEDIUM conviction"
    elif score >= 3:
        risk_pct, size_label = 1.5, "MODERATE conviction"
    else:
        risk_pct, size_label = 1.0, "LOW conviction"

    sl  = float(analysis.get("suggested_stop_loss")  or round(price*(1-config.STOP_LOSS_PERCENT/100), 4))
    tp  = float(analysis.get("suggested_take_profit") or round(price*(1+config.TAKE_PROFIT_PERCENT/100), 4))

    risk_per_share    = max(price - sl, price * 0.01)
    max_risk          = cap * (risk_pct / 100)
    shares            = max(1, int(max_risk / risk_per_share))
    max_shares_by_cap = max(1, int(config.CAPITAL_PER_TRADE / price))
    shares            = min(shares, max_shares_by_cap)

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
