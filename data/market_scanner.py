"""
data/market_scanner.py — Full market scanner.

WEEK 1 (already shipped):
  + is_stock_market_open()  — NYSE/NASDAQ hours check
  + get_market_regime()     — SPY weekly SMA50 regime filter

WEEK 2 (new):
  + get_open_exchanges()    — all 4 exchanges: NYSE, NSE/BSE, LSE, HKEX
  + get_india_tickers()     — 30 liquid NSE/BSE stocks (.NS suffix)
  + get_lse_tickers()       — 20 liquid LSE stocks (.L suffix)
  + get_hkex_tickers()      — 12 liquid HKEX stocks (.HK suffix)
  + has_upcoming_earnings() — free yfinance earnings blackout (no API key)
  + select_trades()         — now includes earnings blackout filter
  + run_market_scan()       — now scans all open exchanges each cycle
"""

import pandas as pd
import yfinance as yf
import time
from datetime import datetime, date
from zoneinfo import ZoneInfo


# ══════════════════════════════════════════════════════════════════
#  WEEK 1 — MARKET HOURS (NYSE only, kept for main.py backward compat)
# ══════════════════════════════════════════════════════════════════

def is_stock_market_open() -> tuple[bool, str]:
    """
    NYSE/NASDAQ check. Monday–Friday 09:30–16:00 EST.
    Kept for backward compatibility with main.py.
    """
    est  = ZoneInfo("America/New_York")
    now  = datetime.now(est)
    day  = now.weekday()
    mins = now.hour * 60 + now.minute
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    if day >= 5:
        return False, f"Weekend ({days[day]}) — NYSE closed"
    if mins < 9*60+30:
        opens_in = (9*60+30) - mins
        return False, f"Pre-market — NYSE opens in {opens_in//60}h {opens_in%60}m (09:30 EST)"
    if mins >= 16*60:
        return False, f"After-hours — NYSE closed for today. Reopens tomorrow 09:30 EST"
    return True, f"NYSE open — {days[day]} {now.strftime('%H:%M')} EST"


# ══════════════════════════════════════════════════════════════════
#  WEEK 2 — UPGRADE 1: ALL EXCHANGE HOURS
# ══════════════════════════════════════════════════════════════════

def get_open_exchanges() -> dict:
    """
    Returns open/closed status for all 4 supported exchanges.
    Crypto is always open and handled separately.

    Returns dict: { exchange_name: {"open": bool, "msg": str} }
    """
    result = {}

    # ── NYSE / NASDAQ  (EST, Mon-Fri 09:30–16:00) ─────────────────
    est  = ZoneInfo("America/New_York")
    now  = datetime.now(est)
    day  = now.weekday()
    mins = now.hour * 60 + now.minute
    nyse_open = day < 5 and (9*60+30) <= mins < 16*60
    result["NYSE/NASDAQ"] = {
        "open":   nyse_open,
        "suffix": "",
        "msg":    f"{'OPEN' if nyse_open else 'CLOSED'} ({now.strftime('%H:%M')} EST)",
    }

    # ── NSE / BSE  (IST, Mon-Fri 09:15–15:30) ────────────────────
    ist  = ZoneInfo("Asia/Kolkata")
    now  = datetime.now(ist)
    day  = now.weekday()
    mins = now.hour * 60 + now.minute
    nse_open = day < 5 and (9*60+15) <= mins < (15*60+30)
    result["NSE/BSE"] = {
        "open":   nse_open,
        "suffix": ".NS",
        "msg":    f"{'OPEN' if nse_open else 'CLOSED'} ({now.strftime('%H:%M')} IST)",
    }

    # ── LSE  (GMT/BST, Mon-Fri 08:00–16:30) ──────────────────────
    gmt  = ZoneInfo("Europe/London")
    now  = datetime.now(gmt)
    day  = now.weekday()
    mins = now.hour * 60 + now.minute
    lse_open = day < 5 and (8*60) <= mins < (16*60+30)
    result["LSE"] = {
        "open":   lse_open,
        "suffix": ".L",
        "msg":    f"{'OPEN' if lse_open else 'CLOSED'} ({now.strftime('%H:%M')} {now.strftime('%Z')})",
    }

    # ── HKEX  (HKT, Mon-Fri 09:30–16:00, lunch break 12:00–13:00) ─
    hkt  = ZoneInfo("Asia/Hong_Kong")
    now  = datetime.now(hkt)
    day  = now.weekday()
    mins = now.hour * 60 + now.minute
    morning   = (9*60+30) <= mins < 12*60
    afternoon = (13*60)   <= mins < 16*60
    hkex_open = day < 5 and (morning or afternoon)
    result["HKEX"] = {
        "open":   hkex_open,
        "suffix": ".HK",
        "msg":    f"{'OPEN' if hkex_open else 'CLOSED'} ({now.strftime('%H:%M')} HKT)",
    }

    return result


