"""
dashboard/app.py — FRIDAY Web Dashboard Backend
Run with: python dashboard/app.py
Then open: http://localhost:5000
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import threading
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

import config as cfg
from trading.journal import (
    init_db, get_open_positions,
    get_performance_summary, log_scan, log_trade
)

app = Flask(__name__, static_folder="static")
scan_log = []   # in-memory log of recent scan messages
is_running = False
scan_thread = None


# ── Static files ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ── Status ─────────────────────────────────────────────────────────────────────
@app.route("/api/status")
def status():
    return jsonify({
        "running": is_running,
        "mock_mode": cfg.MOCK_MODE,
        "scan_interval": cfg.SCAN_INTERVAL_MINUTES,
        "capital_per_trade": cfg.CAPITAL_PER_TRADE,
        "max_risk_pct": cfg.MAX_RISK_PERCENT,
        "stop_loss_pct": cfg.STOP_LOSS_PERCENT,
        "take_profit_pct": cfg.TAKE_PROFIT_PERCENT,
        "stock_watchlist": cfg.STOCK_WATCHLIST,
        "crypto_watchlist": cfg.CRYPTO_WATCHLIST,
        "timestamp": datetime.now().isoformat(),
    })


# ── Performance ────────────────────────────────────────────────────────────────
@app.route("/api/performance")
def performance():
    return jsonify(get_performance_summary())


# ── Open positions ─────────────────────────────────────────────────────────────
@app.route("/api/positions")
def positions():
    return jsonify(get_open_positions())


# ── Recent logs ────────────────────────────────────────────────────────────────
@app.route("/api/logs")
def logs():
    return jsonify(scan_log[-100:])  # last 100 messages


# ── Manual scan trigger ────────────────────────────────────────────────────────
@app.route("/api/scan", methods=["POST"])
def trigger_scan():
    global is_running, scan_thread
    if is_running:
        return jsonify({"error": "Scan already running"}), 400

    def run():
        global is_running
        is_running = True
        try:
            from main import scan_asset
            import config as cfg
            for t in cfg.STOCK_WATCHLIST:
                _log(f"Scanning {t}...")
                scan_asset(t)
                _log(f"Done: {t}")
            for t in cfg.CRYPTO_WATCHLIST:
                _log(f"Scanning {t}...")
                scan_asset(t)
                _log(f"Done: {t}")
        except Exception as e:
            _log(f"ERROR: {e}")
        finally:
            is_running = False

    scan_thread = threading.Thread(target=run, daemon=True)
    scan_thread.start()
    return jsonify({"message": "Scan started"})


# ── Settings update ────────────────────────────────────────────────────────────
@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.json or {}

    # Update in-memory config
    if "capital_per_trade" in data:
        cfg.CAPITAL_PER_TRADE = float(data["capital_per_trade"])
    if "max_risk_pct" in data:
        cfg.MAX_RISK_PERCENT = float(data["max_risk_pct"])
    if "stop_loss_pct" in data:
        cfg.STOP_LOSS_PERCENT = float(data["stop_loss_pct"])
    if "take_profit_pct" in data:
        cfg.TAKE_PROFIT_PERCENT = float(data["take_profit_pct"])
    if "scan_interval" in data:
        cfg.SCAN_INTERVAL_MINUTES = int(data["scan_interval"])
    if "stock_watchlist" in data:
        cfg.STOCK_WATCHLIST = [t.strip().upper() for t in data["stock_watchlist"] if t.strip()]
    if "crypto_watchlist" in data:
        cfg.CRYPTO_WATCHLIST = [t.strip().upper() for t in data["crypto_watchlist"] if t.strip()]
    if "mock_mode" in data:
        cfg.MOCK_MODE = bool(data["mock_mode"])

    _log(f"Settings updated: {list(data.keys())}")
    return jsonify({"message": "Settings updated successfully"})


def _log(msg: str):
    scan_log.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg})


if __name__ == "__main__":
    init_db()
    print("\n🤖 FRIDAY Dashboard starting at http://localhost:5000\n")
    app.run(debug=False, port=5000)
