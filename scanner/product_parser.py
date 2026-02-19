import re
import json
import logging
from urllib.parse import unquote
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# FWGS uses Oracle Commerce Cloud (OCC). Product data is embedded in
# a URL-encoded JSON blob assigned to window.state in the page HTML.
# This parser extracts products directly from that structured data.


def parse_fwgs_search_results(html):
    """Parse product listings from FWGS search results page.

    The FWGS site is an Oracle Commerce Cloud SPA. Product data is
    embedded in window.state as JSON, not in rendered HTML.
    """
    # Primary: extract from window.state JSON
    products = _parse_occ_window_state(html)
    if products:
        return products

    # Fallback: try HTML parsing (unlikely to work but harmless)
    soup = BeautifulSoup(html, "lxml")
    return _parse_html_fallback(soup)


def _parse_occ_window_state(html):
    """Extract product data from Oracle Commerce Cloud window.state."""
    match = re.search(
        r'window\.state\s*=\s*JSON\.parse\(decodeURI\("(.+?)"\)\)', html
    )
    if not match:
        logger.debug("No window.state found in page")
        return []

    try:
        decoded = unquote(match.group(1))
        state = json.loads(decoded)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse window.state JSON: {e}")
        return []

    # Navigate to search results
    search_repo = state.get("searchRepository", {})
    pages = search_repo.get("pages", {})

    products = []
    for page_key, page_data in pages.items():
        if not isinstance(page_data, dict):
            continue
        results = page_data.get("results", {})
        records = results.get("records", [])

        total = results.get("totalNumRecs", 0)
        logger.info(f"FWGS search returned {total} total results")

        for record in records:
            product = _parse_occ_record(record)
            if product:
                products.append(product)

    return products


def _parse_occ_record(record):
    """Parse a single OCC product record into our product format."""
    attrs = record.get("attributes", {})
    if not attrs:
        return None

    def attr(key):
        val = attrs.get(key)
        if isinstance(val, list):
            return val[0] if val else None
        return val

    name = attr("product.displayName")
    if not name:
        return None

    product = {
        "name": name,
        "fwgs_code": attr("product.repositoryId") or attr("sku.repositoryId"),
        "sku": attr("sku-B2CProduct.x_searchableSKU"),
        "price": _safe_float(attr("sku.activePrice")),
        "list_price": _safe_float(attr("product.listPrice")),
        "size": attr("product.b2c_size"),
        "brand": attr("product.brand"),
        "route": attr("product.route"),
        "url": attr("product.route") or "",
        "image_url": attr("product.primaryMediumImageURL"),
        "availability": attr("sku.availabilityStatus"),
        "in_stock": attr("sku.availabilityStatus") == "INSTOCK",
        "proof": _extract_proof(name),
        # FWGS-specific flags
        "is_lottery": attr("B2CProduct.b2c_lotteryProduct") == "Y",
        "is_highly_allocated": attr("B2CProduct.b2c_highlyAllocatedProduct") == "Y",
        "is_chairmans_selection": attr("B2CProduct.b2c_chairmansSelection") == "Y",
        "is_online_exclusive": attr("B2CProduct.b2c_onlineExclusive") == "Y",
        "is_coming_soon": attr("B2CProduct.b2c_comingSoon") == "Y",
        "is_special_order": attr("B2CProduct.b2c_specialOrderProduct") == "Y",
        "category": attr("parentCategory.displayName"),
    }

    # Build full URLs
    base = "https://www.finewineandgoodspirits.com"
    if product["route"]:
        product["url"] = f"{base}{product['route']}"
    if product["image_url"] and product["image_url"].startswith("/"):
        product["image_url"] = f"{base}{product['image_url']}"

    return product


def parse_fwgs_inventory_page(html):
    """Parse store inventory from a product inventory page."""
    # Try window.state first (OCC format)
    stores = _parse_occ_inventory_state(html)
    if stores:
        return stores

    # Fallback to HTML table parsing (legacy PLCB pages)
    soup = BeautifulSoup(html, "lxml")
    return _parse_inventory_html(soup)


