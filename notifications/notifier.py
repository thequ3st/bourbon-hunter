import logging
from config import Config
from database.models import can_send_alert, log_alert_sent
from notifications.email_alert import send_email, format_bourbon_alert_email
from notifications.sms_alert import send_sms, format_bourbon_alert_sms
from notifications.discord_alert import send_discord, format_bourbon_alert_discord
from notifications.slack_alert import send_slack, format_bourbon_alert_slack

logger = logging.getLogger(__name__)


def notify_new_find(bourbon, product, store):
    """Send notifications for a new bourbon find across all configured channels."""
    tier = bourbon.get("rarity_tier", 4)
    channels = Config.TIER_NOTIFICATION_MAP.get(tier, ["dashboard"])
    bourbon_id = bourbon.get("id", "unknown")
    fwgs_product_id = product.get("db_id")
    sent_channels = []

    for channel in channels:
        if channel == "dashboard":
            # Dashboard is always available (handled by the web UI)
            continue

        if not can_send_alert(bourbon_id, channel, Config.ALERT_COOLDOWN_HOURS):
            logger.debug(f"Alert cooldown active for {bourbon_id} on {channel}")
            continue

        success = False
        message = ""

        if channel == "email":
            subject, html, text = format_bourbon_alert_email(bourbon, product, store)
            success = send_email(subject, html, text)
            message = subject

        elif channel == "sms":
            message = format_bourbon_alert_sms(bourbon, product, store)
            success = send_sms(message)

        elif channel == "discord":
            embed = format_bourbon_alert_discord(bourbon, product, store)
            success = send_discord(embed)
            message = f"Discord: {bourbon['name']}"

        elif channel == "slack":
            blocks = format_bourbon_alert_slack(bourbon, product, store)
            success = send_slack(blocks)
            message = f"Slack: {bourbon['name']}"

        if success:
            log_alert_sent(bourbon_id, fwgs_product_id, channel, message)
            sent_channels.append(channel)
            logger.info(f"Alert sent via {channel} for {bourbon['name']}")

    return sent_channels


def notify_scan_results(scan_results):
    """Process scan results and send notifications for all new finds."""
    new_finds = scan_results.get("new_finds_detail", [])
    if not new_finds:
        return []

    all_sent = []
    for find in new_finds:
        channels = notify_new_find(find["bourbon"], find["product"], find["store"])
        all_sent.append({
            "bourbon": find["bourbon"]["name"],
            "channels": channels,
        })

    return all_sent


def test_notifications():
    """Send a test notification on all enabled channels."""
    test_bourbon = {
        "id": "test",
        "name": "Test Bourbon (Not Real)",
        "distillery": "Test Distillery",
        "rarity_tier": 3,
        "average_rating": 8.0,
        "proof": 100.0,
        "age": "10 years",
        "msrp": 49.99,
    }
    test_product = {"price": 49.99, "fwgs_code": "99999", "db_id": None}
    test_store = {
        "store_name": "Test Store",
        "store_number": "0000",
        "store_address": "123 Test St, Philadelphia, PA 19103",
        "quantity": 3,
    }

    results = {}

    if Config.EMAIL_ENABLED:
        subject, html, text = format_bourbon_alert_email(test_bourbon, test_product, test_store)
        results["email"] = send_email(subject, html, text)

    if Config.SMS_ENABLED:
        msg = format_bourbon_alert_sms(test_bourbon, test_product, test_store)
        results["sms"] = send_sms(msg)

    if Config.DISCORD_ENABLED:
        embed = format_bourbon_alert_discord(test_bourbon, test_product, test_store)
        results["discord"] = send_discord(embed)

    if Config.SLACK_ENABLED:
        blocks = format_bourbon_alert_slack(test_bourbon, test_product, test_store)
        results["slack"] = send_slack(blocks)

    return results
