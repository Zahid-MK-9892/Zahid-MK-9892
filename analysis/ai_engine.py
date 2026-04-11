"""
analysis/ai_engine.py — FRIDAY's analysis engine.
Full rule-based swing trading analysis. No API key required.
Optionally upgrades to Claude AI if ANTHROPIC_API_KEY has credits.
"""

import json
from config import ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS, MOCK_MODE

_PLACEHOLDER = {"your_anthropic_key_here", "", None}


def analyze_asset(ticker: str, market_data: dict, news_text: str) -> dict:
    """
    Main entry point. Uses Claude AI if key+credits available, else rule-based.
    Rule-based is the default and works perfectly for swing trading.
    """
    if "error" in market_data:
        return _hold("Data error: " + market_data["error"])

    use_ai = (
        not MOCK_MODE and
        ANTHROPIC_API_KEY and
        ANTHROPIC_API_KEY not in _PLACEHOLDER
    )

    if use_ai:
        result = _claude_analysis(ticker, market_data, news_text)
        if result:
            return result
        # If Claude fails for any reason, fall through to rule-based

    return _rule_based(ticker, market_data)


# ── Rule-Based Engine ──────────────────────────────────────────────────────────

def _rule_based(ticker: str, md: dict) -> dict:
    """
    Professional swing trading rule engine.
    Scores 8 signals across momentum, trend, volume and volatility.
    Each signal is weighted. Final score determines BUY / HOLD.
    """
    price       = float(md.get("price", 0) or 0)
    rsi         = float(md.get("rsi", 50) or 50)
    macd        = float(md.get("macd", 0) or 0)
    macd_sig    = float(md.get("macd_signal", 0) or 0)
    crossover   = bool(md.get("macd_crossover", False))
    above_sma20 = bool(md.get("above_sma20", False))
    above_sma50 = bool(md.get("above_sma50", False))
    vol_spike   = bool(md.get("volume_spike", False))
    bb_low      = float(md.get("bb_low", 0) or 0)
    bb_high     = float(md.get("bb_high", price * 1.1) or price * 1.1)
    atr         = float(md.get("atr", 0) or 0)
    change_pct  = float(md.get("change_pct", 0) or 0)

    score   = 0
    signals = []
    reasons = []

    # ── Signal 1: RSI (weight: 3) ──────────────────────────────────────────────
    if rsi < 28:
        score += 3; signals.append(f"RSI deeply oversold ({rsi:.1f})")
        reasons.append(f"RSI at {rsi:.1f} is deeply oversold — strong mean-reversion opportunity")
    elif rsi < 35:
        score += 2; signals.append(f"RSI oversold ({rsi:.1f})")
        reasons.append(f"RSI at {rsi:.1f} is oversold — bullish reversal likely")
    elif rsi < 43:
        score += 1; signals.append(f"RSI cooling off ({rsi:.1f})")
        reasons.append(f"RSI at {rsi:.1f} is below mid — moderate bullish bias")
    elif rsi > 72:
        score -= 3; signals.append(f"RSI overbought ({rsi:.1f})")
        reasons.append(f"RSI at {rsi:.1f} is overbought — risk of reversal")
    elif rsi > 65:
        score -= 2; signals.append(f"RSI elevated ({rsi:.1f})")
        reasons.append(f"RSI at {rsi:.1f} is elevated — momentum stretched")
    else:
        signals.append(f"RSI neutral ({rsi:.1f})")

    # ── Signal 2: MACD crossover (weight: 3) ──────────────────────────────────
    if crossover:
        score += 3; signals.append("MACD bullish crossover ✓")
        reasons.append("MACD just crossed above signal line — strong momentum confirmation")
    elif macd > macd_sig:
        score += 1; signals.append("MACD above signal line")
        reasons.append("MACD is above signal — positive momentum")
    elif macd < macd_sig:
        score -= 1; signals.append("MACD below signal line")
        reasons.append("MACD below signal — negative momentum")

    # ── Signal 3: Moving averages (weight: 2) ─────────────────────────────────
    if above_sma20 and above_sma50:
        score += 2; signals.append("Price above SMA20 + SMA50 — uptrend")
        reasons.append("Price is above both moving averages — confirmed uptrend")
    elif above_sma20 and not above_sma50:
        score += 1; signals.append("Price above SMA20 only — early trend")
        reasons.append("Price above SMA20 but below SMA50 — early recovery, watch SMA50")
    elif not above_sma20 and not above_sma50:
        score -= 2; signals.append("Price below both SMAs — downtrend")
        reasons.append("Price below SMA20 and SMA50 — bearish trend in place")
    else:
        score -= 1; signals.append("Price below SMA20 — weak")

    # ── Signal 4: Volume (weight: 1) ──────────────────────────────────────────
    if vol_spike and score > 0:
        score += 1; signals.append("Volume spike — strong conviction")
        reasons.append("Volume is 1.5x above average — buyers/sellers showing conviction")
    elif vol_spike and score < 0:
        score -= 1; signals.append("Volume spike on weakness — caution")

    # ── Signal 5: Bollinger Band position (weight: 1) ─────────────────────────
    if bb_low and price <= bb_low * 1.015:
        score += 1; signals.append("Price near lower Bollinger Band")
        reasons.append("Price near lower Bollinger Band — mean-reversion setup")
    elif bb_high and price >= bb_high * 0.985:
        score -= 1; signals.append("Price near upper Bollinger Band")
        reasons.append("Price near upper Bollinger Band — stretched, resistance ahead")

    # ── Signal 6: Daily momentum (weight: 1) ──────────────────────────────────
    if change_pct > 2.5:
        score += 1; signals.append(f"Strong day: +{change_pct:.1f}%")
    elif change_pct < -3.0:
        score -= 1; signals.append(f"Weak day: {change_pct:.1f}%")

    # ── Decision ───────────────────────────────────────────────────────────────
    sma20  = md.get("sma_20", price)
    sma50  = md.get("sma_50", price)

    if score >= 5:
        action, confidence, sentiment, risk = "BUY", min(88, 62 + score * 4), "BULLISH", "LOW"
        summary = (
            f"{ticker} has a strong bullish setup (score {score}/8). "
            + " ".join(reasons[:2])
            + f" Entry near ${price} with clear risk levels."
        )
    elif score >= 3:
        action, confidence, sentiment, risk = "BUY", min(78, 58 + score * 3), "BULLISH", "MEDIUM"
        summary = (
            f"{ticker} shows moderate bullish signals (score {score}/8). "
            + (reasons[0] if reasons else "Positive momentum developing.")
            + " Position sizing should be conservative."
        )
    elif score >= 1:
        action, confidence, sentiment, risk = "BUY", 62, "NEUTRAL", "MEDIUM"
        summary = (
            f"{ticker} has a marginal bullish edge (score {score}/8). "
            "Mixed signals present — small position only if risk/reward is favourable."
        )
    elif score <= -4:
        action, confidence, sentiment, risk = "HOLD", 70, "BEARISH", "HIGH"
        summary = (
            f"{ticker} shows strong bearish signals (score {score}/8). "
            + (reasons[0] if reasons else "Downtrend confirmed.")
            + " Avoid long entry — wait for reversal confirmation."
        )
    elif score <= -2:
        action, confidence, sentiment, risk = "HOLD", 60, "BEARISH", "MEDIUM"
        summary = (
            f"{ticker} is showing weakness (score {score}/8). "
            "Below key moving averages with negative momentum. Staying on sidelines."
        )
    else:
        action, confidence, sentiment, risk = "HOLD", 50, "NEUTRAL", "MEDIUM"
        summary = (
            f"{ticker} has no clear directional edge (score {score}/8). "
            "Signals are mixed — waiting for a higher-conviction setup before entering."
        )

    # Dynamic stop/target based on ATR if available
    if atr and price:
        suggested_sl = round(price - (atr * 2), 4)
        suggested_tp = round(price + (atr * 3), 4)
    else:
        suggested_sl = round(price * 0.95, 4)
        suggested_tp = round(price * 1.10, 4)

    return {
        "action":                action,
        "confidence":            confidence,
        "reasoning":             summary,
        "key_signals":           signals[:4],
        "risk_level":            risk,
        "suggested_entry":       round(price, 4) if action == "BUY" else None,
        "suggested_stop_loss":   suggested_sl    if action == "BUY" else None,
        "suggested_take_profit": suggested_tp    if action == "BUY" else None,
        "time_horizon":          "5-10 days",
        "sentiment":             sentiment,
        "score":                 score,
        "source":                "rule_based",
    }


