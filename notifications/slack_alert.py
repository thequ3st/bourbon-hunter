import logging
import requests
from config import Config

logger = logging.getLogger(__name__)


def send_slack(blocks):
    if not Config.SLACK_ENABLED:
        logger.debug("Slack disabled, skipping")
        return False

    if not Config.SLACK_WEBHOOK_URL:
        logger.warning("Slack webhook URL not configured")
        return False

    try:
        payload = {"blocks": blocks}
        resp = requests.post(
            Config.SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Slack alert sent")
        return True
    except Exception as e:
        logger.error(f"Slack alert failed: {e}")
        return False


def format_bourbon_alert_slack(bourbon, product, store):
    tier_emojis = {1: ":unicorn:", 2: ":fire:", 3: ":mag:", 4: ":white_check_mark:"}
    tier_labels = {1: "UNICORN", 2: "HIGHLY ALLOCATED", 3: "ALLOCATED", 4: "WORTH TRACKING"}
    tier = bourbon.get("rarity_tier", 4)
    emoji = tier_emojis.get(tier, ":whisky:")

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{bourbon['name']}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *{tier_labels.get(tier, 'TRACKED')}* — Tier {tier}\n"
                    f"_{bourbon.get('distillery', 'Unknown')}_"
                ),
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Store:*\n{store.get('store_name', '?')} (#{store.get('store_number', '?')})"},
                {"type": "mrkdwn", "text": f"*Qty:*\n{store.get('quantity', '?')}"},
                {"type": "mrkdwn", "text": f"*Price:*\n${product.get('price', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Rating:*\n{bourbon.get('average_rating', 'N/A')}/10"},
                {"type": "mrkdwn", "text": f"*Proof:*\n{bourbon.get('proof', 'N/A')}"},
                {"type": "mrkdwn", "text": f"*Address:*\n{store.get('store_address', 'N/A')}"},
            ],
        },
        {"type": "divider"},
    ]
