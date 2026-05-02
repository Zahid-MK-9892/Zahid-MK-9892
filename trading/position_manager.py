"""
trading/position_manager.py — Automatic position exit manager.
Uses real-time quotes (not daily candles) to check stop-loss / take-profit.

WEEK 3 UPGRADES:
  + Trailing stop  — stop_loss moves UP as price rises. No schema change.
                     Trail % = same % as original stop distance from entry.
                     Stop only ever moves higher, never lower.
                     Activates as soon as the trailing level beats the original stop.

  + Partial TP     — at first TP hit: close 50% of shares, move stop to
                     breakeven (entry price), let remaining 50% run freely.
                     Uses partial_tp_taken column (added by journal.py init_db).
"""

from datetime import datetime
from trading.journal import get_open_positions, close_position, partial_close
import config


def _get_realtime_price(ticker: str) -> float:
    """
    Fetches the latest real-time price using yfinance.
    Tries fast_info (real-time) → history() → download() fallbacks.
    """
    try:
        import yfinance as yf
        import pandas as pd
        import numpy as np

        yf_sym = ticker.replace("/USDT", "-USD").replace("/BTC", "-BTC").replace("/", "-")
        t = yf.Ticker(yf_sym)

        # ── Method 1: fast_info (real-time) ─────────────────────────────────
        # fast_info is an object — use getattr(), NOT .get()
        try:
            fi = t.fast_info
            for attr in ("last_price", "lastPrice", "regularMarketPrice"):
                val = getattr(fi, attr, None)
                if val is not None:
                    price = float(val)
                    if price > 0:
                        return round(price, 4)
        except Exception:
            pass

        # ── Method 2: history() ──────────────────────────────────────────────
        try:
            df = t.history(period="2d", interval="1d")
            if df is not None and not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                close_data = df["Close"].squeeze()
                price = float(close_data.iloc[-1]) if hasattr(close_data, "iloc") else float(close_data)
                if price > 0:
                    return round(price, 4)
        except Exception:
            pass

        # ── Method 3: yf.download() ──────────────────────────────────────────
        try:
            data = yf.download(yf_sym, period="5d", interval="1h",
                               progress=False, auto_adjust=True, threads=False)
            if data is not None and not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                close_col = data["Close"]
                if isinstance(close_col, pd.DataFrame):
                    close_col = close_col.iloc[:, 0]
                squeezed = close_col.squeeze()
                price = float(squeezed.iloc[-1]) if hasattr(squeezed, "iloc") else float(squeezed)
                if price > 0:
                    return round(price, 4)
        except Exception:
            pass

    except Exception as e:
        print(f"[EXIT] Price fetch failed for {ticker}: {e}")

    return 0.0


# ══════════════════════════════════════════════════════════════════
#  WEEK 3 — TRAILING STOP HELPER
# ══════════════════════════════════════════════════════════════════

def _calc_trailing_stop(entry: float, orig_sl: float, current: float) -> float:
    """
    Calculates the new trailing stop level.
    Trail % = original stop distance from entry (e.g. 5%).
    New stop = current_price × (1 - trail_pct).
    Stop only moves UP — returned value may still be below orig_sl.
    The caller decides whether to apply it.
    """
    if entry <= 0:
        return orig_sl
    trail_pct  = (entry - orig_sl) / entry  # e.g. 0.05 for 5%
    trail_pct  = max(trail_pct, 0.03)        # floor at 3% — never trail too tight
    new_trail  = round(current * (1 - trail_pct), 4)
    return new_trail


def _update_trailing_stop(trade_id: int, new_sl: float) -> None:
    """Update stop_loss in DB. Called only when new_sl > current stop."""
    try:
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "friday_journal.db"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE trades SET stop_loss = ? WHERE id = ?",
                (new_sl, trade_id)
            )
            conn.commit()
    except Exception as e:
        print(f"  [WARN] Could not update trailing stop for trade {trade_id}: {e}")


# ══════════════════════════════════════════════════════════════════
#  MAIN CHECK
# ══════════════════════════════════════════════════════════════════

