"""
main.py — FRIDAY: AI Swing Trading Bot
Full market scanner mode — analyses entire S&P 500 + crypto universe.

Usage:
    python main.py              # Single scan run
    python main.py --loop       # Run every N minutes continuously
    python main.py --summary    # Show performance summary
    python main.py --watchlist  # Use fixed watchlist instead of full scan

WEEK 1: market hours + regime filter
WEEK 2: all 4 exchanges, sector limit, earnings blackout, cooling-off
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
from data.market_scanner import (
    run_market_scan, is_stock_market_open,
    get_market_regime, get_open_exchanges
)
from analysis.ai_engine import analyze_asset
from trading.risk_manager import approve_trade, calculate_position
from trading.executor import execute_trade
from trading.position_manager import check_and_close_positions
from trading.journal import (
    init_db, log_scan, log_trade,
    get_open_positions, get_performance_summary
)


def c(text, color):
    if not USE_COLOR: return text
    cols = {"cyan":Fore.CYAN,"green":Fore.GREEN,"yellow":Fore.YELLOW,
            "red":Fore.RED,"white":Fore.WHITE,"dim":Fore.LIGHTBLACK_EX,
            "magenta":Fore.MAGENTA}
    return f"{cols.get(color,'')}{text}{Style.RESET_ALL}"


def banner():
    mode = "MOCK" if config.MOCK_MODE else "PAPER TRADING"
    scan = "FULL MARKET SCAN" if config.MARKET_SCAN_ENABLED else "WATCHLIST"
    print(f"""
{c('╔══════════════════════════════════════════════════╗','cyan')}
{c('║   F.R.I.D.A.Y  —  AI Swing Trading Bot          ║','cyan')}
{c(f'║   Mode: {mode:<43}║','cyan')}
{c(f'║   Scanner: {scan:<41}║','cyan')}
{c('╚══════════════════════════════════════════════════╝','cyan')}
""")


def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    cols = {"INFO":"white","BUY":"green","HOLD":"yellow","SKIP":"yellow",
            "ERROR":"red","TRADE":"cyan","WIN":"green","LOSS":"red",
            "SCAN":"magenta","CLOSE":"cyan"}
    col = cols.get(level, "white")
    print(f"{c(f'[{ts}]','dim')} {c(f'[{level}]',col)} {msg}")


# ── Exit Check ─────────────────────────────────────────────────────────────────
def check_exits():
    log("Checking open positions for stop-loss / take-profit...", "INFO")
    closed = check_and_close_positions()

    if not closed:
        log("No exits triggered this cycle.", "INFO")
        return

    for pos in closed:
        ticker = pos["ticker"]
        reason = pos["exit_reason"]
        pnl    = pos["pnl"]
        entry  = pos["entry"]
        exit_p = pos["exit"]

        if reason == "TAKE_PROFIT":
            log(f"TAKE PROFIT ✓ | {ticker} | ${entry} → ${exit_p} | P&L: +${pnl}", "WIN")
        else:
            log(f"STOP LOSS    | {ticker} | ${entry} → ${exit_p} | P&L: ${pnl}", "LOSS")

        try:
            from notifications.whatsapp import send_custom_message
            emoji = "🎯" if reason == "TAKE_PROFIT" else "🛑"
            send_custom_message(
                f"{emoji} *FRIDAY Exit*\n{'TAKE PROFIT' if reason=='TAKE_PROFIT' else 'STOP LOSS'}"
                f" — *{ticker}*\nEntry: ${entry} → Exit: ${exit_p}\n"
                f"P&L: {'+'if pnl>=0 else ''}${pnl}"
            )
        except Exception:
            pass


# ── Execute a trade from scanner result ────────────────────────────────────────
def execute_candidate(candidate: dict):
    """Takes a pre-scored candidate from the market scanner and executes the trade."""
    ticker   = candidate["ticker"]
    analysis = candidate["analysis"]
    price    = candidate["price"]

    log(f"Executing candidate: {ticker} | Score:{candidate['score']} | "
        f"Conf:{candidate['confidence']}% | {candidate['sentiment']}", "TRADE")

    if analysis.get("key_signals"):
        log(f"  Signals: {' · '.join(analysis['key_signals'][:3])}", "INFO")

    open_positions = get_open_positions()
    approved, reason = approve_trade(analysis, candidate, open_positions)

    if not approved:
        log(f"{ticker} skipped: {reason}", "SKIP")
        return

    position = calculate_position(price, analysis)
    log(
        f"{ticker} | {position['size_label']} | {position['shares']} shares @ ${price} | "
        f"SL: ${position['stop_loss']} | TP: ${position['take_profit']} | "
        f"Risk: ${position['max_dollar_risk']} | R/R: {position['risk_reward_ratio']}x",
        "TRADE"
    )

    log_scan(ticker, price, analysis)

    order = execute_trade(ticker, position)

    if order.get("status") in ("SUBMITTED", "MOCK_SUBMITTED"):
        log(
            f"ORDER PLACED ✓ | {ticker} | ID: {order['order_id']} | "
            f"Cost: ${position['total_cost']} | Broker: {order['broker']}",
            "BUY"
        )
        log_trade(order, analysis)

        try:
            from notifications.whatsapp import send_trade_alert
            send_trade_alert(order, analysis, position)
        except Exception:
            pass
    else:
        log(f"Order failed for {ticker}: {order.get('error','unknown')}", "ERROR")


# ── Watchlist scan (fallback) ──────────────────────────────────────────────────
def scan_watchlist():
    """Scans fixed watchlist when MARKET_SCAN_ENABLED=false."""
    all_tickers = config.STOCK_WATCHLIST + config.CRYPTO_WATCHLIST

    for ticker in all_tickers:
        try:
            log(f"Scanning {ticker}...", "INFO")
            is_crypto   = "/" in ticker or ticker.endswith("-USD")
            market_data = get_crypto_data(ticker) if is_crypto else get_stock_data(ticker)

            if "error" in market_data:
                log(f"{ticker} error: {market_data['error']}", "ERROR")
                continue

            price = market_data.get("price", 0)
            rsi   = market_data.get("rsi", "N/A")
            log(f"{ticker} | Price: ${price} | RSI: {rsi}", "INFO")

            news     = get_news(ticker)
            news_txt = format_news_for_prompt(news)
            analysis = analyze_asset(ticker, market_data, news_txt)

            log_scan(ticker, price, analysis)

            action = analysis.get("action","HOLD")
            conf   = analysis.get("confidence",0)
            score  = analysis.get("score","N/A")
            log(f"{ticker} → {action} (conf:{conf}% score:{score})", action if action=="BUY" else "HOLD")

            if action == "BUY":
                open_positions = get_open_positions()
                approved, reason = approve_trade(analysis, market_data, open_positions)
                if not approved:
                    log(f"{ticker} skipped: {reason}", "SKIP")
                    continue

                position = calculate_position(price, analysis)
                log(f"{ticker} | {position['shares']}sh @ ${price} | "
                    f"SL:${position['stop_loss']} TP:${position['take_profit']}", "TRADE")

                order = execute_trade(ticker, position)
                if order.get("status") in ("SUBMITTED","MOCK_SUBMITTED"):
                    log(f"ORDER PLACED ✓ | {ticker} | {order['order_id']}", "BUY")
                    log_trade(order, analysis)

        except Exception as e:
            log(f"Error on {ticker}: {e}", "ERROR")


# ── Main scan cycle ────────────────────────────────────────────────────────────
def run_scan_cycle():
    print()
    log("═"*55, "INFO")
    log(f"FRIDAY Scan Cycle — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "SCAN")
    log("═"*55, "INFO")

    # ── Week 1 + Week 2: Exchange status + regime ──────────────────
    exchanges = get_open_exchanges()
    open_exc  = [f"{n}({i['msg'].split()[0]})" for n, i in exchanges.items() if i["open"]]
    closed_exc= [f"{n}({i['msg'].split()[0]})" for n, i in exchanges.items() if not i["open"]]
    log(f"Open exchanges  : {', '.join(open_exc)  if open_exc   else 'None (crypto only)'}", "INFO")
    log(f"Closed exchanges: {', '.join(closed_exc) if closed_exc else 'None'}", "INFO")

    regime_data = get_market_regime()
    log(f"Market regime   : {regime_data['message']}", "INFO")
    # ──────────────────────────────────────────────────────────────

    # Step 1: Exit check — always runs regardless of hours or regime
    check_exits()
    print()

    open_positions = get_open_positions()
    log(f"Open positions: {len(open_positions)} / {config.SCAN_MAX_NEW_TRADES+len(open_positions)} slots", "INFO")

    # Step 2: Scan for entries
    if config.MARKET_SCAN_ENABLED:
        log("Mode: FULL MARKET SCAN — all open exchanges + crypto", "SCAN")
        candidates = run_market_scan(
            open_positions=open_positions,
            include_crypto=config.SCAN_INCLUDE_CRYPTO,
            max_candidates=config.SCAN_MAX_CANDIDATES,
            max_new_trades=config.SCAN_MAX_NEW_TRADES,
        )
        print()
        if candidates:
            log(f"Executing {len(candidates)} selected trade candidates...", "SCAN")
            for candidate in candidates:
                execute_candidate(candidate)
        else:
            log("No high-conviction trades found this cycle. Holding cash.", "INFO")
    else:
        log("Mode: WATCHLIST — scanning fixed tickers", "SCAN")
        scan_watchlist()

    print()
    log("Scan cycle complete.", "INFO")
    show_summary_inline()


def show_summary_inline():
    summary = get_performance_summary()
    pos     = get_open_positions()
    print()
    log(f"── Performance: {summary.get('total_trades',0)} trades | "
        f"Win rate: {summary.get('win_rate',0)}% | "
        f"P&L: ${summary.get('total_pnl',0)}", "INFO")
    if pos:
        log(f"── Open: {', '.join(p['ticker'] for p in pos)}", "INFO")


def show_summary():
    summary = get_performance_summary()
    pos     = get_open_positions()
    print(f"\n{c('── FRIDAY Performance ──','cyan')}")
    for k,v in summary.items():
        print(f"  {k}: {v}")
    print(f"\n{c(f'── Open Positions ({len(pos)}) ──','cyan')}")
    for p in pos:
        print(f"  {p['ticker']:<12} {p['shares']}sh @ ${p['entry_price']}"
              f" | SL:${p['stop_loss']} TP:${p['take_profit']} | {p['broker']}")
    print()


def main():
    banner()
    init_db()

    args = sys.argv[1:]

    if "--summary" in args:
        show_summary()
        return

    if "--watchlist" in args:
        config.MARKET_SCAN_ENABLED = False

    if "--loop" in args:
        log(f"FRIDAY running. Full scan every {config.SCAN_INTERVAL_MINUTES} min.", "INFO")
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
