import time
import logging
import requests
from config import Config
from scanner.product_parser import parse_fwgs_search_results
from scanner.store_locator import get_session, check_store_stock, fetch_all_stores
from knowledge.bourbon_db import get_search_terms_by_tier, match_product_to_bourbon
from database.models import (
    upsert_fwgs_product,
    add_inventory_snapshot,
    check_is_new_find,
    log_scan_start,
    log_scan_complete,
    log_scan_error,
)

logger = logging.getLogger(__name__)


class FWGSScanner:
    def __init__(self, on_progress=None):
        self.session = get_session()
        self.delay = Config.REQUEST_DELAY_SECONDS
        self.new_finds = []
        self._on_progress = on_progress or (lambda p: None)

    def run_full_scan(self):
        """Run a complete scan: search for all tracked bourbons."""
        scan_id = log_scan_start("full_scan")
        total_found = 0
        new_finds_count = 0

        try:
            # Pre-load store locations for per-store inventory lookups
            fetch_all_stores(self.session)
            search_terms = get_search_terms_by_tier(max_tier=4)
            total_found, new_finds_count = self._scan_terms(search_terms)
            log_scan_complete(scan_id, total_found, new_finds_count)
            logger.info(f"Scan complete: {total_found} products, {new_finds_count} new finds")
        except Exception as e:
            logger.error(f"Scan error: {e}")
            log_scan_error(scan_id, str(e))
            raise

        return {
            "scan_id": scan_id,
            "products_found": total_found,
            "new_finds": new_finds_count,
            "new_finds_detail": self.new_finds,
        }

    def run_quick_scan(self, tier=None):
        """Quick scan for specific tier(s) only."""
        max_tier = tier or 2
        scan_id = log_scan_start(f"quick_scan_tier_{max_tier}")
        total_found = 0
        new_finds_count = 0

        try:
            fetch_all_stores(self.session)
            search_terms = get_search_terms_by_tier(max_tier=max_tier)
            total_found, new_finds_count = self._scan_terms(search_terms)
            log_scan_complete(scan_id, total_found, new_finds_count)
        except Exception as e:
            log_scan_error(scan_id, str(e))
            raise

        return {
            "scan_id": scan_id,
            "products_found": total_found,
            "new_finds": new_finds_count,
            "new_finds_detail": self.new_finds,
        }

    def _scan_terms(self, search_terms):
        """Core scan loop shared by full and quick scan."""
        total_found = 0
        new_finds_count = 0
        seen_terms = set()
        seen_codes = set()
        # Collect matched products for per-store stock check
        stock_check_queue = []

        # Deduplicate terms first so we know the true count
        unique_terms = []
        for entry in search_terms:
            t = entry["term"].lower()
            if t not in seen_terms:
                seen_terms.add(t)
                unique_terms.append(entry)
        total_terms = len(unique_terms)

        for idx, entry in enumerate(unique_terms):
            term = entry["term"]

            self._on_progress({
                "phase": "search",
                "current": idx + 1,
                "total": total_terms,
                "detail": term,
            })

            logger.info(f"Searching FWGS for: {term}")
            products = self._search_fwgs(term)

            for product in products:
                code = product.get("fwgs_code", "")
                if code in seen_codes:
                    continue
                seen_codes.add(code)

                # Skip products that are clearly not bourbon/whiskey
                category = (product.get("category") or "").lower()
                if category and category not in (
                    "", "bourbon", "whiskey", "rye whiskey",
                    "american whiskey", "spirits",
                ):
                    continue

                # Match to knowledge base
                matched = match_product_to_bourbon(product["name"])
                if matched:
                    product["bourbon_id"] = matched["id"]

                product_id = upsert_fwgs_product(product)
                if product_id:
                    total_found += 1

                    # Queue matched in-stock products for per-store check
                    if matched and product.get("in_stock"):
                        stock_check_queue.append({
                            "product_id": product_id,
                            "product": product,
                            "matched": matched,
                            "code": code,
                        })

            time.sleep(self.delay)

        # Phase 2: Per-store inventory lookups for matched products
        if stock_check_queue:
            logger.info(
                f"Checking per-store stock for {len(stock_check_queue)} "
                f"matched products..."
            )
            new_finds_count = self._check_per_store_stock(stock_check_queue)

        return total_found, new_finds_count

    def _check_per_store_stock(self, queue):
        """Query per-store stock for matched products via OCC stockStatus API."""
        new_finds_count = 0
        total_items = len(queue)

        for idx, item in enumerate(queue):
            product = item["product"]
            matched = item["matched"]
            code = item["code"]
            product_id = item["product_id"]

            self._on_progress({
                "phase": "inventory",
                "current": idx + 1,
                "total": total_items,
                "detail": product["name"][:50],
            })

            logger.info(
                f"  Checking stores for: {product['name'][:50]} "
                f"(tier {matched['rarity_tier']})"
            )

            stores_with_stock = check_store_stock(
                self.session, code
            )

            if stores_with_stock:
                logger.info(
                    f"    Found at {len(stores_with_stock)} store(s)"
                )
                for store in stores_with_stock:
                    is_new = check_is_new_find(
                        code, store["store_number"]
                    )
                    add_inventory_snapshot(
                        product_id,
                        store["store_number"],
                        store["store_name"],
                        store["store_address"],
                        store["quantity"],
                    )
                    if is_new:
                        new_finds_count += 1
                        self.new_finds.append({
                            "bourbon": matched,
                            "product": product,
                            "store": store,
                        })
                        logger.info(
                            f"    NEW FIND: {store['store_name']} "
                            f"qty={store['quantity']}"
                        )
            else:
                # Online-only stock (no physical stores)
                is_new = check_is_new_find(code, "online")
                add_inventory_snapshot(
                    product_id, "online", "FWGS Online",
                    product.get("url", ""), 1,
                )
                if is_new:
                    new_finds_count += 1
                    self.new_finds.append({
                        "bourbon": matched,
                        "product": product,
                        "store": {
                            "store_name": "FWGS Online",
                            "store_number": "online",
                            "store_address": product.get("url", ""),
                            "quantity": 1,
                        },
                    })

            time.sleep(self.delay)

        return new_finds_count

    def _search_fwgs(self, term):
        """Search the FWGS website for a product term."""
        try:
            url = Config.FWGS_SEARCH_URL
            params = {"Ntt": term}
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return parse_fwgs_search_results(resp.text)
        except requests.RequestException as e:
            logger.warning(f"FWGS search failed for '{term}': {e}")
        return []

    def search_single_product(self, term):
        """Search for a single product (for manual searches)."""
        products = self._search_fwgs(term)
        for product in products:
            matched = match_product_to_bourbon(product["name"])
            if matched:
                product["bourbon_match"] = matched
        return products
