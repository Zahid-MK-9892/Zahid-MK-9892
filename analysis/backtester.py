"""
analysis/backtester.py — Walk-forward backtester using rule-based signals.
Tests FRIDAY's strategy on 1 year of historical data.
"""

import pandas as pd
import yfinance as yf
import ta
from datetime import datetime


def _flatten(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def run_backtest(ticker: str, period: str = "1y",
                 stop_pct: float = 5.0, target_pct: float = 10.0,
                 capital: float = 500.0) -> dict:
    """
    Walk-forward backtest: apply rule-based signals day by day.
    Returns performance stats + equity curve + trade list.
    """
    try:
        df = yf.download(ticker, period=period, interval="1d",
                         progress=False, auto_adjust=True)
        if df.empty or len(df) < 60:
            return {"error": f"Not enough data for {ticker}"}

        df = _flatten(df)
        df.dropna(inplace=True)

        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()

        df["rsi"]         = ta.momentum.RSIIndicator(close).rsi()
        df["macd"]        = ta.trend.MACD(close).macd()
        df["macd_signal"] = ta.trend.MACD(close).macd_signal()
        df["sma_20"]      = ta.trend.SMAIndicator(close, window=20).sma_indicator()
        df["sma_50"]      = ta.trend.SMAIndicator(close, window=50).sma_indicator()
        df.dropna(inplace=True)

        trades      = []
        equity      = [capital]
        cash        = capital
        position    = None

        for i in range(1, len(df)):
            row  = df.iloc[i]
            prev = df.iloc[i - 1]
            price = float(row["Close"])
            date  = str(df.index[i])[:10]

            # Check exit if in position
            if position:
                if price <= position["stop"]:
                    pnl  = (price - position["entry"]) * position["shares"]
                    cash += capital + pnl
                    trades.append({**position, "exit": price, "exit_date": date,
                                   "pnl": round(pnl, 2), "outcome": "LOSS"})
                    position = None
                elif price >= position["target"]:
                    pnl  = (price - position["entry"]) * position["shares"]
                    cash += capital + pnl
                    trades.append({**position, "exit": price, "exit_date": date,
                                   "pnl": round(pnl, 2), "outcome": "WIN"})
                    position = None

            # Entry signal (only if flat)
            if not position:
                score = _score(row, prev)
                if score >= 2:
                    shares   = max(1, int((capital * 0.02) / (price * stop_pct / 100)))
                    stop     = round(price * (1 - stop_pct / 100), 4)
                    target   = round(price * (1 + target_pct / 100), 4)
                    cash    -= capital
                    position = {"ticker": ticker, "entry": price, "entry_date": date,
                                "shares": shares, "stop": stop, "target": target,
                                "score": score}

            equity.append(round(cash + (price * position["shares"] if position else 0), 2))

        # Close any open position at last price
        if position:
            last_price = float(df.iloc[-1]["Close"])
            pnl = (last_price - position["entry"]) * position["shares"]
            trades.append({**position, "exit": last_price,
                           "exit_date": str(df.index[-1])[:10],
                           "pnl": round(pnl, 2),
                           "outcome": "WIN" if pnl > 0 else "LOSS"})

        wins       = [t for t in trades if t["outcome"] == "WIN"]
        losses     = [t for t in trades if t["outcome"] == "LOSS"]
        total_pnl  = round(sum(t["pnl"] for t in trades), 2)
        win_rate   = round(len(wins) / len(trades) * 100, 1) if trades else 0
        avg_win    = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0
        avg_loss   = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0
        max_dd     = _max_drawdown(equity)
        best       = max(trades, key=lambda t: t["pnl"]) if trades else {}
        worst      = min(trades, key=lambda t: t["pnl"]) if trades else {}

        return {
            "ticker":       ticker,
            "period":       period,
            "total_trades": len(trades),
            "wins":         len(wins),
            "losses":       len(losses),
            "win_rate":     win_rate,
            "total_pnl":    total_pnl,
            "avg_win":      avg_win,
            "avg_loss":     avg_loss,
            "max_drawdown": max_dd,
            "best_trade":   best,
            "worst_trade":  worst,
            "equity_curve": equity[-60:],  # last 60 points
            "trades":       trades[-20:],  # last 20 trades
        }

    except Exception as e:
        return {"error": str(e)}


def _score(row, prev) -> int:
    score = 0
    rsi = float(row["rsi"]) if row["rsi"] == row["rsi"] else 50
    macd = float(row["macd"]) if row["macd"] == row["macd"] else 0
    macd_sig = float(row["macd_signal"]) if row["macd_signal"] == row["macd_signal"] else 0
    prev_macd = float(prev["macd"]) if prev["macd"] == prev["macd"] else 0
    prev_sig  = float(prev["macd_signal"]) if prev["macd_signal"] == prev["macd_signal"] else 0
    price     = float(row["Close"])
    sma20     = float(row["sma_20"]) if row["sma_20"] == row["sma_20"] else price

    if rsi < 35: score += 2
    elif rsi < 42: score += 1
    elif rsi > 68: score -= 2

    if macd > macd_sig and prev_macd <= prev_sig: score += 2
    elif macd > macd_sig: score += 1
    else: score -= 1

    if price > sma20: score += 1
    return score


def _max_drawdown(equity: list) -> float:
    if not equity: return 0
    peak = equity[0]
    max_dd = 0
    for v in equity:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100 if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    return round(max_dd, 2)
