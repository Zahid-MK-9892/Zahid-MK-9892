"""
trading/journal.py — Logs every FRIDAY decision and trade to a SQLite database.
This is your audit trail, performance tracker, and learning dataset.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "friday_journal.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates the database tables if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker      TEXT NOT NULL,
                price       REAL,
                action      TEXT,
                confidence  INTEGER,
                reasoning   TEXT,
                key_signals TEXT,
                risk_level  TEXT,
                sentiment   TEXT,
                timestamp   TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id        TEXT,
                ticker          TEXT NOT NULL,
                asset_type      TEXT,
                shares          REAL,
                entry_price     REAL,
                stop_loss       REAL,
                take_profit     REAL,
                total_cost      REAL,
                risk_reward     REAL,
                broker          TEXT,
                status          TEXT,
                confidence      INTEGER,
                reasoning       TEXT,
                opened_at       TEXT NOT NULL,
                closed_at       TEXT,
                exit_price      REAL,
                pnl             REAL,
                pnl_pct         REAL,
                outcome         TEXT
            )
        """)
        conn.commit()


def log_scan(ticker: str, price: float, analysis: dict):
    """Logs every AI scan result, regardless of whether a trade was placed."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO scans (ticker, price, action, confidence, reasoning, key_signals, risk_level, sentiment, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker,
            price,
            analysis.get("action"),
            analysis.get("confidence"),
            analysis.get("reasoning"),
            json.dumps(analysis.get("key_signals", [])),
            analysis.get("risk_level"),
            analysis.get("sentiment"),
            datetime.now().isoformat(),
        ))
        conn.commit()


def log_trade(order: dict, analysis: dict):
    """Logs a placed trade order to the trades table."""
    with _get_conn() as conn:
        conn.execute("""
            INSERT INTO trades (order_id, ticker, asset_type, shares, entry_price, stop_loss,
                                take_profit, total_cost, risk_reward, broker, status,
                                confidence, reasoning, opened_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order.get("order_id"),
            order.get("ticker"),
            order.get("asset_type"),
            order.get("shares"),
            order.get("entry_price"),
            order.get("stop_loss"),
            order.get("take_profit"),
            order.get("total_cost"),
            order.get("risk_reward_ratio"),
            order.get("broker"),
            order.get("status"),
            analysis.get("confidence"),
            analysis.get("reasoning"),
            datetime.now().isoformat(),
        ))
        conn.commit()


def get_open_positions() -> list[dict]:
    """Returns all trades that haven't been closed yet."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NULL AND status != 'ERROR'"
        ).fetchall()
        return [dict(r) for r in rows]


def close_position(trade_id: int, exit_price: float):
    """Marks a trade as closed and calculates P&L."""
    with _get_conn() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            return

        trade = dict(trade)
        entry  = trade["entry_price"]
        shares = trade["shares"]
        pnl    = round((exit_price - entry) * shares, 2)
        pnl_pct = round(((exit_price - entry) / entry) * 100, 2)
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")

        conn.execute("""
            UPDATE trades
            SET closed_at=?, exit_price=?, pnl=?, pnl_pct=?, outcome=?, status='CLOSED'
            WHERE id=?
        """, (datetime.now().isoformat(), exit_price, pnl, pnl_pct, outcome, trade_id))
        conn.commit()

    return {"pnl": pnl, "pnl_pct": pnl_pct, "outcome": outcome}


def get_performance_summary() -> dict:
    """Returns key performance stats from the trade journal."""
    with _get_conn() as conn:
        closed = conn.execute(
            "SELECT * FROM trades WHERE closed_at IS NOT NULL"
        ).fetchall()

        if not closed:
            return {"message": "No closed trades yet."}

        trades = [dict(r) for r in closed]
        total  = len(trades)
        wins   = sum(1 for t in trades if t["outcome"] == "WIN")
        losses = sum(1 for t in trades if t["outcome"] == "LOSS")
        total_pnl = sum(t["pnl"] or 0 for t in trades)

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round((wins / total) * 100, 1) if total > 0 else 0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl_per_trade": round(total_pnl / total, 2),
        }
