"""
main.py — FRIDAY: AI Swing Trading Bot
Entry point. Runs the scan loop on a schedule.

Usage:
    python main.py              # Run once immediately
    python main.py --loop       # Run every N minutes (set in config.py)
    python main.py --summary    # Show performance summary
"""

import sys
import time
import schedule
from datetime import datetime

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    USE_COLOR = True
except ImportError:
    USE_COLOR = False

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


def c(text, color):
    if not USE_COLOR:
        return text
    colors = {
        "cyan":   Fore.CYAN,   "green":  Fore.GREEN,
        "yellow": Fore.YELLOW, "red":    Fore.RED,
        "white":  Fore.WHITE,  "dim":    Fore.LIGHTBLACK_EX,
        "blue":   Fore.BLUE,
    }
    return f"{colors.get(color,'')}{text}{Style.RESET_ALL}"


def banner():
    mode = "MOCK SIMULATION" if config.MOCK_MODE else "PAPER TRADING"
    print(f"""
{c('╔══════════════════════════════════════════════╗', 'cyan')}
{c('║   F.R.I.D.A.Y  —  AI Swing Trading Bot      ║', 'cyan')}
{c(f'║   Mode: {mode:<37}║', 'cyan')}
{c('╚══════════════════════════════════════════════╝', 'cyan')}
""")


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    level_colors = {
        "INFO":  "white",  "BUY":   "green",
        "HOLD":  "yellow", "SKIP":  "yellow",
        "ERROR": "red",    "TRADE": "cyan",
        "WARN":  "yellow",
    }
    col = level_colors.get(level, "white")
    print(f"{c(f'[{ts}]', 'dim')} {c(f'[{level}]', col)} {msg}")


def scan_asset(ticker: str):
    """Full analysis + trade cycle for one asset."""
    log(f"Scanning {ticker}...", "INFO")

    # 1. Market data
    is_crypto   = "/" in ticker or ticker.endswith("-USD")
    market_data = get_crypto_data(ticker) if is_crypto else get_stock_data(ticker)

    if "error" in market_data:
        log(f"{ticker} data error: {market_data['error']}", "ERROR")
        return

    price = market_data.get("price", 0)
    rsi   = market_data.get("rsi", "N/A")
    log(f"{ticker} | Price: ${price} | RSI: {rsi}", "INFO")

    # 2. News
    articles  = get_news(ticker)
    news_text = format_news_for_prompt(articles)

    # 3. AI / rule-based analysis
    analysis = analyze_asset(ticker, market_data, news_text)
    action   = analysis.get("action", "HOLD")
    conf     = analysis.get("confidence", 0)
    source   = analysis.get("source", "unknown")
    reason   = analysis.get("reasoning", "")
    source_label = "Claude AI" if source == "claude_ai" else "Rule-based"

    log_scan(ticker, price, analysis)

    level = "BUY" if action == "BUY" else ("HOLD" if action == "HOLD" else "INFO")
    log(f"{ticker} → {action} (conf: {conf}% | {source_label}) | {reason[:75]}...", level)

    if analysis.get("key_signals"):
        log(f"  Signals: {' · '.join(analysis['key_signals'])}", "INFO")

    # 4. Risk check
    open_positions = get_open_positions()
    approved, reason_str = approve_trade(analysis, market_data, open_positions)

    if not approved:
        log(f"{ticker} skipped: {reason_str}", "SKIP")
        return

    # 5. Position sizing
    position = calculate_position(price, analysis)
    log(
        f"{ticker} → {position['shares']} shares @ ${price} | "
        f"SL: ${position['stop_loss']} | TP: ${position['take_profit']} | "
        f"R/R: {position['risk_reward_ratio']}x",
        "TRADE"
    )

    # 6. Execute
    order = execute_trade(ticker, position)

    if order.get("status") in ("SUBMITTED", "MOCK_SUBMITTED"):
        log(
            f"ORDER PLACED ✓ | {ticker} | ID: {order['order_id']} | "
            f"Cost: ${position['total_cost']}",
            "BUY"
        )
        log_trade(order, analysis)
    else:
        log(f"Order failed for {ticker}: {order.get('error', 'unknown error')}", "ERROR")


def run_scan_cycle():
    """Full scan across all watchlisted assets."""
    print()
    log(f"Scan cycle started — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
    log(f"Open positions: {len(get_open_positions())}", "INFO")

    for ticker in config.STOCK_WATCHLIST:
        try:
            scan_asset(ticker)
        except Exception as e:
            log(f"Unexpected error scanning {ticker}: {e}", "ERROR")

    for ticker in config.CRYPTO_WATCHLIST:
        try:
            scan_asset(ticker)
        except Exception as e:
            log(f"Unexpected error scanning {ticker}: {e}", "ERROR")

    log("Scan cycle complete.", "INFO")


def show_summary():
    summary     = get_performance_summary()
    open_pos    = get_open_positions()

    print(f"\n{c('── FRIDAY Performance Summary ──', 'cyan')}")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print(f"\n{c(f'── Open Positions ({len(open_pos)}) ──', 'cyan')}")
    if open_pos:
        for p in open_pos:
            print(
                f"  {p['ticker']} | {p['shares']} shares @ ${p['entry_price']} "
                f"| SL: ${p['stop_loss']} | TP: ${p['take_profit']} | {p['broker']}"
            )
    else:
        print("  No open positions.")
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
        run_scan_cycle()
        schedule.every(config.SCAN_INTERVAL_MINUTES).minutes.do(run_scan_cycle)
        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run_scan_cycle()
        show_summary()


if __name__ == "__main__":
    main()
