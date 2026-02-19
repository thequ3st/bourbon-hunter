import logging
import requests
from config import Config

logger = logging.getLogger(__name__)


def send_discord(embed_data):
    if not Config.DISCORD_ENABLED:
        logger.debug("Discord disabled, skipping")
        return False

    if not Config.DISCORD_WEBHOOK_URL:
        logger.warning("Discord webhook URL not configured")
        return False

    try:
        payload = {"embeds": [embed_data]}
        resp = requests.post(
            Config.DISCORD_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Discord alert sent")
        return True
    except Exception as e:
        logger.error(f"Discord alert failed: {e}")
        return False


def format_bourbon_alert_discord(bourbon, product, store):
    tier_colors = {1: 0xFF0000, 2: 0xFF6600, 3: 0xFFAA00, 4: 0x00AA00}
    tier_labels = {1: "UNICORN", 2: "HIGHLY ALLOCATED", 3: "ALLOCATED", 4: "WORTH TRACKING"}
    tier = bourbon.get("rarity_tier", 4)

    return {
        "title": f"{bourbon['name']}",
        "description": (
            f"**{tier_labels.get(tier, 'TRACKED')}** — Tier {tier}\n"
            f"{bourbon.get('distillery', 'Unknown Distillery')}"
        ),
        "color": tier_colors.get(tier, 0x666666),
        "fields": [
            {"name": "Store", "value": f"{store.get('store_name', '?')} (#{store.get('store_number', '?')})", "inline": True},
            {"name": "Quantity", "value": str(store.get("quantity", "?")), "inline": True},
            {"name": "Price", "value": f"${product.get('price', 'N/A')}", "inline": True},
            {"name": "Rating", "value": f"{bourbon.get('average_rating', 'N/A')}/10", "inline": True},
            {"name": "Proof", "value": str(bourbon.get("proof", "N/A")), "inline": True},
            {"name": "Age", "value": bourbon.get("age", "NAS"), "inline": True},
            {"name": "Address", "value": store.get("store_address", "N/A"), "inline": False},
        ],
        "footer": {"text": "PA Bourbon Hunter"},
    }
