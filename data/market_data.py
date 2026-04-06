"""
data/market_data.py — Fetches price and technical indicator data
Uses yfinance for stocks, ccxt for crypto.
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


def get_stock_data(ticker: str, period: str = "3mo", interval: str = "1d") -> dict:
    """
    Fetch OHLCV + technical indicators for a stock.
    Returns a dict with price data and computed indicators.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty:
            return {"error": f"No data returned for {ticker}"}

        df.dropna(inplace=True)

        # ── Technical Indicators ───────────────────────────────────────────────
        df["rsi"]    = ta.momentum.RSIIndicator(df["Close"]).rsi()
        df["macd"]   = ta.trend.MACD(df["Close"]).macd()
        df["macd_signal"] = ta.trend.MACD(df["Close"]).macd_signal()
        df["sma_20"] = ta.trend.SMAIndicator(df["Close"], window=20).sma_indicator()
        df["sma_50"] = ta.trend.SMAIndicator(df["Close"], window=50).sma_indicator()
        df["ema_12"] = ta.trend.EMAIndicator(df["Close"], window=12).ema_indicator()
        df["bb_high"] = ta.volatility.BollingerBands(df["Close"]).bollinger_hband()
        df["bb_low"]  = ta.volatility.BollingerBands(df["Close"]).bollinger_lband()
        df["atr"]    = ta.volatility.AverageTrueRange(
            df["High"], df["Low"], df["Close"]
        ).average_true_range()

        latest = df.iloc[-1]
        prev   = df.iloc[-2]

        # Volume trend
        avg_volume_10d = df["Volume"].tail(10).mean()
        volume_spike   = float(latest["Volume"]) > (avg_volume_10d * 1.5)

        # Price vs moving averages
        price = float(latest["Close"])

        return {
            "ticker": ticker,
            "price": round(price, 4),
            "change_pct": round(((price - float(prev["Close"])) / float(prev["Close"])) * 100, 2),
            "volume": int(latest["Volume"]),
            "volume_spike": volume_spike,
            "avg_volume_10d": int(avg_volume_10d),
            "rsi": round(float(latest["rsi"]), 2),
            "macd": round(float(latest["macd"]), 4),
            "macd_signal": round(float(latest["macd_signal"]), 4),
            "macd_crossover": (float(latest["macd"]) > float(latest["macd_signal"]) and
                               float(prev["macd"]) <= float(prev["macd_signal"])),
            "sma_20": round(float(latest["sma_20"]), 4),
            "sma_50": round(float(latest["sma_50"]), 4),
            "ema_12": round(float(latest["ema_12"]), 4),
            "bb_high": round(float(latest["bb_high"]), 4),
            "bb_low":  round(float(latest["bb_low"]),  4),
            "atr": round(float(latest["atr"]), 4),
            "above_sma20": price > float(latest["sma_20"]),
            "above_sma50": price > float(latest["sma_50"]),
            "week_high": round(float(df["High"].tail(5).max()), 4),
            "week_low":  round(float(df["Low"].tail(5).min()),  4),
            "month_high": round(float(df["High"].tail(21).max()), 4),
            "month_low":  round(float(df["Low"].tail(21).min()),  4),
        }
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


def get_crypto_data(symbol: str) -> dict:
    """
    Fetch OHLCV + indicators for a crypto pair via ccxt (Binance testnet).
    Falls back to a yfinance-based fetch if ccxt is unavailable.
    """
    if not CCXT_AVAILABLE:
        # Fallback: use yfinance with Yahoo-style ticker (e.g. BTC-USD)
        yf_symbol = symbol.replace("/", "-")
        return get_stock_data(yf_symbol, period="3mo", interval="1d")

    try:
        exchange_config = {"enableRateLimit": True}
        if BINANCE_TESTNET and BINANCE_API_KEY:
            exchange_config.update({
                "apiKey": BINANCE_API_KEY,
                "secret": BINANCE_SECRET_KEY,
                "options": {"defaultType": "spot"},
            })
            exchange = ccxt.binance(exchange_config)
            exchange.set_sandbox_mode(True)
        else:
            exchange = ccxt.binance(exchange_config)

        ohlcv = exchange.fetch_ohlcv(symbol, timeframe="1d", limit=100)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)

        df["rsi"]    = ta.momentum.RSIIndicator(df["Close"]).rsi()
        df["macd"]   = ta.trend.MACD(df["Close"]).macd()
        df["macd_signal"] = ta.trend.MACD(df["Close"]).macd_signal()
        df["sma_20"] = ta.trend.SMAIndicator(df["Close"], window=20).sma_indicator()
        df["sma_50"] = ta.trend.SMAIndicator(df["Close"], window=50).sma_indicator()
        df["atr"]    = ta.volatility.AverageTrueRange(
            df["High"], df["Low"], df["Close"]
        ).average_true_range()

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
    except Exception as e:
        return {"error": str(e), "ticker": symbol}