def _parse_occ_inventory_state(html):
    """Try to extract inventory data from OCC window.state."""
    match = re.search(
        r'window\.state\s*=\s*JSON\.parse\(decodeURI\("(.+?)"\)\)', html
    )
    if not match:
        return []

    try:
        decoded = unquote(match.group(1))
        state = json.loads(decoded)
    except (json.JSONDecodeError, ValueError):
        return []

    # Look for inventory data in inventoryRepository or productRepository
    inv_repo = state.get("inventoryRepository", {})
    stores = []

    # OCC may store inventory per-location
    for key, val in inv_repo.items():
        if isinstance(val, dict):
            for loc_key, loc_data in val.items():
                if isinstance(loc_data, dict) and "locationId" in loc_data:
                    store = {
                        "store_number": loc_data.get("locationId", ""),
                        "store_name": loc_data.get("locationName", ""),
                        "store_address": loc_data.get("address", ""),
                        "quantity": loc_data.get("stockLevel", 0),
                    }
                    if store["quantity"] and store["quantity"] > 0:
                        stores.append(store)

    return stores


def _parse_inventory_html(soup):
    """Parse store inventory from HTML tables (legacy PLCB pages)."""
    stores = []
    rows = soup.select("table tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) < 2:
            continue

        store = {}
        texts = [c.get_text(strip=True) for c in cells]

        for text in texts:
            if re.match(r"^\d{4}$", text):
                store["store_number"] = text
            elif re.match(r"^\d{1,3}$", text) and "store_number" in store:
                store["quantity"] = int(text)
            elif re.search(r"\d+\s+\w+\s+(st|ave|rd|blvd|dr|ln|way|pike)", text, re.I):
                store["store_address"] = text

        name_el = row.select_one("a, .store-name")
        if name_el:
            store["store_name"] = name_el.get_text(strip=True)

        if store.get("store_number") or store.get("store_name"):
            store.setdefault("quantity", 0)
            stores.append(store)

    return stores


def parse_legacy_search_results(html):
    """Parse results from legacy PLCB product search (ASP pages)."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    rows = soup.select("table tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) >= 4:
            product = {}
            link = row.select_one("a")
            if link:
                product["name"] = link.get_text(strip=True)
                href = link.get("href", "")
                code_match = re.search(r"cdeNo=(\d+)", href)
                if code_match:
                    product["fwgs_code"] = code_match.group(1)
                    product["url"] = href

            for cell in cells:
                text = cell.get_text(strip=True)
                if "$" in text:
                    product["price"] = _extract_price(text)
                size_match = re.search(r"(\d+)\s*ml", text, re.I)
                if size_match:
                    product["size"] = f"{size_match.group(1)} ml"

            if product.get("name") and product.get("fwgs_code"):
                products.append(product)

    return products


def _parse_html_fallback(soup):
    """Last-resort HTML parsing for product listings."""
    products = []
    cards = soup.select(".card, .product-card, [data-product-id]")
    for card in cards:
        name_el = card.select_one(".card__title, .product-title, h2, h3")
        if not name_el:
            continue
        product = {"name": name_el.get_text(strip=True)}
        price_el = card.select_one(".card__price-amount, .product-price, .price")
        if price_el:
            product["price"] = _extract_price(price_el.get_text(strip=True))
        link = card.select_one("a[href]")
        if link:
            product["url"] = link.get("href", "")
            product["fwgs_code"] = _extract_product_code(product["url"])
        products.append(product)
    return products


def _extract_price(text):
    match = re.search(r"\$?\s*(\d+(?:\.\d{2})?)", text)
    return float(match.group(1)) if match else None


def _extract_product_code(url):
    match = re.search(r"/product/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"cdeNo=(\d+)", url)
    if match:
        return match.group(1)
    return None


def _extract_proof(name):
    match = re.search(r"(\d{2,3}(?:\.\d)?)\s*proof", name, re.I)
    return float(match.group(1)) if match else None


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