# ══════════════════════════════════════════════════════════════════
#  WEEK 2 — UPGRADE 2: EARNINGS BLACKOUT (free, no API key)
# ══════════════════════════════════════════════════════════════════

def has_upcoming_earnings(ticker: str, days: int = 3) -> bool:
    """
    Returns True if ticker has earnings within the next N days.
    Uses yfinance .calendar — completely free, no API key needed.
    Returns False (safe default = allow trade) if check fails.
    Crypto tickers are automatically skipped.
    """
    # Skip crypto — they have no earnings reports
    if ticker.endswith("-USD") or "/" in ticker:
        return False

    try:
        t   = yf.Ticker(ticker)
        cal = t.calendar

        if cal is None:
            return False

        today = date.today()

        # ── Handle dict format (yfinance 0.2.x+) ─────────────────
        if isinstance(cal, dict):
            earnings_list = cal.get("Earnings Date", [])
            if not earnings_list:
                return False
            for ed in (earnings_list if isinstance(earnings_list, list) else [earnings_list]):
                try:
                    ed_date   = ed.date() if hasattr(ed, "date") else pd.Timestamp(ed).date()
                    days_until = (ed_date - today).days
                    if 0 <= days_until <= days:
                        return True
                except Exception:
                    continue
            return False

        # ── Handle DataFrame format (older yfinance) ──────────────
        if hasattr(cal, "loc"):
            try:
                ed        = cal.loc["Earnings Date"].iloc[0]
                ed_date   = ed.date() if hasattr(ed, "date") else pd.Timestamp(ed).date()
                days_until = (ed_date - today).days
                return 0 <= days_until <= days
            except Exception:
                return False

        return False

    except Exception:
        # Fail open — never block a trade just because the check errored
        return False


# ══════════════════════════════════════════════════════════════════
#  STOCK UNIVERSES
# ══════════════════════════════════════════════════════════════════

def get_sp500_tickers() -> list:
    """Fetch S&P 500 tickers. Tries Wikipedia then curated fallback."""
    try:
        tables  = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            flavor="html5lib"
        )
        tickers = [t.replace(".", "-") for t in tables[0]["Symbol"].tolist()]
        print(f"[SCANNER] Loaded {len(tickers)} S&P 500 tickers from Wikipedia")
        return tickers
    except Exception:
        pass
    try:
        tables  = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        tickers = [t.replace(".", "-") for t in tables[0]["Symbol"].tolist()]
        print(f"[SCANNER] Loaded {len(tickers)} tickers (alternate parser)")
        return tickers
    except Exception as e:
        print(f"[SCANNER] Wikipedia blocked ({e}). Using curated fallback list.")
        return _sp500_fallback()


