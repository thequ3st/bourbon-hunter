import json
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from config import Config
from database.db import init_db
from database.models import (
    get_all_bourbons, get_latest_inventory, get_scan_history,
    get_dashboard_stats, get_setting, set_setting, get_bourbon_images,
)
from knowledge.bourbon_db import (
    sync_knowledge_base_to_db, get_knowledge_base_stats,
    load_knowledge_base, get_tier_label,
)
from scanner.fwgs_scraper import FWGSScanner
from scanner.store_locator import (
    geocode_zip, get_nearby_stores, get_store_info, fetch_all_stores,
    haversine_miles,
)
from notifications.notifier import notify_scan_results, test_notifications

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Scanner state
scanner_lock = threading.Lock()
scanner_running = False
last_scan_result = None


def init_app():
    """Initialize database and sync knowledge base."""
    init_db()
    Config.load_db_settings()
    count = sync_knowledge_base_to_db()
    logger.info(f"Synced {count} bourbons to database")


# --- Web Routes ---

@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/settings")
def settings_page():
    return render_template("settings.html")


# --- API Routes ---

@app.route("/api/stats")
def api_stats():
    stats = get_dashboard_stats()
    kb_stats = get_knowledge_base_stats()
    stats["knowledge_base"] = kb_stats
    return jsonify(stats)


@app.route("/api/bourbons")
def api_bourbons():
    tier = request.args.get("tier", type=int)
    bourbons = load_knowledge_base()["bourbons"]
    if tier:
        bourbons = [b for b in bourbons if b["rarity_tier"] == tier]
    # Add tier labels and product images
    images = get_bourbon_images()
    for b in bourbons:
        b["tier_label"] = get_tier_label(b["rarity_tier"])
        b["image_url"] = images.get(b["id"])
    return jsonify(bourbons)


@app.route("/api/inventory")
def api_inventory():
    bourbon_id = request.args.get("bourbon_id")
    inventory = get_latest_inventory(bourbon_id)
    return jsonify(inventory)


@app.route("/api/inventory/nearby")
def api_inventory_nearby():
    """Get inventory filtered by proximity to a zip code or lat/lng."""
    zip_code = request.args.get("zip", "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", 25, type=float)

    if zip_code:
        lat, lng = geocode_zip(zip_code)
        if lat is None:
            return jsonify({"error": f"Could not locate zip code {zip_code}"}), 400
    elif lat is None or lng is None:
        return jsonify({"error": "Provide zip or lat/lng parameters"}), 400

    # Get stores within radius
    nearby = get_nearby_stores(lat, lng, radius_miles=radius)
    nearby_ids = {s["store_number"] for s in nearby}
    dist_map = {s["store_number"]: s["distance_miles"] for s in nearby}

    # Get inventory and filter to nearby stores
    inventory = get_latest_inventory()
    filtered = []
    for item in inventory:
        snum = item.get("store_number", "")
        if snum in nearby_ids:
            item["distance_miles"] = dist_map.get(snum, 0)
            # Enrich with store details
            store = get_store_info(snum)
            if store:
                item["county"] = store.get("county", "")
                item["store_hours"] = store.get("hours", "")
                item["store_phone"] = store.get("phone", "")
            filtered.append(item)

    filtered.sort(key=lambda x: (x.get("distance_miles", 999)))
    return jsonify({
        "location": {"lat": lat, "lng": lng, "zip": zip_code, "radius": radius},
        "stores_in_range": len(nearby),
        "inventory": filtered,
    })


@app.route("/api/stores/nearby")
def api_stores_nearby():
    """Get store locations near a zip code or lat/lng (no inventory filter)."""
    zip_code = request.args.get("zip", "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", 25, type=float)

    if zip_code:
        lat, lng = geocode_zip(zip_code)
        if lat is None:
            return jsonify({"error": f"Could not locate zip code {zip_code}"}), 400
    elif lat is None or lng is None:
        return jsonify({"error": "Provide zip or lat/lng parameters"}), 400

    nearby = get_nearby_stores(lat, lng, radius_miles=radius)
    return jsonify({
        "location": {"lat": lat, "lng": lng, "zip": zip_code, "radius": radius},
        "stores": nearby,
    })


@app.route("/api/scan/history")
def api_scan_history():
    limit = request.args.get("limit", 20, type=int)
    history = get_scan_history(limit)
    return jsonify(history)


