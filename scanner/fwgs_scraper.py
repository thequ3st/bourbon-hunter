import time
import logging
import requests
from config import Config
from scanner.product_parser import (
    parse_fwgs_search_results,
    parse_fwgs_inventory_page,
    parse_legacy_search_results,
)
from scanner.store_locator import get_session
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
    def __init__(self):
        self.session = get_session()
        self.delay = Config.REQUEST_DELAY_SECONDS
        self.new_finds = []

    def run_full_scan(self):
        """Run a complete scan: search for all tracked bourbons, check inventory."""
        scan_id = log_scan_start("full_scan")
        total_found = 0
        new_finds_count = 0

        try:
            search_terms = get_search_terms_by_tier(max_tier=4)
            seen_terms = set()

            for entry in search_terms:
                term = entry["term"]
                if term.lower() in seen_terms:
                    continue
                seen_terms.add(term.lower())

                logger.info(f"Searching FWGS for: {term}")
                products = self._search_fwgs(term)
                logger.info(f"  Found {len(products)} products for '{term}'")

                for product in products:
                    # Match to our knowledge base
                    matched = match_product_to_bourbon(product["name"])
                    if matched:
                        product["bourbon_id"] = matched["id"]

                    product_id = upsert_fwgs_product(product)
                    if product_id:
                        total_found += 1

                        # Check inventory at stores
                        if product.get("fwgs_code"):
                            inventory = self._check_inventory(product["fwgs_code"])
                            for store in inventory:
                                if store.get("quantity", 0) > 0:
                                    is_new = check_is_new_find(
                                        product["fwgs_code"],
                                        store.get("store_number", ""),
                                    )
                                    add_inventory_snapshot(
                                        product_id,
                                        store.get("store_number", ""),
                                        store.get("store_name", ""),
                                        store.get("store_address", ""),
                                        store.get("quantity", 0),
                                    )
                                    if is_new and matched:
                                        new_finds_count += 1
                                        self.new_finds.append({
                                            "bourbon": matched,
                                            "product": product,
                                            "store": store,
                                        })

                time.sleep(self.delay)

            log_scan_complete(scan_id, total_found, new_finds_count)
            logger.info(
                f"Scan complete: {total_found} products, {new_finds_count} new finds"
            )

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
        max_tier = tier or 2  # Default: just unicorns and highly allocated
        scan_id = log_scan_start(f"quick_scan_tier_{max_tier}")
        total_found = 0
        new_finds_count = 0

        try:
            search_terms = get_search_terms_by_tier(max_tier=max_tier)
            seen_terms = set()

            for entry in search_terms:
                term = entry["term"]
                if term.lower() in seen_terms:
                    continue
                seen_terms.add(term.lower())

                products = self._search_fwgs(term)
                for product in products:
                    matched = match_product_to_bourbon(product["name"])
                    if matched:
                        product["bourbon_id"] = matched["id"]
                        product_id = upsert_fwgs_product(product)
                        if product_id:
                            total_found += 1
                            if product.get("fwgs_code"):
                                inventory = self._check_inventory(product["fwgs_code"])
                                for store in inventory:
                                    if store.get("quantity", 0) > 0:
                                        is_new = check_is_new_find(
                                            product["fwgs_code"],
                                            store.get("store_number", ""),
                                        )
                                        add_inventory_snapshot(
                                            product_id,
                                            store.get("store_number", ""),
                                            store.get("store_name", ""),
                                            store.get("store_address", ""),
                                            store.get("quantity", 0),
                                        )
                                        if is_new:
                                            new_finds_count += 1
                                            self.new_finds.append({
                                                "bourbon": matched,
                                                "product": product,
                                                "store": store,
                                            })
                time.sleep(self.delay)

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

    def _search_fwgs(self, term):
        """Search the FWGS website for a product term."""
        products = []

        # Try modern FWGS site first
        try:
            url = Config.FWGS_SEARCH_URL
            params = {"Ntt": term}
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                products = parse_fwgs_search_results(resp.text)
        except requests.RequestException as e:
            logger.warning(f"FWGS search failed for '{term}': {e}")

        # Fallback to legacy PLCB search
        if not products:
            try:
                url = Config.FWGS_LEGACY_SEARCH_URL
                data = {"txtBrandName": term, "btnSearch": "Search"}
                resp = self.session.post(url, data=data, timeout=15)
                if resp.status_code == 200:
                    products = parse_legacy_search_results(resp.text)
            except requests.RequestException as e:
                logger.warning(f"Legacy search failed for '{term}': {e}")

        return products

    def _check_inventory(self, product_code):
        """Check store inventory for a specific product code."""
        stores = []

        try:
            url = Config.FWGS_LEGACY_INVENTORY_URL
            params = {"cdeNo": product_code}
            resp = self.session.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                stores = parse_fwgs_inventory_page(resp.text)
            time.sleep(self.delay / 2)  # Shorter delay for inventory checks
        except requests.RequestException as e:
            logger.warning(f"Inventory check failed for code {product_code}: {e}")

        return stores

    def search_single_product(self, term):
        """Search for a single product (for manual searches)."""
        products = self._search_fwgs(term)
        for product in products:
            matched = match_product_to_bourbon(product["name"])
            if matched:
                product["bourbon_match"] = matched
        return products
