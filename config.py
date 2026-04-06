"""
config.py — FRIDAY's central configuration
Loads all settings from .env and exposes them as typed constants.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ALPACA_API_KEY      = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY   = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL     = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
BINANCE_API_KEY     = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET_KEY  = os.getenv("BINANCE_SECRET_KEY", "")
BINANCE_TESTNET     = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
NEWS_API_KEY        = os.getenv("NEWS_API_KEY", "")

# ── Mode ───────────────────────────────────────────────────────────────────────
# MOCK_MODE = True means no real API calls, pure simulation. Safe to test with.
MOCK_MODE = os.getenv("MOCK_MODE", "true").lower() == "true"

# ── Risk Settings ──────────────────────────────────────────────────────────────
CAPITAL_PER_TRADE    = float(os.getenv("CAPITAL_PER_TRADE", 500))
MAX_RISK_PERCENT     = float(os.getenv("MAX_RISK_PERCENT", 2))
STOP_LOSS_PERCENT    = float(os.getenv("STOP_LOSS_PERCENT", 5))
TAKE_PROFIT_PERCENT  = float(os.getenv("TAKE_PROFIT_PERCENT", 10))

# ── Watchlists ─────────────────────────────────────────────────────────────────
# Add or remove tickers as you like
STOCK_WATCHLIST = ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"]
CRYPTO_WATCHLIST = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]

# ── Schedule ───────────────────────────────────────────────────────────────────
# How often FRIDAY runs her analysis (in minutes)
SCAN_INTERVAL_MINUTES = 30

# ── AI Model ───────────────────────────────────────────────────────────────────
AI_MODEL = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 1500
