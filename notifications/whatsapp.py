"""
notifications/whatsapp.py — WhatsApp trade alerts via Twilio.

Setup (free):
1. Go to twilio.com → sign up free
2. Go to Messaging → Try it out → Send a WhatsApp message
3. Follow the sandbox instructions (send a message to the Twilio number)
4. Add your credentials to .env
"""

import os
from datetime import datetime
from config import MOCK_MODE

TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM  = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
WHATSAPP_TO  = os.getenv("WHATSAPP_TO", "")

_PLACEHOLDERS = {"your_twilio_sid", "your_twilio_token", "your_whatsapp_number", ""}


def _is_configured() -> bool:
    return (
        TWILIO_SID not in _PLACEHOLDERS and
        TWILIO_TOKEN not in _PLACEHOLDERS and
        WHATSAPP_TO not in _PLACEHOLDERS
    )


def send_trade_alert(order: dict, analysis: dict, position: dict) -> dict:
    """Send a WhatsApp message when FRIDAY places a trade."""
    ticker     = order.get("ticker", "?")
    action     = "BUY"
    entry      = position.get("entry_price", 0)
    stop       = position.get("stop_loss", 0)
    target     = position.get("take_profit", 0)
    shares     = position.get("shares", 0)
    cost       = position.get("total_cost", 0)
    rr         = position.get("risk_reward_ratio", 0)
    conf       = analysis.get("confidence", 0)
    reason     = analysis.get("reasoning", "")[:120]
    broker     = order.get("broker", "Paper")
    ts         = datetime.now().strftime("%d %b %Y %H:%M")

    msg = (
        f"🤖 *F.R.I.D.A.Y Trade Alert*\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📌 *{action}* {ticker}\n"
        f"🕐 {ts}\n\n"
        f"💰 Entry:  ${entry}\n"
        f"🛑 Stop:   ${stop}\n"
        f"🎯 Target: ${target}\n"
        f"📦 Shares: {shares}  |  Cost: ${cost}\n"
        f"⚖️  R/R: {rr}x  |  Conf: {conf}%\n\n"
        f"📝 _{reason}_\n\n"
        f"🏦 Broker: {broker}"
    )

    if MOCK_MODE or not _is_configured():
        print(f"[WhatsApp MOCK] Would send:\n{msg}")
        return {"status": "mock", "message": msg}

    try:
        from twilio.rest import Client
        client  = Client(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=msg,
            from_=TWILIO_FROM,
            to=f"whatsapp:{WHATSAPP_TO}",
        )
        return {"status": "sent", "sid": message.sid}
    except ImportError:
        return {"status": "error", "error": "twilio not installed. Run: pip install twilio"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def send_custom_message(text: str) -> dict:
    """Send any custom WhatsApp message (for test button)."""
    if MOCK_MODE or not _is_configured():
        return {"status": "mock", "message": text}
    try:
        from twilio.rest import Client
        client  = Client(TWILIO_SID, TWILIO_TOKEN)
        message = client.messages.create(
            body=text, from_=TWILIO_FROM, to=f"whatsapp:{WHATSAPP_TO}",
        )
        return {"status": "sent", "sid": message.sid}
    except Exception as e:
        return {"status": "error", "error": str(e)}
