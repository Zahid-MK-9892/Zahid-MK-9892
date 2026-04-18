"""
data/market_scanner.py — Full market scanner.
Fixed: individual ticker downloads instead of buggy batch mode.
Fixed: removed dead tickers, cleaner fallback list.
"""

import pandas as pd
import yfinance as yf
import time


# ── Stock Universe ─────────────────────────────────────────────────────────────

def get_sp500_tickers() -> list:
    """Fetch S&P 500 tickers. Tries multiple sources before fallback."""
    # Try Wikipedia
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            flavor="html5lib"
        )
        tickers = tables[0]["Symbol"].tolist()
        tickers = [t.replace(".", "-") for t in tickers]
        print(f"[SCANNER] Loaded {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers
    except Exception:
        pass

    # Try alternate flavor
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        )
        tickers = tables[0]["Symbol"].tolist()
        tickers = [t.replace(".", "-") for t in tickers]
        print(f"[SCANNER] Loaded {len(tickers)} tickers (alternate parser)")
        return tickers
    except Exception as e:
        print(f"[SCANNER] Wikipedia blocked ({e}). Using curated fallback list.")
        return _sp500_fallback()


def get_crypto_universe() -> list:
    """Top crypto pairs available on Yahoo Finance."""
    return [
        "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD",
        "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD",
        "XRP-USD", "LTC-USD", "BCH-USD", "ALGO-USD",
    ]


def _sp500_fallback() -> list:
    """Curated list of the most liquid S&P 500 stocks — verified active."""
    return [
        # Mega cap tech
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","ORCL","ADBE",
        "CRM","AMD","INTC","QCOM","TXN","IBM","INTU","NOW","SNOW","PLTR",
        "PANW","CRWD","DDOG","NET","ZS","MDB","GTLB","RBLX","COIN",
        # Finance
        "JPM","BAC","WFC","GS","MS","C","BLK","AXP","V","MA","SPGI","MCO",
        # Healthcare
        "UNH","JNJ","LLY","ABBV","MRK","PFE","AMGN","GILD","VRTX","REGN",
        "ISRG","MDT","BSX","ELV","CI","HUM","CVS","ZTS","DXCM",
        # Consumer
        "AMZN","HD","MCD","SBUX","NKE","TGT","COST","WMT","PG","KO",
        "PEP","PM","MO","MNST","CMG","YUM","DPZ",
        # Industrial / Energy
        "XOM","CVX","SLB","EOG","COP","PLD","AMT","EQIX","PSA",
        "HON","CAT","DE","RTX","GE","ETN","EMR","ITW","NSC","UPS","FDX",
        # Other quality
        "BRK-B","ACN","TMO","DHR","LIN","MMM","NEE","SO","DUK",
        "CB","AON","ADP","CME","ICE","MSCI",
    ]


# ── Phase 1: Individual ticker screening ───────────────────────────────────────

def quick_screen(tickers: list,
                 min_price: float = 5.0,
                 min_volume: int = 500_000,
                 max_candidates: int = 60) -> list:
    """
    Downloads each ticker individually to avoid batch TypeError bugs.
    Filters by price and volume. Returns top candidates sorted by volume.
    """
    print(f"[SCANNER] Screening {len(tickers)} tickers (individual mode)...")
    candidates = []
    failed     = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = yf.download(
                ticker, period="5d", interval="1d",
                progress=False, auto_adjust=True
            )
            if df is None or df.empty:
                failed += 1
                continue

            # Flatten MultiIndex if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.dropna()
            if len(df) < 2:
                failed += 1
                continue

            close  = df["Close"].squeeze()
            vol    = df["Volume"].squeeze()
            price  = float(close.iloc[-1])
            volume = float(vol.iloc[-1])
            prev   = float(close.iloc[-2])
            change = round(((price - prev) / prev) * 100, 2) if prev else 0
            avg_vol= float(vol.mean())

            if price < min_price or avg_vol < min_volume:
                continue

            candidates.append({
                "ticker":  ticker,
                "price":   round(price, 4),
                "volume":  int(volume),
                "avg_vol": int(avg_vol),
                "change":  change,
            })

            # Progress every 20 tickers
            if i % 20 == 0:
                print(f"[SCANNER] Screened {i}/{len(tickers)} — {len(candidates)} passing so far...")

            # Stop early once we have enough good candidates
            if len(candidates) >= max_candidates * 2:
                break

        except Exception:
            failed += 1
            continue

    candidates.sort(key=lambda x: x["avg_vol"], reverse=True)
    result = candidates[:max_candidates]
    print(f"[SCANNER] Screen complete: {len(result)} candidates ({failed} failed/skipped)")
    return result


