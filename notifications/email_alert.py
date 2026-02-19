import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config

logger = logging.getLogger(__name__)


def send_email(subject, html_body, text_body=None):
    if not Config.EMAIL_ENABLED:
        logger.debug("Email disabled, skipping")
        return False

    if not all([Config.SMTP_USER, Config.SMTP_PASSWORD, Config.EMAIL_TO]):
        logger.warning("Email config incomplete")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = Config.SMTP_USER
        msg["To"] = Config.EMAIL_TO

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        logger.error(f"Email failed: {e}")
        return False


def format_bourbon_alert_email(bourbon, product, store):
    tier_labels = {1: "UNICORN", 2: "HIGHLY ALLOCATED", 3: "ALLOCATED", 4: "WORTH TRACKING"}
    tier = bourbon.get("rarity_tier", 4)
    tier_label = tier_labels.get(tier, "TRACKED")
    tier_colors = {1: "#ff0000", 2: "#ff6600", 3: "#ffaa00", 4: "#00aa00"}
    color = tier_colors.get(tier, "#666")

    subject = f"[Bourbon Hunter] {tier_label}: {bourbon['name']} in stock!"

    html = f"""
    <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto;
                background: #1a1a2e; color: #eee; padding: 20px; border-radius: 8px;">
        <h1 style="color: #d4a574; margin: 0 0 10px;">PA Bourbon Hunter</h1>
        <div style="background: {color}; color: white; display: inline-block;
                    padding: 4px 12px; border-radius: 4px; font-weight: bold;
                    font-size: 12px; margin-bottom: 15px;">
            TIER {tier} — {tier_label}
        </div>
        <h2 style="color: #fff; margin: 10px 0;">{bourbon['name']}</h2>
        <p style="color: #aaa;">{bourbon.get('distillery', 'Unknown Distillery')}</p>
        <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #333; color: #888;">Price</td>
                <td style="padding: 8px; border-bottom: 1px solid #333;">
                    ${product.get('price', 'N/A')}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #333; color: #888;">Store</td>
                <td style="padding: 8px; border-bottom: 1px solid #333;">
                    {store.get('store_name', 'Unknown')} (#{store.get('store_number', '?')})</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #333; color: #888;">Address</td>
                <td style="padding: 8px; border-bottom: 1px solid #333;">
                    {store.get('store_address', 'N/A')}</td>
            </tr>
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #333; color: #888;">Quantity</td>
                <td style="padding: 8px; border-bottom: 1px solid #333;">
                    {store.get('quantity', '?')} units</td>
            </tr>
            <tr>
                <td style="padding: 8px; color: #888;">Rating</td>
                <td style="padding: 8px;">{bourbon.get('average_rating', 'N/A')}/10</td>
            </tr>
        </table>
        <p style="color: #888; font-size: 12px; margin-top: 20px;">
            MSRP: ${bourbon.get('msrp', 'N/A')} |
            Proof: {bourbon.get('proof', 'N/A')} |
            Age: {bourbon.get('age', 'NAS')}
        </p>
        <p style="color: #555; font-size: 11px; margin-top: 20px;">
            PA Bourbon Hunter — Automated inventory alert
        </p>
    </div>
    """

    text = (
        f"[BOURBON HUNTER] {tier_label}: {bourbon['name']}\n\n"
        f"Store: {store.get('store_name', 'Unknown')} (#{store.get('store_number', '?')})\n"
        f"Address: {store.get('store_address', 'N/A')}\n"
        f"Quantity: {store.get('quantity', '?')}\n"
        f"Price: ${product.get('price', 'N/A')}\n"
        f"Rating: {bourbon.get('average_rating', 'N/A')}/10\n"
    )

    return subject, html, text
