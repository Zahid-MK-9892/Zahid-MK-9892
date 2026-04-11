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
from trading.position_manager import check_and_close_positions
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
        "INFO":  "white",  "BUY":    "green",
        "HOLD":  "yellow", "SKIP":   "yellow",
        "ERROR": "red",    "TRADE":  "cyan",
        "CLOSE": "cyan",   "WIN":    "green",
        "LOSS":  "red",
    }
    col = level_colors.get(level, "white")
    print(f"{c(f'[{ts}]', 'dim')} {c(f'[{level}]', col)} {msg}")


def check_exits():
    """
    Step 1 of every scan cycle.
    Automatically closes positions that hit stop-loss or take-profit.
    """
    log("Checking open positions for exits...", "INFO")
    closed = check_and_close_positions()

    if not closed:
        log("No exits triggered.", "INFO")
        return

    for c_pos in closed:
        ticker = c_pos["ticker"]
        reason = c_pos["exit_reason"]
        pnl    = c_pos["pnl"]
        outcome= c_pos["outcome"]
        entry  = c_pos["entry"]
        exit_p = c_pos["exit"]

        if reason == "TAKE_PROFIT":
            log(
                f"TAKE PROFIT HIT ✓ | {ticker} | Entry: ${entry} → Exit: ${exit_p} | "
                f"P&L: +${pnl}", "WIN"
            )
        else:
            log(
                f"STOP LOSS HIT | {ticker} | Entry: ${entry} → Exit: ${exit_p} | "
                f"P&L: ${pnl}", "LOSS"
            )

        # Send WhatsApp alert on exit
        try:
            from notifications.whatsapp import send_custom_message
            emoji = "🎯" if reason == "TAKE_PROFIT" else "🛑"
            send_custom_message(
                f"{emoji} *FRIDAY Exit Alert*\n"
                f"{'TAKE PROFIT' if reason=='TAKE_PROFIT' else 'STOP LOSS'} hit on *{ticker}*\n"
                f"Entry: ${entry} → Exit: ${exit_p}\n"
                f"P&L: {'+'if pnl>=0 else ''}${pnl} ({outcome})"
            )
        except Exception:
            pass


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

    # 3. Analysis
    analysis = analyze_asset(ticker, market_data, news_text)
    action   = analysis.get("action", "HOLD")
    conf     = analysis.get("confidence", 0)
    source   = analysis.get("source", "unknown")
    reason   = analysis.get("reasoning", "")
    score    = analysis.get("score", "N/A")
    src_label= "Claude AI" if source == "claude_ai" else f"Rule-based (score:{score})"

    log_scan(ticker, price, analysis)

    level = "BUY" if action == "BUY" else "HOLD"
    log(f"{ticker} → {action} (conf:{conf}% | {src_label}) | {reason[:80]}...", level)

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

        # WhatsApp alert on entry
        try:
            from notifications.whatsapp import send_trade_alert
            send_trade_alert(order, analysis, position)
        except Exception:
            pass
    else:
        log(f"Order failed for {ticker}: {order.get('error', 'unknown')}", "ERROR")


def run_scan_cycle():
    """Full scan cycle: exits first, then new entries."""
    print()
    log(f"{'='*50}", "INFO")
    log(f"Scan cycle — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
    log(f"{'='*50}", "INFO")

    # ── Step 1: Check exits on all open positions ──────────────────────────────
    check_exits()
    print()

    # ── Step 2: Scan for new entries ───────────────────────────────────────────
    log(f"Open positions after exits: {len(get_open_positions())}", "INFO")
    log("Scanning watchlist for new entries...", "INFO")

    for ticker in config.STOCK_WATCHLIST:
        try:
            scan_asset(ticker)
        except Exception as e:
            log(f"Error scanning {ticker}: {e}", "ERROR")

    for ticker in config.CRYPTO_WATCHLIST:
        try:
            scan_asset(ticker)
        except Exception as e:
            log(f"Error scanning {ticker}: {e}", "ERROR")

    log("Scan cycle complete.", "INFO")


def show_summary():
    summary  = get_performance_summary()
    open_pos = get_open_positions()

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
        log("Exit logic: Stop-loss and take-profit checked on every cycle.", "INFO")
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