# ── Phase 2: Deep Technical Analysis ──────────────────────────────────────────

def deep_scan(candidates: list) -> list:
    """
    Runs full technical analysis on each screened candidate.
    Returns scored list sorted by conviction.
    """
    from data.market_data import get_stock_data, get_crypto_data
    from analysis.ai_engine import _rule_based

    scored = []
    total  = len(candidates)

    for i, c in enumerate(candidates, 1):
        ticker = c["ticker"]
        try:
            is_crypto = ticker.endswith("-USD")
            md = get_crypto_data(ticker) if is_crypto else get_stock_data(ticker)

            if "error" in md or not md.get("price"):
                continue

            analysis = _rule_based(ticker, md)
            scored.append({
                **c,
                **md,
                "analysis":   analysis,
                "score":      analysis.get("score", 0),
                "action":     analysis.get("action", "HOLD"),
                "confidence": analysis.get("confidence", 0),
                "sentiment":  analysis.get("sentiment", "NEUTRAL"),
                "signals":    analysis.get("key_signals", []),
                "sl":         analysis.get("suggested_stop_loss"),
                "tp":         analysis.get("suggested_take_profit"),
            })

            if i % 10 == 0:
                print(f"[SCANNER] Analysed {i}/{total}...")

        except Exception as e:
            print(f"[SCANNER] Error on {ticker}: {e}")
            continue

    scored.sort(key=lambda x: (x["action"] == "BUY", x["score"]), reverse=True)
    return scored


# ── Phase 3: Select Best Trades ────────────────────────────────────────────────

def select_trades(scored: list, open_positions: list,
                  max_new_trades: int = 3,
                  min_score: int = 3,
                  min_confidence: int = 62) -> list:
    open_tickers = {p.get("ticker", "") for p in open_positions}
    selected     = []

    for item in scored:
        if len(selected) >= max_new_trades:
            break
        if item["action"] != "BUY":
            break
        if item["ticker"] in open_tickers:
            continue
        if item["score"] < min_score:
            continue
        if item["confidence"] < min_confidence:
            continue
        selected.append(item)

    print(f"[SCANNER] Selected {len(selected)} trade(s) from universe")
    return selected


# ── Full Pipeline ──────────────────────────────────────────────────────────────

def run_market_scan(open_positions: list,
                    include_crypto: bool = True,
                    max_candidates: int = 60,
                    max_new_trades: int = 3) -> list:
    print(f"\n[SCANNER] ═══ Starting full market scan ═══")
    print(f"[SCANNER] Open positions: {len(open_positions)}")

    stocks   = get_sp500_tickers()
    crypto   = get_crypto_universe() if include_crypto else []
    universe = stocks + crypto
    print(f"[SCANNER] Universe: {len(stocks)} stocks + {len(crypto)} crypto = {len(universe)} total")

    candidates = quick_screen(universe, max_candidates=max_candidates)
    if not candidates:
        print("[SCANNER] No candidates passed screen")
        return []

    scored = deep_scan(candidates)
    if not scored:
        print("[SCANNER] No assets scored")
        return []

    # Show top 5
    print(f"\n[SCANNER] ─── Top opportunities ───")
    for item in scored[:5]:
        print(f"  {item['ticker']:<10} Score:{item['score']:+d}  "
              f"Conf:{item['confidence']}%  {item['action']}  "
              f"RSI:{item.get('rsi','?')}  {item['sentiment']}")

    return select_trades(scored, open_positions, max_new_trades=max_new_trades)
