"""
config.py — FRIDAY's central configuration.
All settings loaded from .env and exposed as typed constants.
"""

import os
from dotenv import load_dotenv
load_dotenv()

# ── API Keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
ALPACA_API_KEY     = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY  = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL    = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY", "")
BINANCE_TESTNET    = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
NEWS_API_KEY       = os.getenv("NEWS_API_KEY", "")

# ── Telegram Alerts (free — no credit card needed) ────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Mode ───────────────────────────────────────────────────────────────────────
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

# ── Capital & Risk ─────────────────────────────────────────────────────────────
# Total portfolio capital available for trading
TOTAL_CAPITAL        = float(os.getenv("TOTAL_CAPITAL", 10000))

# Max spend per individual trade (USD)
CAPITAL_PER_TRADE    = float(os.getenv("CAPITAL_PER_TRADE", 500))

# Max % of capital at risk per trade (used for position sizing)
MAX_RISK_PERCENT     = float(os.getenv("MAX_RISK_PERCENT", 2))

# Stop loss % below entry
STOP_LOSS_PERCENT    = float(os.getenv("STOP_LOSS_PERCENT", 5))

# Take profit % above entry
TAKE_PROFIT_PERCENT  = float(os.getenv("TAKE_PROFIT_PERCENT", 10))

# ── Market Scanner Settings ────────────────────────────────────────────────────
# Enable full market scan (S&P 500 + crypto universe)
MARKET_SCAN_ENABLED  = os.getenv("MARKET_SCAN_ENABLED", "true").lower() == "true"

# How many top candidates to deep-analyse each cycle
SCAN_MAX_CANDIDATES  = int(os.getenv("SCAN_MAX_CANDIDATES", 60))

# Max NEW positions opened per scan cycle
SCAN_MAX_NEW_TRADES  = int(os.getenv("SCAN_MAX_NEW_TRADES", 5))

# Minimum stock price to consider (avoids penny stocks)
SCAN_MIN_PRICE       = float(os.getenv("SCAN_MIN_PRICE", 5.0))

# Minimum average daily volume to consider
SCAN_MIN_VOLUME      = int(os.getenv("SCAN_MIN_VOLUME", 500000))

# Include crypto in market scan
SCAN_INCLUDE_CRYPTO  = os.getenv("SCAN_INCLUDE_CRYPTO", "true").lower() == "true"

# ── Fallback Watchlist ─────────────────────────────────────────────────────────
# Only used if MARKET_SCAN_ENABLED=false
STOCK_WATCHLIST  = ["AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL"]
CRYPTO_WATCHLIST = ["BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT"]

# ── Schedule ───────────────────────────────────────────────────────────────────
# How often FRIDAY scans (minutes). 30 min recommended for swing trading.
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", 30))

# ── AI Model ───────────────────────────────────────────────────────────────────
AI_MODEL      = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 1500
