import logging
from config import Config

logger = logging.getLogger(__name__)


def send_sms(message):
    if not Config.SMS_ENABLED:
        logger.debug("SMS disabled, skipping")
        return False

    if not all([Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN,
                Config.TWILIO_FROM_NUMBER, Config.SMS_TO_NUMBER]):
        logger.warning("Twilio config incomplete")
        return False

    try:
        from twilio.rest import Client
        client = Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=message,
            from_=Config.TWILIO_FROM_NUMBER,
            to=Config.SMS_TO_NUMBER,
        )
        logger.info("SMS sent successfully")
        return True
    except ImportError:
        logger.error("twilio package not installed. Run: pip install twilio")
        return False
    except Exception as e:
        logger.error(f"SMS failed: {e}")
        return False


def format_bourbon_alert_sms(bourbon, product, store):
    tier_labels = {1: "UNICORN", 2: "ALLOCATED", 3: "FOUND", 4: "TRACKED"}
    tier = bourbon.get("rarity_tier", 4)
    tier_label = tier_labels.get(tier, "")

    return (
        f"[{tier_label}] {bourbon['name']}\n"
        f"${product.get('price', '?')} @ {store.get('store_name', '?')} "
        f"(#{store.get('store_number', '?')})\n"
        f"Qty: {store.get('quantity', '?')} | "
        f"Rating: {bourbon.get('average_rating', '?')}/10"
    )