@app.route("/api/scan/start", methods=["POST"])
def api_start_scan():
    global scanner_running, last_scan_result

    if scanner_running:
        return jsonify({"error": "Scan already in progress"}), 409

    scan_type = request.json.get("type", "full") if request.is_json else "full"
    tier = request.json.get("tier") if request.is_json else None

    def run_scan():
        global scanner_running, last_scan_result
        try:
            scanner = FWGSScanner()
            if scan_type == "quick":
                result = scanner.run_quick_scan(tier=tier)
            else:
                result = scanner.run_full_scan()

            last_scan_result = result

            # Send notifications for new finds
            if result.get("new_finds", 0) > 0:
                notify_scan_results(result)

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            last_scan_result = {"error": str(e)}
        finally:
            with scanner_lock:
                scanner_running = False

    with scanner_lock:
        scanner_running = True

    thread = threading.Thread(target=run_scan, daemon=True)
    thread.start()

    return jsonify({"status": "started", "type": scan_type})


@app.route("/api/scan/status")
def api_scan_status():
    return jsonify({
        "running": scanner_running,
        "last_result": last_scan_result,
    })


@app.route("/api/search", methods=["POST"])
def api_search():
    term = request.json.get("term", "") if request.is_json else ""
    if not term:
        return jsonify({"error": "Search term required"}), 400

    scanner = FWGSScanner()
    products = scanner.search_single_product(term)
    return jsonify(products)


@app.route("/api/notifications/test", methods=["POST"])
def api_test_notifications():
    results = test_notifications()
    return jsonify(results)


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    settings = {
        # Email
        "email_enabled": Config.EMAIL_ENABLED,
        "smtp_host": Config.SMTP_HOST,
        "smtp_port": Config.SMTP_PORT,
        "smtp_user": Config.SMTP_USER,
        "smtp_password": "••••••••" if Config.SMTP_PASSWORD else "",
        "email_to": Config.EMAIL_TO,
        # SMS
        "sms_enabled": Config.SMS_ENABLED,
        "twilio_account_sid": Config.TWILIO_ACCOUNT_SID,
        "twilio_auth_token": "••••••••" if Config.TWILIO_AUTH_TOKEN else "",
        "twilio_from_number": Config.TWILIO_FROM_NUMBER,
        "sms_to_number": Config.SMS_TO_NUMBER,
        # Discord
        "discord_enabled": Config.DISCORD_ENABLED,
        "discord_webhook_url": Config.DISCORD_WEBHOOK_URL,
        # Slack
        "slack_enabled": Config.SLACK_ENABLED,
        "slack_webhook_url": Config.SLACK_WEBHOOK_URL,
        # Scan
        "scan_interval": Config.SCAN_INTERVAL_MINUTES,
        "alert_cooldown": Config.ALERT_COOLDOWN_HOURS,
        "request_delay": Config.REQUEST_DELAY_SECONDS,
        # Tier map
        "tier_map": Config.TIER_NOTIFICATION_MAP,
    }
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Mask-aware: skip password fields if they're still the masked value
    for key, value in data.items():
        if isinstance(value, str) and value == "••••••••":
            continue
        db_val = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        set_setting(key, db_val)
        Config.apply_setting(key, db_val)

    return jsonify({"status": "updated"})


# --- Scheduler ---

def start_scheduler():
    """Start background scan scheduler."""
    import schedule
    import time

    def scheduled_scan():
        global scanner_running, last_scan_result
        if scanner_running:
            logger.info("Scheduled scan skipped — already running")
            return
        with scanner_lock:
            scanner_running = True
        try:
            scanner = FWGSScanner()
            result = scanner.run_full_scan()
            last_scan_result = result
            if result.get("new_finds", 0) > 0:
                notify_scan_results(result)
        except Exception as e:
            logger.error(f"Scheduled scan failed: {e}")
        finally:
            with scanner_lock:
                scanner_running = False

    interval = Config.SCAN_INTERVAL_MINUTES
    schedule.every(interval).minutes.do(scheduled_scan)
    logger.info(f"Scheduler started: scanning every {interval} minutes")

    def scheduler_loop():
        while True:
            schedule.run_pending()
            time.sleep(30)

    thread = threading.Thread(target=scheduler_loop, daemon=True)
    thread.start()


if __name__ == "__main__":
    init_app()
    start_scheduler()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
