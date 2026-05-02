"""
notifications/telegram.py — Telegram trade alerts for F.R.I.D.A.Y.

FREE — uses Telegram Bot API directly via requests (no extra library needed).
requests is already in requirements.txt.

SETUP (5 minutes, one time):
  1. Open Telegram → search @BotFather → send /newbot
  2. Give it a name e.g. "FRIDAY Trading Bot" → get your TOKEN
  3. Message @userinfobot → get your CHAT_ID (a plain number)
  4. Add to .env:
       TELEGRAM_BOT_TOKEN=123456:ABC-your-token-here
       TELEGRAM_CHAT_ID=987654321
  5. Restart the bot → use the Test button in the dashboard

FUNCTIONS (all public):
  send_trade_alert(order, analysis, position)  — called on BUY signal
  send_close_alert(ticker, reason, entry, exit_price, pnl, shares)
  send_partial_tp_alert(ticker, current, pnl_partial, entry, remaining)
  send_trailing_stop_alert(ticker, old_sl, new_sl, current)
  send_daily_summary(summary, open_positions)
  send_custom_message(text)                    — test button / custom use

All functions return {"status": "sent"|"mock"|"error", ...}.
All functions are safe to call even if Telegram is not configured —
they silently return {"status": "mock"} so they never crash the bot.
"""

import os
import requests
from datetime import datetime
from config import MOCK_MODE

# ── Credentials (loaded at import time from .env via config) ──────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

_PLACEHOLDERS = {"your_telegram_bot_token_here", "your_chat_id_here", ""}

_API_BASE = "https://api.telegram.org/bot{token}/sendMessage"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_configured() -> bool:
    """Returns True only if both token and chat_id are real values."""
    return (
        bool(TELEGRAM_TOKEN)   and TELEGRAM_TOKEN   not in _PLACEHOLDERS and
        bool(TELEGRAM_CHAT_ID) and TELEGRAM_CHAT_ID not in _PLACEHOLDERS
    )