def get_india_tickers() -> list:
    """Top 30 liquid NSE/BSE stocks. yfinance uses .NS suffix."""
    return [
        # Banking & Finance
        "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "KOTAKBANK.NS",
        "AXISBANK.NS", "BAJFINANCE.NS",
        # Technology
        "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS",
        # Energy & Industrial
        "RELIANCE.NS", "ONGC.NS", "COALINDIA.NS", "NTPC.NS",
        "POWERGRID.NS", "LT.NS", "JSWSTEEL.NS",
        # Consumer & FMCG
        "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "ASIANPAINT.NS",
        "MARUTI.NS", "TITAN.NS",
        # Healthcare
        "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS",
        # Telecom
        "BHARTIARTL.NS",
        # Other large caps
        "TATAMOTORS.NS", "ULTRACEMCO.NS",
    ]


def get_lse_tickers() -> list:
    """Top 20 liquid London Stock Exchange stocks. yfinance uses .L suffix."""
    return [
        # Energy
        "SHEL.L", "BP.L",
        # Healthcare
        "AZN.L", "GSK.L",
        # Finance
        "HSBA.L", "BARC.L", "LLOY.L", "STAN.L",
        # Consumer
        "ULVR.L", "DGE.L", "ABF.L",
        # Mining / Industrial
        "RIO.L", "AAL.L",
        # Telecom
        "VOD.L", "BT-A.L",
        # Utilities
        "NG.L",
        # Other
        "REL.L", "CPG.L", "EXPN.L", "IMB.L",
    ]


def get_hkex_tickers() -> list:
    """Top 12 liquid Hong Kong Exchange stocks. yfinance uses .HK suffix."""
    return [
        "0700.HK",   # Tencent
        "9988.HK",   # Alibaba
        "0005.HK",   # HSBC
        "0941.HK",   # China Mobile
        "1299.HK",   # AIA Group
        "0388.HK",   # HKEX
        "2318.HK",   # Ping An Insurance
        "1810.HK",   # Xiaomi
        "3690.HK",   # Meituan
        "0883.HK",   # CNOOC
        "1398.HK",   # ICBC
        "0939.HK",   # China Construction Bank
    ]


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
        "AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AVGO","ORCL","ADBE",
        "CRM","AMD","INTC","QCOM","TXN","IBM","INTU","NOW","SNOW","PLTR",
        "PANW","CRWD","DDOG","NET","ZS","MDB","GTLB","RBLX","COIN",
        "JPM","BAC","WFC","GS","MS","C","BLK","AXP","V","MA","SPGI","MCO",
        "UNH","JNJ","LLY","ABBV","MRK","PFE","AMGN","GILD","VRTX","REGN",
        "ISRG","MDT","BSX","ELV","CI","HUM","CVS","ZTS","DXCM",
        "AMZN","HD","MCD","SBUX","NKE","TGT","COST","WMT","PG","KO",
        "PEP","PM","MO","MNST","CMG","YUM","DPZ",
        "XOM","CVX","SLB","EOG","COP","PLD","AMT","EQIX","PSA",
        "HON","CAT","DE","RTX","GE","ETN","EMR","ITW","NSC","UPS","FDX",
        "BRK-B","ACN","TMO","DHR","LIN","MMM","NEE","SO","DUK",
        "CB","AON","ADP","CME","ICE","MSCI",
    ]


# ══════════════════════════════════════════════════════════════════
#  WEEK 1 — MARKET REGIME (unchanged)
# ══════════════════════════════════════════════════════════════════

