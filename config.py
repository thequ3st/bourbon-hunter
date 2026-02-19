import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Scan settings
    SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "120"))
    REQUEST_DELAY_SECONDS = float(os.getenv("REQUEST_DELAY_SECONDS", "2.5"))

    # FWGS URLs
    FWGS_BASE_URL = os.getenv("FWGS_BASE_URL", "https://www.finewineandgoodspirits.com")
    FWGS_SEARCH_URL = f"{FWGS_BASE_URL}/search"
    FWGS_BOURBON_URL = f"{FWGS_BASE_URL}/bourbon/152"
    FWGS_LEGACY_URL = os.getenv("FWGS_LEGACY_URL", "https://www.lcbapps.lcb.state.pa.us")
    FWGS_LEGACY_INVENTORY_URL = f"{FWGS_LEGACY_URL}/webapp/Product_Management/psi_ProductInventory_Inter.asp"
    FWGS_LEGACY_SEARCH_URL = f"{FWGS_LEGACY_URL}/webapp/product_management/psi_productdefault_inter.asp"
    FWGS_STORE_URL = f"{FWGS_LEGACY_URL}/app/retail/storeloc.asp"

    # User agent for polite scraping
    USER_AGENT = "PA-Bourbon-Hunter/1.0 (Personal Use; Inventory Tracker)"

    # Email
    EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    EMAIL_TO = os.getenv("EMAIL_TO", "")

    # SMS (Twilio)
    SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() == "true"
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
    SMS_TO_NUMBER = os.getenv("SMS_TO_NUMBER", "")

    # Discord
    DISCORD_ENABLED = os.getenv("DISCORD_ENABLED", "false").lower() == "true"
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Slack
    SLACK_ENABLED = os.getenv("SLACK_ENABLED", "false").lower() == "true"
    SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "bourbon_hunter.db")

    # Notification rate limiting (hours between repeat alerts for same product)
    ALERT_COOLDOWN_HOURS = 6

    # Tier notification defaults
    TIER_NOTIFICATION_MAP = {
        1: ["email", "sms", "discord", "slack", "dashboard"],
        2: ["email", "sms", "discord", "slack", "dashboard"],
        3: ["email", "discord", "dashboard"],
        4: ["dashboard"],
    }
