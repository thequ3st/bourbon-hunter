import re
import time
import requests
from bs4 import BeautifulSoup
from config import Config


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": Config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def fetch_all_stores(session=None):
    """Fetch list of all PA FWGS store locations."""
    if session is None:
        session = get_session()

    stores = []
    # PA has 67 counties — iterate through them
    pa_counties = [
        "Adams", "Allegheny", "Armstrong", "Beaver", "Bedford", "Berks",
        "Blair", "Bradford", "Bucks", "Butler", "Cambria", "Cameron",
        "Carbon", "Centre", "Chester", "Clarion", "Clearfield", "Clinton",
        "Columbia", "Crawford", "Cumberland", "Dauphin", "Delaware", "Elk",
        "Erie", "Fayette", "Forest", "Franklin", "Fulton", "Greene",
        "Huntingdon", "Indiana", "Jefferson", "Juniata", "Lackawanna",
        "Lancaster", "Lawrence", "Lebanon", "Lehigh", "Luzerne", "Lycoming",
        "McKean", "Mercer", "Mifflin", "Monroe", "Montgomery", "Montour",
        "Northampton", "Northumberland", "Perry", "Philadelphia", "Pike",
        "Potter", "Schuylkill", "Snyder", "Somerset", "Sullivan", "Susquehanna",
        "Tioga", "Union", "Venango", "Warren", "Washington", "Wayne",
        "Westmoreland", "Wyoming", "York"
    ]

    for i, county in enumerate(pa_counties):
        try:
            url = f"{Config.FWGS_STORE_URL}?county={i + 1}"
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                county_stores = _parse_store_list(resp.text, county)
                stores.extend(county_stores)
            time.sleep(Config.REQUEST_DELAY_SECONDS)
        except requests.RequestException:
            continue

    return stores


def _parse_store_list(html, county):
    """Parse store listings from county page."""
    soup = BeautifulSoup(html, "lxml")
    stores = []

    # Look for store entries in tables or divs
    rows = soup.select("table tr, .store-row, [class*='store']")
    for row in rows:
        store = _parse_single_store(row, county)
        if store:
            stores.append(store)

    # Fallback: parse text blocks
    if not stores:
        stores = _parse_store_text_blocks(soup, county)

    return stores


def _parse_single_store(element, county):
    """Parse a single store entry."""
    store = {"county": county}

    # Store number
    text = element.get_text()
    num_match = re.search(r"Store\s*#?\s*(\d{4})", text)
    if num_match:
        store["store_number"] = num_match.group(1)

    # Store name / address from links or text
    link = element.select_one("a")
    if link:
        store["store_name"] = link.get_text(strip=True)

    # Address
    addr_match = re.search(
        r"(\d+\s+[\w\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|"
        r"Lane|Ln|Way|Pike|Highway|Hwy|Court|Ct|Place|Pl|Circle|Cir)[\w\s,]*)",
        text, re.I
    )
    if addr_match:
        store["address"] = addr_match.group(1).strip()

    # Phone
    phone_match = re.search(r"\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{4}", text)
    if phone_match:
        store["phone"] = phone_match.group()

    # City/zip
    zip_match = re.search(r"(\w[\w\s]+),?\s*PA\s*(\d{5})", text)
    if zip_match:
        store["city"] = zip_match.group(1).strip()
        store["zip"] = zip_match.group(2)

    if store.get("store_number") or store.get("store_name"):
        return store
    return None


def _parse_store_text_blocks(soup, county):
    """Parse stores from less structured text content."""
    stores = []
    # Try to find store blocks by looking for store number patterns
    text = soup.get_text()
    blocks = re.split(r"(?=Store\s*#?\s*\d{4})", text)
    for block in blocks:
        if not block.strip():
            continue
        store = {"county": county}
        num_match = re.search(r"Store\s*#?\s*(\d{4})", block)
        if num_match:
            store["store_number"] = num_match.group(1)
            # Get address lines after store number
            lines = block.split("\n")
            addr_parts = []
            for line in lines[1:4]:
                line = line.strip()
                if line and not line.startswith("Store"):
                    addr_parts.append(line)
            if addr_parts:
                store["address"] = ", ".join(addr_parts)
                store["store_name"] = addr_parts[0]
            stores.append(store)
    return stores


def get_stores_by_county(county_name, session=None):
    """Get stores for a specific county."""
    if session is None:
        session = get_session()

    pa_counties = [
        "Adams", "Allegheny", "Armstrong", "Beaver", "Bedford", "Berks",
        "Blair", "Bradford", "Bucks", "Butler", "Cambria", "Cameron",
        "Carbon", "Centre", "Chester", "Clarion", "Clearfield", "Clinton",
        "Columbia", "Crawford", "Cumberland", "Dauphin", "Delaware", "Elk",
        "Erie", "Fayette", "Forest", "Franklin", "Fulton", "Greene",
        "Huntingdon", "Indiana", "Jefferson", "Juniata", "Lackawanna",
        "Lancaster", "Lawrence", "Lebanon", "Lehigh", "Luzerne", "Lycoming",
        "McKean", "Mercer", "Mifflin", "Monroe", "Montgomery", "Montour",
        "Northampton", "Northumberland", "Perry", "Philadelphia", "Pike",
        "Potter", "Schuylkill", "Snyder", "Somerset", "Sullivan", "Susquehanna",
        "Tioga", "Union", "Venango", "Warren", "Washington", "Wayne",
        "Westmoreland", "Wyoming", "York"
    ]

    try:
        idx = next(
            i for i, c in enumerate(pa_counties)
            if c.lower() == county_name.lower()
        )
    except StopIteration:
        return []

    url = f"{Config.FWGS_STORE_URL}?county={idx + 1}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            return _parse_store_list(resp.text, county_name)
    except requests.RequestException:
        pass
    return []
