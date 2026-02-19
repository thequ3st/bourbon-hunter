from datetime import datetime, timedelta
from database.db import get_db


def upsert_bourbon(bourbon_data):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO bourbons (id, name, distillery, type, proof, age, msrp,
                                  rarity_tier, average_rating, search_terms, notes,
                                  annual_release, release_window)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, distillery=excluded.distillery,
                proof=excluded.proof, age=excluded.age, msrp=excluded.msrp,
                rarity_tier=excluded.rarity_tier, average_rating=excluded.average_rating,
                search_terms=excluded.search_terms, notes=excluded.notes,
                annual_release=excluded.annual_release, release_window=excluded.release_window,
                updated_at=CURRENT_TIMESTAMP
        """, (
            bourbon_data["id"], bourbon_data["name"], bourbon_data.get("distillery"),
            bourbon_data.get("type", "bourbon"), bourbon_data.get("proof"),
            bourbon_data.get("age"), bourbon_data.get("msrp"),
            bourbon_data.get("rarity_tier", 4), bourbon_data.get("average_rating"),
            ",".join(bourbon_data.get("search_terms", [])),
            bourbon_data.get("notes"), bourbon_data.get("annual_release", False),
            bourbon_data.get("release_window")
        ))


def upsert_fwgs_product(product_data):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO fwgs_products (fwgs_code, name, price, size, proof, url, bourbon_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fwgs_code) DO UPDATE SET
                name=excluded.name, price=excluded.price, size=excluded.size,
                proof=excluded.proof, url=excluded.url, bourbon_id=excluded.bourbon_id,
                last_seen=CURRENT_TIMESTAMP
        """, (
            product_data.get("fwgs_code"), product_data["name"],
            product_data.get("price"), product_data.get("size"),
            product_data.get("proof"), product_data.get("url"),
            product_data.get("bourbon_id")
        ))
        row = conn.execute(
            "SELECT id FROM fwgs_products WHERE fwgs_code = ?",
            (product_data.get("fwgs_code"),)
        ).fetchone()
        return row["id"] if row else None


def add_inventory_snapshot(fwgs_product_id, store_number, store_name, store_address, quantity):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO inventory_snapshots
                (fwgs_product_id, store_number, store_name, store_address, quantity)
            VALUES (?, ?, ?, ?, ?)
        """, (fwgs_product_id, store_number, store_name, store_address, quantity))


def get_latest_inventory(bourbon_id=None):
    with get_db() as conn:
        query = """
            SELECT fp.name, fp.fwgs_code, fp.price, fp.url, fp.bourbon_id,
                   inv.store_number, inv.store_name, inv.store_address,
                   inv.quantity, inv.scanned_at,
                   b.rarity_tier, b.average_rating, b.distillery
            FROM inventory_snapshots inv
            JOIN fwgs_products fp ON inv.fwgs_product_id = fp.id
            LEFT JOIN bourbons b ON fp.bourbon_id = b.id
            WHERE inv.scanned_at = (
                SELECT MAX(inv2.scanned_at) FROM inventory_snapshots inv2
                WHERE inv2.fwgs_product_id = inv.fwgs_product_id
                  AND inv2.store_number = inv.store_number
            )
            AND inv.quantity > 0
        """
        params = []
        if bourbon_id:
            query += " AND fp.bourbon_id = ?"
            params.append(bourbon_id)
        query += " ORDER BY b.rarity_tier ASC, inv.scanned_at DESC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]


def check_is_new_find(fwgs_code, store_number):
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM inventory_snapshots inv
            JOIN fwgs_products fp ON inv.fwgs_product_id = fp.id
            WHERE fp.fwgs_code = ? AND inv.store_number = ?
              AND inv.quantity > 0
              AND inv.scanned_at > datetime('now', '-24 hours')
        """, (fwgs_code, store_number)).fetchone()
        return row["cnt"] == 0


def log_scan_start(scan_type):
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO scan_log (scan_type, status) VALUES (?, 'running')",
            (scan_type,)
        )
        return cursor.lastrowid


def log_scan_complete(scan_id, products_found, new_finds, errors=None):
    with get_db() as conn:
        conn.execute("""
            UPDATE scan_log SET status='completed', products_found=?,
                   new_finds=?, errors=?, completed_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (products_found, new_finds, errors, scan_id))


def log_scan_error(scan_id, error_msg):
    with get_db() as conn:
        conn.execute("""
            UPDATE scan_log SET status='error', errors=?, completed_at=CURRENT_TIMESTAMP
            WHERE id=?
        """, (error_msg, scan_id))


def can_send_alert(bourbon_id, channel, cooldown_hours=6):
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) as cnt FROM alerts_sent
            WHERE bourbon_id = ? AND channel = ?
              AND sent_at > datetime('now', ? || ' hours')
        """, (bourbon_id, channel, f"-{cooldown_hours}")).fetchone()
        return row["cnt"] == 0


def log_alert_sent(bourbon_id, fwgs_product_id, channel, message):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO alerts_sent (bourbon_id, fwgs_product_id, channel, message)
            VALUES (?, ?, ?, ?)
        """, (bourbon_id, fwgs_product_id, channel, message))


def get_scan_history(limit=20):
    with get_db() as conn:
        return [dict(row) for row in conn.execute("""
            SELECT * FROM scan_log ORDER BY started_at DESC LIMIT ?
        """, (limit,)).fetchall()]


def get_all_bourbons():
    with get_db() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM bourbons ORDER BY rarity_tier ASC, average_rating DESC"
        ).fetchall()]


def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM user_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO user_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
        """, (key, value))


def get_dashboard_stats():
    with get_db() as conn:
        total_tracked = conn.execute("SELECT COUNT(*) as cnt FROM bourbons").fetchone()["cnt"]
        in_stock = conn.execute("""
            SELECT COUNT(DISTINCT fp.bourbon_id) as cnt
            FROM fwgs_products fp
            JOIN inventory_snapshots inv ON inv.fwgs_product_id = fp.id
            WHERE inv.quantity > 0
              AND inv.scanned_at > datetime('now', '-24 hours')
        """).fetchone()["cnt"]
        last_scan = conn.execute(
            "SELECT * FROM scan_log ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        total_alerts = conn.execute(
            "SELECT COUNT(*) as cnt FROM alerts_sent WHERE sent_at > datetime('now', '-24 hours')"
        ).fetchone()["cnt"]
        return {
            "total_tracked": total_tracked,
            "in_stock": in_stock,
            "last_scan": dict(last_scan) if last_scan else None,
            "alerts_today": total_alerts,
        }
