"""
trading/executor.py — Places orders via Alpaca (stocks) or Binance testnet (crypto).
Falls back to mock simulation if keys are missing.
"""

import uuid
from datetime import datetime
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY,
    BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET,
    MOCK_MODE
)

_NO_ALPACA  = not ALPACA_API_KEY  or ALPACA_API_KEY  == "your_alpaca_key_here"
_NO_BINANCE = not BINANCE_API_KEY or BINANCE_API_KEY == "your_binance_testnet_key_here"


def execute_trade(ticker: str, position: dict) -> dict:
    """Unified entry — routes to stock or crypto executor."""
    if _is_crypto(ticker):
        return _place_crypto(ticker, position)
    return _place_stock(ticker, position)


def _is_crypto(ticker: str) -> bool:
    return "/" in ticker or ticker.endswith("-USD")


def _place_stock(ticker: str, position: dict) -> dict:
    if MOCK_MODE or _NO_ALPACA:
        return _mock_order(ticker, position, "STOCK")
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        order = client.submit_order(MarketOrderRequest(
            symbol=ticker, qty=position["shares"],
            side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
        ))
        return {
            "status": "SUBMITTED", "order_id": str(order.id),
            "ticker": ticker, "shares": position["shares"],
            "entry_price": position["entry_price"],
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "total_cost": position["total_cost"],
            "risk_reward_ratio": position.get("risk_reward_ratio"),
            "timestamp": datetime.now().isoformat(),
            "broker": "Alpaca Paper", "asset_type": "STOCK",
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "ticker": ticker,
                "timestamp": datetime.now().isoformat()}


def _place_crypto(ticker: str, position: dict) -> dict:
    if MOCK_MODE or _NO_BINANCE:
        return _mock_order(ticker, position, "CRYPTO")
    try:
        import ccxt
        exchange = ccxt.binance({
            "apiKey": BINANCE_API_KEY, "secret": BINANCE_SECRET_KEY,
            "enableRateLimit": True,
        })
        if BINANCE_TESTNET:
            exchange.set_sandbox_mode(True)
        amount = position["total_cost"] / position["entry_price"]
        order  = exchange.create_market_buy_order(ticker, amount)
        return {
            "status": "SUBMITTED", "order_id": str(order.get("id", "unknown")),
            "ticker": ticker, "shares": amount,
            "entry_price": position["entry_price"],
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "total_cost": position["total_cost"],
            "risk_reward_ratio": position.get("risk_reward_ratio"),
            "timestamp": datetime.now().isoformat(),
            "broker": "Binance Testnet", "asset_type": "CRYPTO",
        }
    except Exception as e:
        return {"status": "ERROR", "error": str(e), "ticker": ticker,
                "timestamp": datetime.now().isoformat()}


def _mock_order(ticker: str, position: dict, asset_type: str) -> dict:
    return {
        "status": "MOCK_SUBMITTED",
        "order_id": f"MOCK-{uuid.uuid4().hex[:8].upper()}",
        "ticker": ticker,
        "shares": position["shares"],
        "entry_price": position["entry_price"],
        "stop_loss": position["stop_loss"],
        "take_profit": position["take_profit"],
        "total_cost": position["total_cost"],
        "risk_reward_ratio": position.get("risk_reward_ratio"),
        "timestamp": datetime.now().isoformat(),
        "broker": "Mock Simulation",
        "asset_type": asset_type,
    }