def check_and_close_positions() -> list:
    """
    Called every scan cycle.
    Checks every open position against real-time price.

    Week 3 logic per position:
      1. Fetch current price.
      2. Calculate new trailing stop. If it's higher than existing stop → update DB.
      3. Check for Partial TP: if price >= take_profit and partial not yet taken:
           → close 50% of shares at current price (mark as partial WIN)
           → update remaining shares = 50%, move stop_loss to entry (breakeven)
      4. Check full exit:
           - Full TP:  price >= take_profit (partial already taken) → close all
           - Full SL:  price <= stop_loss → close all
    """
    open_positions = get_open_positions()
    closed = []

    for pos in open_positions:
        ticker            = pos.get("ticker", "")
        entry             = float(pos.get("entry_price") or 0)
        stop_loss         = float(pos.get("stop_loss") or 0)
        take_profit       = float(pos.get("take_profit") or 0)
        shares            = float(pos.get("shares") or 0)
        trade_id          = pos.get("id")
        partial_tp_taken  = bool(pos.get("partial_tp_taken", 0))

        if not ticker or not entry or not stop_loss or not take_profit:
            continue

        current = _get_realtime_price(ticker)
        if not current or current <= 0:
            print(f"  [EXIT] Could not get price for {ticker}, skipping")
            continue

        print(f"  [EXIT] {ticker} | Entry: ${entry} | Current: ${current} | "
              f"SL: ${stop_loss} | TP: ${take_profit}"
              + (" | 🔄 Partial TP taken" if partial_tp_taken else ""))

        # ── Step 2: Update trailing stop ──────────────────────────────────────
        new_trail = _calc_trailing_stop(entry, stop_loss, current)
        if new_trail > stop_loss:
            print(f"  [TRAIL] {ticker} stop updated: ${stop_loss} → ${new_trail}")
            _update_trailing_stop(trade_id, new_trail)
            try:
                from notifications.telegram import send_trailing_stop_alert
                send_trailing_stop_alert(
                    ticker  = ticker,
                    old_sl  = stop_loss,
                    new_sl  = new_trail,
                    current = current,
                )
            except Exception:
                pass
            stop_loss = new_trail  # use updated value for exit checks this cycle

        # ── Step 3: Partial TP (first time price hits TP) ────────────────────
        if current >= take_profit and not partial_tp_taken:
            half_shares = shares / 2
            pnl_partial = round((current - entry) * half_shares, 2)

            print(f"  [PARTIAL TP] {ticker} | Closing 50% ({half_shares:.4f} shares) "
                  f"@ ${current} | Partial P&L: +${pnl_partial}")

            # Close 50% in journal — mark partial, move stop to breakeven
            partial_close(
                trade_id=trade_id,
                exit_price=current,
                pnl_partial=pnl_partial,
                remaining_shares=half_shares,
                new_stop=entry,   # move stop to breakeven
            )

            # Send alerts for partial close
            _partial_msg = (
                f"🎯 F.R.I.D.A.Y PARTIAL TAKE PROFIT\n"
                f"📌 {ticker} — 50% closed @ ${current}\n"
                f"Partial P&L: +${pnl_partial}\n"
                f"Remaining 50% running with stop at breakeven (${entry})"
            )
            _send_whatsapp(_partial_msg)
            try:
                from notifications.telegram import send_partial_tp_alert
                send_partial_tp_alert(
                    ticker          = ticker,
                    current         = current,
                    pnl_partial     = pnl_partial,
                    entry           = entry,
                    remaining_shares= half_shares,
                )
            except Exception:
                pass

            closed.append({
                "ticker":      ticker,
                "exit_reason": "PARTIAL_TAKE_PROFIT",
                "entry":       entry,
                "exit":        current,
                "pnl":         pnl_partial,
                "outcome":     "WIN",
                "shares":      half_shares,
                "timestamp":   datetime.now().isoformat(),
            })
            continue  # don't check full exit this cycle — let remaining run

        # ── Step 4: Full exit check ───────────────────────────────────────────
        exit_reason = None
        if current >= take_profit and partial_tp_taken:
            # Second half hit TP — close remaining
            exit_reason = "TAKE_PROFIT"
        elif current <= stop_loss:
            exit_reason = "STOP_LOSS"

        if not exit_reason:
            continue  # Still open

        result  = close_position(trade_id, current)
        pnl     = result.get("pnl", 0) if result else 0
        outcome = result.get("outcome", "?") if result else "?"

        label = "TAKE PROFIT ✓" if exit_reason == "TAKE_PROFIT" else "STOP LOSS ✗"
        print(f"  [{outcome}] {label} | {ticker} | ${entry} → ${current} | P&L: ${pnl:+.2f}")

        _send_whatsapp(
            f"{'🎯' if outcome == 'WIN' else '🛑'} F.R.I.D.A.Y {label}\n"
            f"{'✅' if outcome == 'WIN' else '❌'} {ticker} fully closed\n"
            f"Entry: ${entry} → Exit: ${current}\n"
            f"P&L: ${pnl:+.2f}"
        )
        try:
            from notifications.telegram import send_close_alert
            send_close_alert(
                ticker      = ticker,
                exit_reason = exit_reason,
                entry       = entry,
                exit_price  = current,
                pnl         = pnl,
                shares      = shares,
            )
        except Exception:
            pass

        closed.append({
            "ticker":      ticker,
            "exit_reason": exit_reason,
            "entry":       entry,
            "exit":        current,
            "pnl":         pnl,
            "outcome":     outcome,
            "shares":      shares,
            "timestamp":   datetime.now().isoformat(),
        })

        _close_on_broker(pos, current)

    return closed


def _send_whatsapp(message: str) -> None:
    """Send WhatsApp alert. Silently skips if not configured."""
    try:
        from notifications.whatsapp import send_custom_message
        send_custom_message(message)
    except Exception:
        pass


def _send_telegram(message: str) -> None:
    """Send Telegram alert. Silently skips if not configured."""
    try:
        from notifications.telegram import send_custom_message
        send_custom_message(message)
    except Exception:
        pass

def _close_on_broker(pos: dict, exit_price: float) -> None:
    """Attempt to close on Alpaca. Silently ignores errors."""
    try:
        if config.MOCK_MODE:
            return
        if pos.get("asset_type") == "STOCK":
            from alpaca.trading.client import TradingClient
            client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
            client.close_position(pos["ticker"])
    except Exception:
        pass
