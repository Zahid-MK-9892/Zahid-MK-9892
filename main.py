"""
main.py — FRIDAY: AI Swing Trading Bot
Entry point. Runs the scan loop on a schedule.

Usage:
    python main.py              # Run once immediately
    python main.py --loop       # Run on schedule (every N minutes per config)
    python main.py --summary    # Show performance summary
"""

import sys
import time
import schedule
from datetime import datetime
from colorama import Fore, Style, init as colorama_init

import config
from data.market_data import get_stock_data, get_crypto_data
from data.news_fetcher import get_news, format_news_for_prompt
from analysis.ai_engine import analyze_asset
from trading.risk_manager import approve_trade, calculate_position
from trading.executor import execute_trade
from trading.journal import (
    init_db, log_scan, log_trade,
    get_open_positions, get_performance_summary
)

colorama_init(autoreset=True)


def banner():
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════╗
║   F.R.I.D.A.Y  —  AI Swing Trading Bot      ║
║   Mode: {'MOCK SIMULATION' if config.MOCK_MODE else 'PAPER TRADING'}                     ║
╚══════════════════════════════════════════════╝{Style.RESET_ALL}
""")


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    colors = {"INFO": Fore.WHITE, "BUY": Fore.GREEN, "HOLD": Fore.YELLOW,
              "SKIP": Fore.YELLOW, "ERROR": Fore.RED, "TRADE": Fore.CYAN}
    color = colors.get(level, Fore.WHITE)
    print(f"{Fore.LIGHTBLACK_EX}[{ts}]{Style.RESET_ALL} {color}[{level}]{Style.RESET_ALL} {msg}")


def scan_asset(ticker: str):
    """Run a full analysis cycle on a single asset."""
    log(f"Scanning {ticker}...", "INFO")

    # ── 1. Fetch market data ───────────────────────────────────────────────────
    is_crypto = "/" in ticker or "-USD" in ticker.upper()
    market_data = get_crypto_data(ticker) if is_crypto else get_stock_data(ticker)

    if "error" in market_data:
        log(f"{ticker} data error: {market_data['error']}", "ERROR")
        return

    price = market_data.get("price", 0)
    rsi   = market_data.get("rsi", "N/A")
    log(f"{ticker} | Price: ${price} | RSI: {rsi}", "INFO")

    # ── 2. Fetch news ──────────────────────────────────────────────────────────
    articles   = get_news(ticker)
    news_text  = format_news_for_prompt(articles)

    # ── 3. AI analysis ────────────────────────────────────────────────────────
    analysis = analyze_asset(ticker, market_data, news_text)
    action   = analysis.get("action", "HOLD")
    conf     = analysis.get("confidence", 0)
    reason   = analysis.get("reasoning", "")

    # Log every scan to the journal
    log_scan(ticker, price, analysis)

    level = action if action in ("BUY", "HOLD") else "INFO"
    log(f"{ticker} → {action} (confidence: {conf}%) | {reason[:80]}...", level)

    if analysis.get("key_signals"):
        log(f"  Signals: {' · '.join(analysis['key_signals'])}", "INFO")

    # ── 4. Risk check ─────────────────────────────────────────────────────────
    open_positions = get_open_positions()
    approved, reason_str = approve_trade(analysis, market_data, open_positions)

    if not approved:
        log(f"{ticker} trade skipped: {reason_str}", "SKIP")
        return

    # ── 5. Calculate position size ────────────────────────────────────────────
    position = calculate_position(price, analysis)
    log(f"{ticker} position: {position['shares']} shares @ ${price} | "
        f"SL: ${position['stop_loss']} | TP: ${position['take_profit']} | "
        f"R/R: {position['risk_reward_ratio']}x", "TRADE")

    # ── 6. Execute trade ──────────────────────────────────────────────────────
    order = execute_trade(ticker, position)

    if order["status"] in ("SUBMITTED", "MOCK_SUBMITTED"):
        log(f"ORDER PLACED ✓ | {ticker} | ID: {order['order_id']} | "
            f"Cost: ${position['total_cost']}", "BUY")
        log_trade(order, analysis)
    else:
        log(f"Order failed for {ticker}: {order.get('error')}", "ERROR")


def run_scan_cycle():
    """Full scan cycle across all watchlisted assets."""
    print()
    log(f"Starting scan cycle — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
    log(f"Open positions: {len(get_open_positions())}", "INFO")

    for ticker in config.STOCK_WATCHLIST:
        scan_asset(ticker)

    for ticker in config.CRYPTO_WATCHLIST:
        scan_asset(ticker)

    log("Scan cycle complete.\n", "INFO")


def show_summary():
    """Print performance summary from the journal."""
    summary = get_performance_summary()
    print(f"\n{Fore.CYAN}── FRIDAY Performance Summary ──{Style.RESET_ALL}")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    open_pos = get_open_positions()
    print(f"\n{Fore.CYAN}── Open Positions ({len(open_pos)}) ──{Style.RESET_ALL}")
    for p in open_pos:
        print(f"  {p['ticker']} | {p['shares']} shares @ ${p['entry_price']} "
              f"| SL: ${p['stop_loss']} | TP: ${p['take_profit']}")
    print()


def main():
    banner()
    init_db()

    args = sys.argv[1:]

    if "--summary" in args:
        show_summary()
        return

    if "--loop" in args:
        log(f"FRIDAY is live. Scanning every {config.SCAN_INTERVAL_MINUTES} minutes.", "INFO")
        run_scan_cycle()  # Run immediately on start
        schedule.every(config.SCAN_INTERVAL_MINUTES).minutes.do(run_scan_cycle)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        # Single run
        run_scan_cycle()
        show_summary()


if __name__ == "__main__":
    main()
