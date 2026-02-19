import re
from bs4 import BeautifulSoup


def parse_fwgs_search_results(html):
    """Parse product listings from FWGS search results page."""
    soup = BeautifulSoup(html, "lxml")
    products = []

    # Modern FWGS site uses product cards
    cards = soup.select(".card, .product-card, .product-card-link, [data-product-id]")
    for card in cards:
        product = _parse_product_card(card)
        if product:
            products.append(product)

    # Fallback: try generic link/title patterns
    if not products:
        products = _parse_generic_product_listing(soup)

    return products


def _parse_product_card(card):
    """Parse a single product card element."""
    product = {}

    # Name
    name_el = card.select_one(
        ".card__title, .product-title, .product-name, h2, h3, [class*='title']"
    )
    if name_el:
        product["name"] = name_el.get_text(strip=True)
    else:
        return None

    # Price
    price_el = card.select_one(
        ".card__price-amount, .product-price, .price, [class*='price']"
    )
    if price_el:
        price_text = price_el.get_text(strip=True)
        product["price"] = _extract_price(price_text)

    # URL / product code
    link = card.select_one("a[href]")
    if not link:
        link = card if card.name == "a" else None
    if link:
        href = link.get("href", "")
        product["url"] = href
        product["fwgs_code"] = _extract_product_code(href)

    # Size
    size_el = card.select_one(".card__size, .product-size, [class*='size']")
    if size_el:
        product["size"] = size_el.get_text(strip=True)

    # Availability
    avail_el = card.select_one(
        ".card__availability, .availability, [class*='availability'], [class*='stock']"
    )
    if avail_el:
        avail_text = avail_el.get_text(strip=True).lower()
        product["in_stock"] = "out" not in avail_text and "unavailable" not in avail_text

    # Product ID from data attribute
    product_id = card.get("data-product-id") or card.get("data-sku")
    if product_id:
        product["fwgs_code"] = product_id

    # Proof from name
    product["proof"] = _extract_proof(product.get("name", ""))

    return product


def _parse_generic_product_listing(soup):
    """Fallback parser for less structured pages."""
    products = []
    # Look for table rows (legacy PLCB site)
    rows = soup.select("table tr")
    for row in rows:
        cells = row.select("td")
        if len(cells) >= 3:
            product = {}
            link = row.select_one("a[href]")
            if link:
                product["name"] = link.get_text(strip=True)
                product["url"] = link.get("href", "")
                product["fwgs_code"] = _extract_product_code(product["url"])
            for cell in cells:
                text = cell.get_text(strip=True)
                if text.startswith("$"):
                    product["price"] = _extract_price(text)
                elif re.match(r"^\d{3,6}$", text):
                    product["fwgs_code"] = text
            if product.get("name"):
                products.append(product)
    return products


def parse_fwgs_inventory_page(html):
    """Parse store inventory from a product inventory page."""
    soup = BeautifulSoup(html, "lxml")
    stores = []

    # Look for store inventory table/list
    rows = soup.select("table tr, .store-inventory-row, [class*='store']")
    for row in rows:
        store = _parse_store_row(row)
        if store:
            stores.append(store)

    # Try JSON data embedded in page
    if not stores:
        stores = _extract_embedded_store_data(soup)

    return stores


def _parse_store_row(row):
    """Parse a single store inventory row."""
    cells = row.select("td")
    if len(cells) < 2:
        return None

    store = {}
    texts = [c.get_text(strip=True) for c in cells]

    for text in texts:
        # Store number pattern
        if re.match(r"^\d{4}$", text):
            store["store_number"] = text
        # Quantity
        elif re.match(r"^\d{1,3}$", text) and "store_number" in store:
            store["quantity"] = int(text)
        # Address-like pattern
        elif re.search(r"\d+\s+\w+\s+(st|ave|rd|blvd|dr|ln|way|pike)", text, re.I):
            store["store_address"] = text

    # Store name
    name_el = row.select_one("a, .store-name, [class*='name']")
    if name_el:
        store["store_name"] = name_el.get_text(strip=True)

    if store.get("store_number") or store.get("store_name"):
        store.setdefault("quantity", 0)
        return store
    return None


def _extract_embedded_store_data(soup):
    """Try to extract store data from embedded JSON or scripts."""
    import json
    stores = []
    scripts = soup.select("script")
    for script in scripts:
        text = script.string or ""
        # Look for JSON with inventory data
        matches = re.findall(r'\{[^{}]*"store[^{}]*"inventory"[^{}]*\}', text)
        for match in matches:
            try:
                data = json.loads(match)
                stores.append(data)
            except (json.JSONDecodeError, ValueError):
                continue
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


def _extract_price(text):
    """Extract numeric price from text like '$45.99'."""
    match = re.search(r"\$?\s*(\d+(?:\.\d{2})?)", text)
    return float(match.group(1)) if match else None


def _extract_product_code(url):
    """Extract FWGS product code from URL."""
    # Pattern: /product/12345/... or cdeNo=12345
    match = re.search(r"/product/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"cdeNo=(\d+)", url)
    if match:
        return match.group(1)
    # Try trailing numeric segment
    match = re.search(r"/(\d{3,6})(?:\?|$|/)", url)
    if match:
        return match.group(1)
    return None


def _extract_proof(name):
    """Try to extract proof from product name."""
    match = re.search(r"(\d{2,3}(?:\.\d)?)\s*proof", name, re.I)
    if match:
        return float(match.group(1))
    return None
