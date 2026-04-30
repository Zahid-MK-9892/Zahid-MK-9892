"""
data/market_data.py — Fetches price and technical indicator data.
Uses yfinance for stocks, ccxt for crypto.

FIXED: handles new yfinance MultiIndex column format (v0.2.x+)
FIXED: crypto falls back to yfinance if Binance testnet has too few candles

WEEK 4 ADDITIONS (surgical — all existing keys preserved):
  + rvol             — Relative Volume vs 20-day avg (conviction filter)
  + weekly_trend     — 'BULLISH'|'BEARISH'|'NEUTRAL' based on weekly SMA20
  + weekly_above_sma20 — bool: price above weekly SMA20
  + weekly_rsi       — RSI on weekly chart (higher-timeframe momentum)
  + h4_trend         — 'BULLISH'|'BEARISH'|'NEUTRAL' based on 4H SMA20
  + h4_macd_bullish  — bool: 4H MACD above signal line
"""

import pandas as pd
import yfinance as yf
import ta
from config import BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET

try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False


def _flatten_yfinance_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Newer versions of yfinance return a MultiIndex column DataFrame like:
        ('Close', 'AAPL'), ('High', 'AAPL'), ...
    This flattens it back to simple column names: 'Close', 'High', ...
    """
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


# ══════════════════════════════════════════════════════════════════
#  WEEK 4 — MULTI-TIMEFRAME HELPERS
# ══════════════════════════════════════════════════════════════════

def _get_weekly_signals(yf_symbol: str) -> dict:
    """
    Fetch weekly OHLCV and compute:
      - weekly_trend: BULLISH if price > weekly SMA20, else BEARISH
      - weekly_above_sma20: bool
      - weekly_rsi: RSI(14) on weekly candles

    Returns a dict with safe defaults on any failure.
    Defaults to NEUTRAL so a fetch failure never blocks a trade.
    """
    defaults = {
        "weekly_trend":      "NEUTRAL",
        "weekly_above_sma20": False,
        "weekly_rsi":        50.0,
    }
    try:
        df = yf.download(yf_symbol, period="2y", interval="1wk",
                         progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 25:
            return defaults

        df = _flatten_yfinance_df(df)
        df.dropna(inplace=True)

        close = df["Close"].squeeze()
        sma20 = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        rsi   = ta.momentum.RSIIndicator(close, window=14).rsi()

        latest_close = float(close.iloc[-1])
        latest_sma20 = float(sma20.iloc[-1]) if not pd.isna(sma20.iloc[-1]) else latest_close
        latest_rsi   = float(rsi.iloc[-1])   if not pd.isna(rsi.iloc[-1])   else 50.0

        above = latest_close > latest_sma20
        trend = "BULLISH" if above else "BEARISH"

        return {
            "weekly_trend":       trend,
            "weekly_above_sma20": above,
            "weekly_rsi":         round(latest_rsi, 2),
        }
    except Exception:
        return defaults


def _get_4h_signals(yf_symbol: str) -> dict:
    """
    Fetch 4-hour OHLCV and compute:
      - h4_trend: BULLISH if price > 4H SMA20, else BEARISH
      - h4_macd_bullish: bool (4H MACD > signal line)

    Returns a dict with safe defaults on any failure.
    Defaults to NEUTRAL so a fetch failure never blocks a trade.
    """
    defaults = {
        "h4_trend":         "NEUTRAL",
        "h4_macd_bullish":  False,
    }
    try:
        df = yf.download(yf_symbol, period="30d", interval="4h",
                         progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 26:
            return defaults

        df = _flatten_yfinance_df(df)
        df.dropna(inplace=True)

        close = df["Close"].squeeze()

        sma20  = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        macd   = ta.trend.MACD(close).macd()
        macd_s = ta.trend.MACD(close).macd_signal()

        latest_close = float(close.iloc[-1])
        latest_sma20 = float(sma20.iloc[-1])  if not pd.isna(sma20.iloc[-1])  else latest_close
        latest_macd  = float(macd.iloc[-1])   if not pd.isna(macd.iloc[-1])   else 0.0
        latest_sig   = float(macd_s.iloc[-1]) if not pd.isna(macd_s.iloc[-1]) else 0.0

        above        = latest_close > latest_sma20
        macd_bull    = latest_macd > latest_sig

        return {
            "h4_trend":        "BULLISH" if above else "BEARISH",
            "h4_macd_bullish":  macd_bull,
        }
    except Exception:
        return defaults


# ══════════════════════════════════════════════════════════════════
#  MAIN STOCK DATA FETCH
# ══════════════════════════════════════════════════════════════════

def get_stock_data(ticker: str, period: str = "6mo", interval: str = "1d") -> dict:
    """
    Fetch OHLCV + technical indicators for a stock.
    Returns a dict with price data and computed indicators.

    Week 4: also fetches weekly + 4H signals and RVOL.
    All new keys have safe defaults — no existing callers break.
    """
    try:
        df = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )

        if df.empty:
            return {"error": f"No data returned for {ticker}", "ticker": ticker}

        df = _flatten_yfinance_df(df)
        df.dropna(subset=["Close", "High", "Low", "Volume"], inplace=True)

        if len(df) < 52:
            return {"error": f"Not enough data for {ticker} ({len(df)} rows)", "ticker": ticker}

        # Squeeze all columns to 1D Series
        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()
        volume = df["Volume"].squeeze()

        # ── Technical Indicators (daily) ──────────────────────────────────────
        df["rsi"]         = ta.momentum.RSIIndicator(close).rsi()
        df["macd"]        = ta.trend.MACD(close).macd()
        df["macd_signal"] = ta.trend.MACD(close).macd_signal()
        df["sma_20"]      = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        df["sma_50"]      = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        df["ema_12"]      = ta.trend.EMAIndicator(close, window=12).ema_indicator()
        df["bb_high"]     = ta.volatility.BollingerBands(close).bollinger_hband()
        df["bb_low"]      = ta.volatility.BollingerBands(close).bollinger_lband()
        df["atr"]         = ta.volatility.AverageTrueRange(high, low, close).average_true_range()

        df.dropna(inplace=True)
        if len(df) < 2:
            return {"error": f"Insufficient data after indicators for {ticker}", "ticker": ticker}

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        avg_volume_10d = float(volume.tail(10).mean())
        avg_volume_20d = float(volume.tail(20).mean())   # ← Week 4: 20-day for RVOL
        price          = float(latest["Close"])
        today_volume   = float(latest["Volume"])

        # ── WEEK 4: RVOL ──────────────────────────────────────────────────────
        # Relative Volume = today's volume / 20-day avg daily volume
        # >1.5 = significantly above average (institutional conviction)
        # <0.5 = very quiet session (weak signal reliability)
        rvol = round(today_volume / avg_volume_20d, 2) if avg_volume_20d > 0 else 1.0

        # ── WEEK 4: Weekly + 4H signals ───────────────────────────────────────
        # yfinance uses same ticker format for weekly/4H as daily
        weekly = _get_weekly_signals(ticker)
        h4     = _get_4h_signals(ticker)

        # ── Build return dict ─────────────────────────────────────────────────
        result = {
            # ── Existing keys (all preserved) ──────────────────────────────
            "ticker":        ticker,
            "price":         round(price, 4),
            "change_pct":    round(((price - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "volume":        int(today_volume),
            "volume_spike":  today_volume > (avg_volume_10d * 1.5),
            "avg_volume_10d": int(avg_volume_10d),
            "rsi":           round(float(latest["rsi"]), 2),
            "macd":          round(float(latest["macd"]), 4),
            "macd_signal":   round(float(latest["macd_signal"]), 4),
            "macd_crossover": (
                float(latest["macd"]) > float(latest["macd_signal"]) and
                float(prev["macd"]) <= float(prev["macd_signal"])
            ),
            "sma_20":        round(float(latest["sma_20"]), 4),
            "sma_50":        round(float(latest["sma_50"]), 4),
            "ema_12":        round(float(latest["ema_12"]), 4),
            "bb_high":       round(float(latest["bb_high"]), 4),
            "bb_low":        round(float(latest["bb_low"]),  4),
            "atr":           round(float(latest["atr"]), 4),
            "above_sma20":   price > float(latest["sma_20"]),
            "above_sma50":   price > float(latest["sma_50"]),
            "week_high":     round(float(high.tail(5).max()),  4),
            "week_low":      round(float(low.tail(5).min()),   4),
            "month_high":    round(float(high.tail(21).max()), 4),
            "month_low":     round(float(low.tail(21).min()),  4),
            # ── Week 4: New keys ───────────────────────────────────────────
            "rvol":              rvol,
            "avg_volume_20d":    int(avg_volume_20d),
            **weekly,   # weekly_trend, weekly_above_sma20, weekly_rsi
            **h4,       # h4_trend, h4_macd_bullish
        }
        return result

    except Exception as e:
        return {"error": str(e), "ticker": ticker}


# ══════════════════════════════════════════════════════════════════
#  CRYPTO DATA FETCH  (unchanged — crypto has no weekly earnings risk)
# ══════════════════════════════════════════════════════════════════

def get_crypto_data(symbol: str) -> dict:
    """
    Fetch OHLCV + indicators for a crypto pair.
    Tries Binance testnet first, falls back to yfinance if testnet has too few candles.
    Week 4: crypto also gets weekly + 4H signals via yfinance fallback path.
    """
    if not CCXT_AVAILABLE or not BINANCE_API_KEY:
        return _crypto_via_yfinance(symbol)

    try:
        exchange_config = {
            "enableRateLimit": True,
            "apiKey":  BINANCE_API_KEY,
            "secret":  BINANCE_SECRET_KEY,
            "options": {"defaultType": "spot"},
        }
        exchange = ccxt.binance(exchange_config)
        if BINANCE_TESTNET:
            exchange.set_sandbox_mode(True)

        ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=200)

        if not ohlcv or len(ohlcv) < 52:
            return _crypto_via_yfinance(symbol)

        df = pd.DataFrame(ohlcv, columns=["timestamp","Open","High","Low","Close","Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]
        vol   = df["Volume"]

        df["rsi"]         = ta.momentum.RSIIndicator(close).rsi()
        df["macd"]        = ta.trend.MACD(close).macd()
        df["macd_signal"] = ta.trend.MACD(close).macd_signal()
        df["sma_20"]      = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        df["sma_50"]      = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        df["atr"]         = ta.volatility.AverageTrueRange(high, low, close).average_true_range()

        df.dropna(inplace=True)
        latest = df.iloc[-1]
        prev   = df.iloc[-2]
        price  = float(latest["Close"])

        avg_volume_20d = float(vol.tail(20).mean())
        today_volume   = float(latest["Volume"])
        rvol           = round(today_volume / avg_volume_20d, 2) if avg_volume_20d > 0 else 1.0

        # Weekly + 4H for crypto via yfinance
        yf_sym = symbol.replace("/USDT","-USD").replace("/BTC","-BTC").replace("/","-")
        weekly = _get_weekly_signals(yf_sym)
        h4     = _get_4h_signals(yf_sym)

        return {
            "ticker":         symbol,
            "price":          round(price, 4),
            "change_pct":     round(((price - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "volume":         today_volume,
            "volume_spike":   today_volume > (float(vol.tail(10).mean()) * 1.5),
            "avg_volume_10d": int(float(vol.tail(10).mean())),
            "rsi":            round(float(latest["rsi"]), 2),
            "macd":           round(float(latest["macd"]), 4),
            "macd_signal":    round(float(latest["macd_signal"]), 4),
            "sma_20":         round(float(latest["sma_20"]), 4),
            "sma_50":         round(float(latest["sma_50"]), 4),
            "atr":            round(float(latest["atr"]), 4),
            "above_sma20":    price > float(latest["sma_20"]),
            "above_sma50":    price > float(latest["sma_50"]),
            # Week 4
            "rvol":           rvol,
            "avg_volume_20d": int(avg_volume_20d),
            **weekly,
            **h4,
        }

    except Exception:
        return _crypto_via_yfinance(symbol)


def _crypto_via_yfinance(symbol: str) -> dict:
    """
    Fetches crypto data from Yahoo Finance as a reliable fallback.
    Converts 'BTC/USDT' -> 'BTC-USD' for Yahoo Finance format.
    Week 4: weekly + 4H signals included via get_stock_data().
    """
    yf_symbol = symbol.replace("/USDT","-USD").replace("/BTC","-BTC").replace("/","-")
    return get_stock_data(yf_symbol, period="6mo", interval="1d")
