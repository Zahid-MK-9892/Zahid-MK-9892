# FRIDAY Setup Guide — From Zero to Paper Trading

## Step 1 — Install Python (if not already installed)
Download Python 3.11+ from https://python.org
Verify: `python --version`

---

## Step 2 — Create Your Accounts (all free)

### A. Alpaca Markets (Paper Stock Trading)
1. Go to https://alpaca.markets and sign up (free)
2. In the dashboard, switch to **Paper Trading** mode
3. Go to **Overview → API Keys → Generate New Keys**
4. Copy your API Key and Secret Key

### B. Binance Testnet (Paper Crypto Trading)
1. Go to https://testnet.binance.vision
2. Log in with your GitHub account
3. Click **Generate HMAC_SHA256 Key**
4. Copy your API Key and Secret Key

### C. Anthropic API (FRIDAY's Brain)
1. Go to https://console.anthropic.com
2. Sign up → Go to **API Keys** → **Create Key**
3. Copy your API key (starts with `sk-ant-...`)
4. Add a small credit (~$5) to your account — Claude is cheap to run

### D. NewsAPI (Market News)
1. Go to https://newsapi.org
2. Sign up for the **free Developer plan**
3. Copy your API Key from the dashboard

---

## Step 3 — Install FRIDAY

```bash
# Clone/copy the friday/ folder to your computer, then:
cd friday
pip install -r requirements.txt

# Copy the env template
cp .env.example .env
```

---

## Step 4 — Add Your Keys to .env

Open `.env` in any text editor and fill in your keys:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
ALPACA_API_KEY=your-alpaca-key
ALPACA_SECRET_KEY=your-alpaca-secret
BINANCE_API_KEY=your-binance-testnet-key
BINANCE_SECRET_KEY=your-binance-testnet-secret
NEWS_API_KEY=your-newsapi-key
MOCK_MODE=false          ← Change to false once keys are in
```

---

## Step 5 — First Run (Test Mode)

Before adding any keys, FRIDAY works in MOCK_MODE (safe simulation):
```bash
python main.py
```

You'll see FRIDAY scan every stock and crypto on her watchlist,
make AI decisions, and log them to `friday_journal.db`.

---

## Step 6 — Go Live with Paper Trading

Once your keys are in `.env` and `MOCK_MODE=false`:
```bash
python main.py             # Single scan run
python main.py --loop      # Run every 30 minutes (continuous)
python main.py --summary   # View your P&L and open positions
```

---

## Step 7 — Customize FRIDAY

Edit `config.py` to change her watchlists and risk settings:

```python
STOCK_WATCHLIST  = ["AAPL", "NVDA", ...]   # Add any US stock
CRYPTO_WATCHLIST = ["BTC/USDT", ...]       # Add any Binance pair
CAPITAL_PER_TRADE    = 500    # USD per trade
MAX_RISK_PERCENT     = 2      # Max % of capital at risk
STOP_LOSS_PERCENT    = 5      # Stop loss distance %
TAKE_PROFIT_PERCENT  = 10     # Take profit target %
SCAN_INTERVAL_MINUTES = 30    # How often she scans
```

---

## How to Read FRIDAY's Output

```
[10:32:01] [INFO]  Scanning NVDA...
[10:32:02] [INFO]  NVDA | Price: $875.20 | RSI: 42.5
[10:32:03] [BUY]   NVDA → BUY (confidence: 74%) | RSI oversold, MACD crossing...
[10:32:03] [TRADE] NVDA position: 1 shares @ $875.20 | SL: $831.44 | TP: $962.72 | R/R: 2.0x
[10:32:04] [BUY]   ORDER PLACED ✓ | NVDA | ID: MOCK-A3F1B2C4 | Cost: $875.20
```

---

## FRIDAY's Database

All decisions are logged to `friday_journal.db` (SQLite).
You can open it with DB Browser for SQLite (free app) to inspect:
- `scans` table: every analysis FRIDAY ran
- `trades` table: every order placed, with P&L when closed

---

## Important Reminders

- Always paper trade for at least 4-6 weeks before using real money
- Past performance of a strategy does not guarantee future results
- FRIDAY is a tool — not financial advice. You are responsible for your trades.
- Keep `MAX_RISK_PERCENT` at 2% or less. Protect your capital first.
