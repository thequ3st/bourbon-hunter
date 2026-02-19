import json
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request
from config import Config
from database.db import init_db
from database.models import (
    get_all_bourbons, get_latest_inventory, get_scan_history,
    get_dashboard_stats, get_setting, set_setting,
)
from knowledge.bourbon_db import (
    sync_knowledge_base_to_db, get_knowledge_base_stats,
    load_knowledge_base, get_tier_label,
)
from scanner.fwgs_scraper import FWGSScanner
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
    # Add tier labels
    for b in bourbons:
        b["tier_label"] = get_tier_label(b["rarity_tier"])
    return jsonify(bourbons)


@app.route("/api/inventory")
def api_inventory():
    bourbon_id = request.args.get("bourbon_id")
    inventory = get_latest_inventory(bourbon_id)
    return jsonify(inventory)


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
        "email_enabled": Config.EMAIL_ENABLED,
        "sms_enabled": Config.SMS_ENABLED,
        "discord_enabled": Config.DISCORD_ENABLED,
        "slack_enabled": Config.SLACK_ENABLED,
        "scan_interval": Config.SCAN_INTERVAL_MINUTES,
        "alert_cooldown": Config.ALERT_COOLDOWN_HOURS,
        "tier_map": Config.TIER_NOTIFICATION_MAP,
    }
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    for key, value in data.items():
        set_setting(key, json.dumps(value) if isinstance(value, (dict, list)) else str(value))

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
