"""
data/market_data.py — Fetches price and technical indicator data
Uses yfinance for stocks, ccxt for crypto.

FIXED: handles new yfinance MultiIndex column format (v0.2.x+)
FIXED: crypto falls back to yfinance if Binance testnet has too few candles
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


def get_stock_data(ticker: str, period: str = "6mo", interval: str = "1d") -> dict:
    """
    Fetch OHLCV + technical indicators for a stock.
    Returns a dict with price data and computed indicators.
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

        # Fix for new yfinance MultiIndex format
        df = _flatten_yfinance_df(df)
        df.dropna(subset=["Close", "High", "Low", "Volume"], inplace=True)

        if len(df) < 52:
            return {"error": f"Not enough data for {ticker} ({len(df)} rows)", "ticker": ticker}

        # Squeeze all columns to 1D Series — this is the critical fix
        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()
        volume = df["Volume"].squeeze()

        # Technical Indicators
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
        price          = float(latest["Close"])

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "change_pct": round(((price - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "volume": int(float(latest["Volume"])),
            "volume_spike": float(latest["Volume"]) > (avg_volume_10d * 1.5),
            "avg_volume_10d": int(avg_volume_10d),
            "rsi": round(float(latest["rsi"]), 2),
            "macd": round(float(latest["macd"]), 4),
            "macd_signal": round(float(latest["macd_signal"]), 4),
            "macd_crossover": (
                float(latest["macd"]) > float(latest["macd_signal"]) and
                float(prev["macd"]) <= float(prev["macd_signal"])
            ),
            "sma_20": round(float(latest["sma_20"]), 4),
            "sma_50": round(float(latest["sma_50"]), 4),
            "ema_12": round(float(latest["ema_12"]), 4),
            "bb_high": round(float(latest["bb_high"]), 4),
            "bb_low":  round(float(latest["bb_low"]),  4),
            "atr": round(float(latest["atr"]), 4),
            "above_sma20": price > float(latest["sma_20"]),
            "above_sma50": price > float(latest["sma_50"]),
            "week_high":  round(float(high.tail(5).max()),  4),
            "week_low":   round(float(low.tail(5).min()),   4),
            "month_high": round(float(high.tail(21).max()), 4),
            "month_low":  round(float(low.tail(21).min()),  4),
        }

    except Exception as e:
        return {"error": str(e), "ticker": ticker}


def get_crypto_data(symbol: str) -> dict:
    """
    Fetch OHLCV + indicators for a crypto pair.
    Tries Binance testnet first, falls back to yfinance if testnet has too few candles.
    """
    if not CCXT_AVAILABLE or not BINANCE_API_KEY:
        return _crypto_via_yfinance(symbol)

    try:
        exchange_config = {
            "enableRateLimit": True,
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET_KEY,
            "options": {"defaultType": "spot"},
        }
        exchange = ccxt.binance(exchange_config)
        if BINANCE_TESTNET:
            exchange.set_sandbox_mode(True)

        ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=200)

        if not ohlcv or len(ohlcv) < 52:
            return _crypto_via_yfinance(symbol)

        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        close = df["Close"]
        high  = df["High"]
        low   = df["Low"]

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

        return {
            "ticker": symbol,
            "price": round(price, 4),
            "change_pct": round(((price - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "volume": float(latest["Volume"]),
            "rsi": round(float(latest["rsi"]), 2),
            "macd": round(float(latest["macd"]), 4),
            "macd_signal": round(float(latest["macd_signal"]), 4),
            "sma_20": round(float(latest["sma_20"]), 4),
            "sma_50": round(float(latest["sma_50"]), 4),
            "atr": round(float(latest["atr"]), 4),
            "above_sma20": price > float(latest["sma_20"]),
            "above_sma50": price > float(latest["sma_50"]),
        }

    except Exception:
        return _crypto_via_yfinance(symbol)


def _crypto_via_yfinance(symbol: str) -> dict:
    """
    Fetches crypto data from Yahoo Finance as a reliable fallback.
    Converts 'BTC/USDT' -> 'BTC-USD' for Yahoo Finance format.
    """
    yf_symbol = symbol.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
    return get_stock_data(yf_symbol, period="6mo", interval="1d")
