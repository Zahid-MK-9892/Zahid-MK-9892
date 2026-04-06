"""
analysis/ai_engine.py — FRIDAY's AI brain powered by Claude.
Sends market data + news to Claude and gets back a structured trade decision.
"""

import json
import anthropic
from config import ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS, MOCK_MODE


SYSTEM_PROMPT = """You are FRIDAY — an expert swing trading AI analyst specializing in stocks and cryptocurrency.
Your job is to analyze market data and news for a given asset and produce a clear, well-reasoned trade recommendation.

You think like a professional swing trader with 15+ years of experience. You consider:
- Technical analysis: RSI, MACD, Bollinger Bands, Moving Averages, volume, ATR
- Fundamental context: earnings, sector trends, macroeconomic factors
- News sentiment: recent headlines and their likely market impact
- Risk/reward ratio: you only recommend trades with a clear edge

DECISION RULES you follow strictly:
- RSI > 70: overbought → lean bearish or hold
- RSI < 30: oversold → lean bullish
- MACD bullish crossover + price above SMA20 → bullish signal
- Price below SMA20 and SMA50 → bearish trend
- Volume spike + price breakout → strong confirmation signal
- Never recommend a trade without a clear stop-loss and take-profit level
- Confidence below 60% → always output HOLD

You MUST respond ONLY with a valid JSON object — no preamble, no explanation outside the JSON.
The JSON must exactly follow this structure:
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": <integer 0-100>,
  "reasoning": "<2-3 sentence explanation of your decision>",
  "key_signals": ["<signal 1>", "<signal 2>", "<signal 3>"],
  "risk_level": "LOW" | "MEDIUM" | "HIGH",
  "suggested_entry": <float or null>,
  "suggested_stop_loss": <float or null>,
  "suggested_take_profit": <float or null>,
  "time_horizon": "<e.g. 3-7 days>",
  "sentiment": "BULLISH" | "BEARISH" | "NEUTRAL"
}"""


def analyze_asset(ticker: str, market_data: dict, news_text: str) -> dict:
    """
    Calls Claude to analyze the given asset and returns a trade decision dict.
    Falls back to mock response if MOCK_MODE or no API key.
    """
    if MOCK_MODE or not ANTHROPIC_API_KEY:
        return _mock_analysis(ticker, market_data)

    if "error" in market_data:
        return {"action": "HOLD", "confidence": 0, "reasoning": f"Data error: {market_data['error']}",
                "key_signals": [], "risk_level": "HIGH", "suggested_entry": None,
                "suggested_stop_loss": None, "suggested_take_profit": None,
                "time_horizon": "N/A", "sentiment": "NEUTRAL"}

    user_message = f"""
Analyze this asset and provide your swing trade recommendation:

TICKER: {ticker}

PRICE DATA:
- Current price: ${market_data.get('price')}
- 1-day change: {market_data.get('change_pct')}%
- RSI (14): {market_data.get('rsi')}
- MACD: {market_data.get('macd')} | Signal: {market_data.get('macd_signal')}
- MACD Bullish Crossover: {market_data.get('macd_crossover')}
- SMA 20: {market_data.get('sma_20')} | SMA 50: {market_data.get('sma_50')}
- Price above SMA20: {market_data.get('above_sma20')} | above SMA50: {market_data.get('above_sma50')}
- Bollinger Band High: {market_data.get('bb_high')} | Low: {market_data.get('bb_low')}
- ATR (volatility): {market_data.get('atr')}
- Volume spike (1.5x avg): {market_data.get('volume_spike')}
- 5-day range: ${market_data.get('week_low')} – ${market_data.get('week_high')}
- 1-month range: ${market_data.get('month_low')} – ${market_data.get('month_high')}

RECENT NEWS:
{news_text}

Provide your structured JSON analysis now.
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=AI_MODEL,
            max_tokens=AI_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        return json.loads(raw)

    except json.JSONDecodeError:
        return {"action": "HOLD", "confidence": 0,
                "reasoning": "AI returned unparseable response. Defaulting to HOLD.",
                "key_signals": [], "risk_level": "HIGH",
                "suggested_entry": None, "suggested_stop_loss": None,
                "suggested_take_profit": None, "time_horizon": "N/A",
                "sentiment": "NEUTRAL"}
    except Exception as e:
        return {"action": "HOLD", "confidence": 0,
                "reasoning": f"AI engine error: {str(e)}",
                "key_signals": [], "risk_level": "HIGH",
                "suggested_entry": None, "suggested_stop_loss": None,
                "suggested_take_profit": None, "time_horizon": "N/A",
                "sentiment": "NEUTRAL"}


def _mock_analysis(ticker: str, market_data: dict) -> dict:
    """Simulated AI analysis for mock/test mode."""
    price = market_data.get("price", 100)
    rsi   = market_data.get("rsi", 50)

    if rsi and rsi < 40:
        action, confidence, sentiment = "BUY", 72, "BULLISH"
        reasoning = f"[MOCK] {ticker} RSI is oversold at {rsi}. Price near support with improving momentum."
    elif rsi and rsi > 65:
        action, confidence, sentiment = "HOLD", 55, "NEUTRAL"
        reasoning = f"[MOCK] {ticker} RSI elevated at {rsi}. Waiting for pullback before entry."
    else:
        action, confidence, sentiment = "HOLD", 60, "NEUTRAL"
        reasoning = f"[MOCK] {ticker} shows mixed signals. No high-conviction setup at current levels."

    return {
        "action": action,
        "confidence": confidence,
        "reasoning": reasoning,
        "key_signals": [f"RSI: {rsi}", "Mock MACD: neutral", "Mock volume: normal"],
        "risk_level": "MEDIUM",
        "suggested_entry": price,
        "suggested_stop_loss": round(price * 0.95, 4),
        "suggested_take_profit": round(price * 1.10, 4),
        "time_horizon": "5-10 days",
        "sentiment": sentiment,
    }