def get_market_regime() -> dict:
    """
    BULL / BEAR regime based on SPY weekly vs 50-week SMA.
    """
    try:
        df = yf.download("SPY", period="2y", interval="1wk",
                         progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 52:
            return {"regime": "UNKNOWN", "message": "Not enough SPY data for regime check"}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close        = df["Close"].squeeze()
        sma50        = close.rolling(50).mean()
        spy_price    = float(close.iloc[-1])
        sma50_weekly = float(sma50.iloc[-1])
        pct_above    = round(((spy_price - sma50_weekly) / sma50_weekly) * 100, 2)

        if spy_price > sma50_weekly:
            regime  = "BULL"
            message = (f"BULL market — SPY ${spy_price:.2f} is {pct_above:+.1f}% "
                       f"above weekly SMA50 (${sma50_weekly:.2f}). Normal trading mode.")
        else:
            regime  = "BEAR"
            message = (f"BEAR market — SPY ${spy_price:.2f} is {pct_above:+.1f}% "
                       f"below weekly SMA50 (${sma50_weekly:.2f}). "
                       f"Raising score threshold and reducing new trades.")

        return {"regime": regime, "spy_price": spy_price,
                "sma50_weekly": sma50_weekly, "pct_above": pct_above, "message": message}

    except Exception as e:
        return {"regime": "UNKNOWN", "message": f"Regime check failed: {e}"}


# ══════════════════════════════════════════════════════════════════
#  PHASE 1: QUICK SCREEN  (unchanged)
# ══════════════════════════════════════════════════════════════════

def quick_screen(tickers: list,
                 min_price: float = 5.0,
                 min_volume: int = 500_000,
                 max_candidates: int = 60) -> list:
    print(f"[SCANNER] Screening {len(tickers)} tickers (individual mode)...")
    candidates = []
    failed     = 0

    for i, ticker in enumerate(tickers, 1):
        try:
            df = yf.download(ticker, period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            if df is None or df.empty:
                failed += 1; continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.dropna()
            if len(df) < 2:
                failed += 1; continue

            close   = df["Close"].squeeze()
            vol     = df["Volume"].squeeze()
            price   = float(close.iloc[-1])
            volume  = float(vol.iloc[-1])
            prev    = float(close.iloc[-2])
            change  = round(((price - prev) / prev) * 100, 2) if prev else 0
            avg_vol = float(vol.mean())

            if price < min_price or avg_vol < min_volume:
                continue

            candidates.append({
                "ticker":  ticker,
                "price":   round(price, 4),
                "volume":  int(volume),
                "avg_vol": int(avg_vol),
                "change":  change,
            })

            if i % 20 == 0:
                print(f"[SCANNER] Screened {i}/{len(tickers)} — {len(candidates)} passing so far...")

            if len(candidates) >= max_candidates * 2:
                break

        except Exception:
            failed += 1; continue

    candidates.sort(key=lambda x: x["avg_vol"], reverse=True)
    result = candidates[:max_candidates]
    print(f"[SCANNER] Screen complete: {len(result)} candidates ({failed} failed/skipped)")
    return result


# ══════════════════════════════════════════════════════════════════
#  PHASE 2: DEEP ANALYSIS  (unchanged)
# ══════════════════════════════════════════════════════════════════

def deep_scan(candidates: list) -> list:
    from data.market_data import get_stock_data, get_crypto_data
    from analysis.ai_engine import _rule_based

    scored = []
    total  = len(candidates)

    for i, c in enumerate(candidates, 1):
        ticker = c["ticker"]
        try:
            is_crypto = ticker.endswith("-USD")
            md        = get_crypto_data(ticker) if is_crypto else get_stock_data(ticker)

            if "error" in md or not md.get("price"):
                continue

            analysis = _rule_based(ticker, md)
            scored.append({
                **c, **md,
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
            print(f"[SCANNER] Error on {ticker}: {e}"); continue

    scored.sort(key=lambda x: (x["action"] == "BUY", x["score"]), reverse=True)
    return scored


# ══════════════════════════════════════════════════════════════════
#  PHASE 3: SELECT TRADES  (+ Week 2 earnings blackout filter)
# ══════════════════════════════════════════════════════════════════

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

        # ── WEEK 2: Earnings blackout check ───────────────────────
        ticker = item["ticker"]
        if has_upcoming_earnings(ticker, days=3):
            print(f"[SCANNER] {ticker} skipped — earnings within 3 days")
            continue

        selected.append(item)

    print(f"[SCANNER] Selected {len(selected)} trade(s) from universe")
    return selected


# ══════════════════════════════════════════════════════════════════
#  FULL PIPELINE  (Week 1 + Week 2 combined)
# ══════════════════════════════════════════════════════════════════

def run_market_scan(open_positions: list,
                    include_crypto: bool = True,
                    max_candidates: int = 60,
                    max_new_trades: int = 3) -> list:

    print(f"\n[SCANNER] ═══ Starting full market scan ═══")
    print(f"[SCANNER] Open positions: {len(open_positions)}")

    # ── Week 2: Check all exchanges ───────────────────────────────
    exchanges = get_open_exchanges()
    for name, info in exchanges.items():
        print(f"[SCANNER] {name:<15} {info['msg']}")

    # ── Week 1: Market regime ─────────────────────────────────────
    regime_data = get_market_regime()
    regime      = regime_data.get("regime", "UNKNOWN")
    print(f"[SCANNER] Regime: {regime_data['message']}")

    # Adjust thresholds in bear market
    if regime == "BEAR":
        min_score      = 4
        max_new_trades = max(1, max_new_trades - 1)
        print(f"[SCANNER] ⚠ BEAR mode: min_score={min_score}, max_new_trades={max_new_trades}")
    else:
        min_score = 3

    # ── Build universe from open exchanges ────────────────────────
    universe = []

    if exchanges["NYSE/NASDAQ"]["open"]:
        sp500 = get_sp500_tickers()
        universe += sp500
        print(f"[SCANNER] NYSE/NASDAQ: +{len(sp500)} S&P 500 stocks")
    else:
        print(f"[SCANNER] NYSE/NASDAQ: closed — skipping US stocks")

    if exchanges["NSE/BSE"]["open"]:
        india = get_india_tickers()
        universe += india
        print(f"[SCANNER] NSE/BSE    : +{len(india)} Indian stocks")
    else:
        print(f"[SCANNER] NSE/BSE    : closed — skipping Indian stocks")

    if exchanges["LSE"]["open"]:
        lse = get_lse_tickers()
        universe += lse
        print(f"[SCANNER] LSE        : +{len(lse)} UK stocks")
    else:
        print(f"[SCANNER] LSE        : closed — skipping UK stocks")

    if exchanges["HKEX"]["open"]:
        hk = get_hkex_tickers()
        universe += hk
        print(f"[SCANNER] HKEX       : +{len(hk)} HK stocks")
    else:
        print(f"[SCANNER] HKEX       : closed — skipping HK stocks")

    crypto = get_crypto_universe() if include_crypto else []
    universe += crypto
    print(f"[SCANNER] Crypto      : +{len(crypto)} pairs (always active)")

    if not universe:
        print("[SCANNER] All exchanges closed and no crypto. Nothing to scan.")
        return []

    # Remove duplicates while preserving order
    seen = set()
    universe = [t for t in universe if not (t in seen or seen.add(t))]
    print(f"[SCANNER] Total universe: {len(universe)} assets")

    # ── Screen ────────────────────────────────────────────────────
    candidates = quick_screen(universe, max_candidates=max_candidates)
    if not candidates:
        print("[SCANNER] No candidates passed screen")
        return []

    # ── Deep analyse ──────────────────────────────────────────────
    scored = deep_scan(candidates)
    if not scored:
        print("[SCANNER] No assets scored")
        return []

    # Show top 5
    print(f"\n[SCANNER] ─── Top opportunities ───")
    for item in scored[:5]:
        print(f"  {item['ticker']:<12} Score:{item['score']:+d}  "
              f"Conf:{item['confidence']}%  {item['action']}  "
              f"RSI:{item.get('rsi','?')}  {item['sentiment']}")

    return select_trades(
        scored, open_positions,
        max_new_trades=max_new_trades,
        min_score=min_score,
    )