# ── Optional Claude AI upgrade ─────────────────────────────────────────────────

_SYSTEM = """You are FRIDAY, an expert swing trading AI. Analyse the market data and return ONLY valid JSON:
{
  "action": "BUY"|"SELL"|"HOLD",
  "confidence": <0-100>,
  "reasoning": "<2-3 sentences>",
  "key_signals": ["signal1","signal2","signal3"],
  "risk_level": "LOW"|"MEDIUM"|"HIGH",
  "suggested_entry": <float|null>,
  "suggested_stop_loss": <float|null>,
  "suggested_take_profit": <float|null>,
  "time_horizon": "<e.g. 5-10 days>",
  "sentiment": "BULLISH"|"BEARISH"|"NEUTRAL"
}"""

def _claude_analysis(ticker: str, md: dict, news: str) -> dict | None:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = f"""Analyse {ticker} for swing trade:
Price: ${md.get('price')} | RSI: {md.get('rsi')} | Change: {md.get('change_pct')}%
MACD: {md.get('macd')} vs Signal: {md.get('macd_signal')} | Crossover: {md.get('macd_crossover')}
SMA20: {md.get('sma_20')} | SMA50: {md.get('sma_50')} | ATR: {md.get('atr')}
Above SMA20: {md.get('above_sma20')} | Above SMA50: {md.get('above_sma50')}
BB High: {md.get('bb_high')} | BB Low: {md.get('bb_low')} | Vol spike: {md.get('volume_spike')}
News: {news[:300]}
Return JSON only."""
        resp = client.messages.create(
            model=AI_MODEL, max_tokens=AI_MAX_TOKENS,
            system=_SYSTEM, messages=[{"role":"user","content":msg}]
        )
        raw = resp.content[0].text.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"): raw = raw[4:]
        result = json.loads(raw.strip())
        result["source"] = "claude_ai"
        return result
    except Exception:
        return None


def _hold(reason: str) -> dict:
    return {
        "action":"HOLD","confidence":0,"reasoning":reason,"key_signals":[],
        "risk_level":"HIGH","suggested_entry":None,"suggested_stop_loss":None,
        "suggested_take_profit":None,"time_horizon":"N/A","sentiment":"NEUTRAL","source":"error",
    }
