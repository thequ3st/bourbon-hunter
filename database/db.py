import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bourbon_hunter.db")


def get_connection(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db(db_path=None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path=None):
    with get_db(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bourbons (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                distillery TEXT,
                type TEXT DEFAULT 'bourbon',
                proof REAL,
                age TEXT,
                msrp REAL,
                rarity_tier INTEGER NOT NULL DEFAULT 4,
                average_rating REAL,
                search_terms TEXT,
                notes TEXT,
                annual_release INTEGER DEFAULT 0,
                release_window TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS fwgs_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fwgs_code TEXT,
                name TEXT NOT NULL,
                price REAL,
                size TEXT,
                proof REAL,
                url TEXT,
                bourbon_id TEXT REFERENCES bourbons(id),
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(fwgs_code)
            );

            CREATE TABLE IF NOT EXISTS inventory_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fwgs_product_id INTEGER REFERENCES fwgs_products(id),
                store_number TEXT,
                store_name TEXT,
                store_address TEXT,
                quantity INTEGER DEFAULT 0,
                scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                products_found INTEGER DEFAULT 0,
                new_finds INTEGER DEFAULT 0,
                errors TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS alerts_sent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bourbon_id TEXT REFERENCES bourbons(id),
                fwgs_product_id INTEGER REFERENCES fwgs_products(id),
                channel TEXT NOT NULL,
                message TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory_snapshots(fwgs_product_id);
            CREATE INDEX IF NOT EXISTS idx_inventory_store ON inventory_snapshots(store_number);
            CREATE INDEX IF NOT EXISTS idx_inventory_time ON inventory_snapshots(scanned_at);
            CREATE INDEX IF NOT EXISTS idx_alerts_bourbon ON alerts_sent(bourbon_id, sent_at);
            CREATE INDEX IF NOT EXISTS idx_fwgs_bourbon ON fwgs_products(bourbon_id);
            CREATE INDEX IF NOT EXISTS idx_scan_log_time ON scan_log(started_at);
        """)
