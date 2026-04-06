"""
trading/executor.py — Places orders via Alpaca (paper) or mock simulation.
Crypto execution via ccxt (Binance testnet) is also supported.
"""

from datetime import datetime
from config import (
    ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL,
    BINANCE_API_KEY, BINANCE_SECRET_KEY, BINANCE_TESTNET,
    MOCK_MODE
)


def place_stock_order(ticker: str, position: dict, dry_run: bool = False) -> dict:
    """
    Places a paper stock buy order via Alpaca.
    Falls back to mock if MOCK_MODE=true or API keys not set.
    """
    if MOCK_MODE or not ALPACA_API_KEY or dry_run:
        return _mock_order(ticker, position, "STOCK")

    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)

        order_data = MarketOrderRequest(
            symbol=ticker,
            qty=position["shares"],
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
        )
        order = client.submit_order(order_data)

        return {
            "status": "SUBMITTED",
            "order_id": str(order.id),
            "ticker": ticker,
            "shares": position["shares"],
            "entry_price": position["entry_price"],
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "total_cost": position["total_cost"],
            "timestamp": datetime.now().isoformat(),
            "broker": "Alpaca Paper",
            "asset_type": "STOCK",
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "ticker": ticker,
            "timestamp": datetime.now().isoformat(),
        }


def place_crypto_order(symbol: str, position: dict, dry_run: bool = False) -> dict:
    """
    Places a crypto paper order via Binance testnet.
    Falls back to mock if MOCK_MODE=true or keys not set.
    """
    if MOCK_MODE or not BINANCE_API_KEY or dry_run:
        return _mock_order(symbol, position, "CRYPTO")

    try:
        import ccxt
        exchange = ccxt.binance({
            "apiKey": BINANCE_API_KEY,
            "secret": BINANCE_SECRET_KEY,
            "enableRateLimit": True,
        })
        if BINANCE_TESTNET:
            exchange.set_sandbox_mode(True)

        # Calculate quantity in base currency
        amount = position["total_cost"] / position["entry_price"]
        order = exchange.create_market_buy_order(symbol, amount)

        return {
            "status": "SUBMITTED",
            "order_id": str(order.get("id", "unknown")),
            "ticker": symbol,
            "shares": amount,
            "entry_price": position["entry_price"],
            "stop_loss": position["stop_loss"],
            "take_profit": position["take_profit"],
            "total_cost": position["total_cost"],
            "timestamp": datetime.now().isoformat(),
            "broker": "Binance Testnet",
            "asset_type": "CRYPTO",
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e),
            "ticker": symbol,
            "timestamp": datetime.now().isoformat(),
        }


def _mock_order(ticker: str, position: dict, asset_type: str) -> dict:
    """Simulates a successful order for mock/paper mode."""
    import uuid
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
        "broker": "Mock (Simulation)",
        "asset_type": asset_type,
    }


def is_crypto(ticker: str) -> bool:
    """Detects if a ticker is a crypto pair (e.g. BTC/USDT)."""
    return "/" in ticker or "-USD" in ticker.upper()


def execute_trade(ticker: str, position: dict) -> dict:
    """
    Unified entry point — routes to stock or crypto executor automatically.
    """
    if is_crypto(ticker):
        return place_crypto_order(ticker, position)
    else:
        return place_stock_order(ticker, position)