def _send(text: str) -> dict:
    """
    Core send function. Uses Telegram Markdown parse mode.
    Falls back to plain text if markdown causes a parse error.
    All network errors are caught — never raises.
    """
    if MOCK_MODE or not _is_configured():
        print(f"[Telegram MOCK]\n{text}")
        return {"status": "mock", "message": text}

    url = _API_BASE.format(token=TELEGRAM_TOKEN)

    # Try with Markdown first, fall back to plain text
    for parse_mode in ("Markdown", None):
        try:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text":    text,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()

            if data.get("ok"):
                return {"status": "sent", "message_id": data["result"]["message_id"]}

            # Markdown parse error → retry as plain text
            if parse_mode and "parse" in data.get("description", "").lower():
                continue

            return {"status": "error", "error": data.get("description", "Unknown error")}

        except requests.exceptions.ConnectionError:
            return {"status": "error", "error": "No internet connection"}
        except requests.exceptions.Timeout:
            return {"status": "error", "error": "Telegram API timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    return {"status": "error", "error": "Failed to send (markdown + plain both failed)"}


def _ts() -> str:
    """Current timestamp formatted for messages."""
    return datetime.now().strftime("%d %b %Y  %H:%M")


# ══════════════════════════════════════════════════════════════════
#  PUBLIC FUNCTIONS
# ══════════════════════════════════════════════════════════════════

def send_trade_alert(order: dict, analysis: dict, position: dict) -> dict:
    """
    Called when FRIDAY opens a new position (BUY signal executed).
    Mirrors the WhatsApp trade alert but optimised for Telegram.
    """
    ticker  = order.get("ticker", "?")
    entry   = position.get("entry_price", 0)
    stop    = position.get("stop_loss", 0)
    target  = position.get("take_profit", 0)
    shares  = position.get("shares", 0)
    cost    = position.get("total_cost", 0)
    rr      = position.get("risk_reward_ratio", 0)
    conf    = analysis.get("confidence", 0)
    score   = analysis.get("score", 0)
    reason  = (analysis.get("reasoning") or "")[:150]
    broker  = order.get("broker", "Paper")
    atype   = order.get("asset_type", "STOCK")
    signals = analysis.get("key_signals", [])[:3]

    icon  = "🪙" if atype == "CRYPTO" else "📈"
    stars = "⭐" * min(5, max(1, score // 2))

    sig_lines = "\n".join(f"  • {s}" for s in signals) if signals else "  • No signals"

    msg = (
        f"🤖 *F.R.I.D.A.Y — NEW TRADE*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{icon} *BUY {ticker}*   {stars}\n"
        f"🕐 {_ts()}\n\n"
        f"💰 Entry:   *${entry}*\n"
        f"🛑 Stop:    ${stop}\n"
        f"🎯 Target:  ${target}\n"
        f"📦 Shares:  {shares}   |   Cost: ${cost}\n"
        f"⚖️ R/R: {rr}x   |   Conf: {conf}%   |   Score: {score}\n\n"
        f"📊 *Signals:*\n{sig_lines}\n\n"
        f"📝 _{reason}_\n\n"
        f"🏦 Broker: {broker}"
    )
    return _send(msg)


def send_close_alert(ticker: str, exit_reason: str,
                     entry: float, exit_price: float,
                     pnl: float, shares: float = 0) -> dict:
    """
    Called when a position is fully closed — TAKE_PROFIT or STOP_LOSS.
    """
    is_win  = pnl >= 0
    emoji   = "🎯✅" if exit_reason == "TAKE_PROFIT" else "🛑❌"
    label   = "TAKE PROFIT" if exit_reason == "TAKE_PROFIT" else "STOP LOSS"
    pnl_str = f"+${pnl:.2f}" if is_win else f"-${abs(pnl):.2f}"
    pct     = round(((exit_price - entry) / entry) * 100, 2) if entry else 0
    pct_str = f"+{pct:.1f}%" if pct >= 0 else f"{pct:.1f}%"

    msg = (
        f"{emoji} *F.R.I.D.A.Y — POSITION CLOSED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *{label}* — {ticker}\n"
        f"🕐 {_ts()}\n\n"
        f"📥 Entry:  ${entry}\n"
        f"📤 Exit:   *${exit_price}*\n"
        f"💵 P&L:    *{pnl_str}* ({pct_str})\n"
        + (f"📦 Shares: {shares}\n" if shares else "")
        + f"\n{'🏆 Trade won!' if is_win else '📉 Stop hit — capital protected.'}"
    )
    return _send(msg)


def send_partial_tp_alert(ticker: str, current: float,
                           pnl_partial: float, entry: float,
                           remaining_shares: float) -> dict:
    """
    Called when first TP hit — 50% closed, stop moved to breakeven.
    """
    msg = (
        f"🎯 *F.R.I.D.A.Y — PARTIAL TAKE PROFIT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *{ticker}* — 50% closed\n"
        f"🕐 {_ts()}\n\n"
        f"📤 Exit (50%):    *${current}*\n"
        f"💵 Partial P&L:   *+${pnl_partial:.2f}*\n"
        f"📦 Remaining:     {remaining_shares:.4f} shares\n"
        f"🛡️ Stop moved to: *${entry}* (breakeven)\n\n"
        f"📊 Remaining position now runs risk-free.\n"
        f"_FRIDAY is letting the winners run_ 🚀"
    )
    return _send(msg)


def send_trailing_stop_alert(ticker: str, old_sl: float,
                              new_sl: float, current: float) -> dict:
    """
    Called when trailing stop is moved up to protect profits.
    """
    protected = round(current - new_sl, 4)
    msg = (
        f"🔒 *F.R.I.D.A.Y — TRAILING STOP UPDATED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *{ticker}*\n"
        f"🕐 {_ts()}\n\n"
        f"📈 Current price:  ${current}\n"
        f"🛑 Old stop:       ${old_sl}\n"
        f"🔒 New stop:       *${new_sl}*\n"
        f"💰 Profit locked:  ~${protected} per share\n\n"
        f"_Stop raised to protect open profit_ 📈"
    )
    return _send(msg)


def send_daily_summary(summary: dict, open_positions: list) -> dict:
    """
    Called at end of last scan cycle each day.
    summary  = get_performance_summary() from journal.py
    open_positions = get_open_positions() from journal.py
    """
    total  = summary.get("total_trades", 0)
    wins   = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    wr     = summary.get("win_rate", 0)
    pnl    = summary.get("total_pnl", 0)
    avg    = summary.get("avg_pnl_per_trade", 0)
    n_open = len(open_positions)

    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    avg_str = f"+${avg:.2f}" if avg >= 0 else f"-${abs(avg):.2f}"
    mood    = "🟢" if pnl >= 0 else "🔴"

    pos_lines = ""
    if open_positions:
        lines = []
        for p in open_positions[:5]:  # max 5 to keep message tidy
            lines.append(
                f"  • {p['ticker']} @ ${p['entry_price']} "
                f"(SL ${p['stop_loss']} | TP ${p['take_profit']})"
            )
        if len(open_positions) > 5:
            lines.append(f"  ... and {len(open_positions)-5} more")
        pos_lines = "\n📂 *Open Positions:*\n" + "\n".join(lines)
    else:
        pos_lines = "\n📂 *Open Positions:* None"

    msg = (
        f"{mood} *F.R.I.D.A.Y — DAILY SUMMARY*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 {datetime.now().strftime('%A, %d %b %Y')}\n\n"
        f"📊 *All-time Performance:*\n"
        f"  Trades:    {total}  ({wins}W / {losses}L)\n"
        f"  Win Rate:  {wr}%\n"
        f"  Total P&L: *{pnl_str}*\n"
        f"  Avg/Trade: {avg_str}\n"
        + pos_lines
        + f"\n\n_FRIDAY is watching the markets 24/7_ 🤖"
    )
    return _send(msg)


def send_custom_message(text: str) -> dict:
    """
    Send any plain text message.
    Used by the dashboard Test button and for one-off alerts.
    """
    return _send(text)
