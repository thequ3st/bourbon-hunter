import math
import logging
import requests
from config import Config

logger = logging.getLogger(__name__)

# In-memory cache of store data (loaded once per app lifetime)
_store_cache = {}


def get_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": Config.USER_AGENT,
        "Accept": "application/json,text/html,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def fetch_all_stores(session=None):
    """Fetch all 600 PA FWGS store locations from the OCC locations API."""
    global _store_cache
    if _store_cache:
        return list(_store_cache.values())

    if session is None:
        session = get_session()

    stores = []
    limit = 250
    for offset in (0, 250, 500):
        try:
            url = f"{Config.FWGS_BASE_URL}/ccstore/v1/locations"
            resp = session.get(url, params={"limit": limit, "offset": offset},
                               timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                for loc in data.get("items", []):
                    store = {
                        "store_number": loc.get("locationId", ""),
                        "store_name": loc.get("name", ""),
                        "address": loc.get("address1", ""),
                        "city": loc.get("city", ""),
                        "state": loc.get("stateAddress", "PA"),
                        "zip": loc.get("postalCode", ""),
                        "county": loc.get("county", ""),
                        "phone": loc.get("phoneNumber", ""),
                        "hours": loc.get("hours", ""),
                        "latitude": loc.get("latitude"),
                        "longitude": loc.get("longitude"),
                        "pickup": loc.get("pickUp", False),
                    }
                    stores.append(store)
        except requests.RequestException as e:
            logger.warning(f"Failed to fetch stores (offset={offset}): {e}")

    # Build cache keyed by store number
    _store_cache = {s["store_number"]: s for s in stores}
    logger.info(f"Loaded {len(stores)} FWGS store locations")
    return stores


def get_store_info(store_number):
    """Get cached info for a single store by number."""
    if not _store_cache:
        fetch_all_stores()
    return _store_cache.get(store_number)


def get_all_store_ids():
    """Get list of all store location IDs."""
    if not _store_cache:
        fetch_all_stores()
    return list(_store_cache.keys())


def check_store_stock(session, fwgs_code, store_ids=None):
    """Check per-store stock for a product using the OCC stockStatus API.

    Args:
        session: requests.Session
        fwgs_code: Product SKU (e.g., "000005480")
        store_ids: List of store IDs to check. If None, checks all stores.

    Returns:
        List of dicts with store_number, store_name, store_address, quantity
        for stores that have stock.
    """
    if not _store_cache:
        fetch_all_stores(session)

    if store_ids is None:
        store_ids = list(_store_cache.keys())

    in_stock_stores = []

    # Query in batches of 100 store IDs to avoid URL length limits
    batch_size = 100
    for i in range(0, len(store_ids), batch_size):
        batch = store_ids[i:i + batch_size]
        try:
            url = f"{Config.FWGS_BASE_URL}/ccstore/v1/stockStatus"
            params = {
                "products": fwgs_code,
                "locationIds": ",".join(batch),
                "actualStockStatus": "true",
            }
            resp = session.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    if item.get("stockStatus") == "IN_STOCK":
                        loc_id = item.get("locationId", "")
                        qty = item.get("productSkuInventoryStatus", {}).get(
                            fwgs_code, 0
                        )
                        if qty > 0:
                            store = _store_cache.get(loc_id, {})
                            addr = store.get("address", "")
                            if store.get("city"):
                                addr = f"{addr}, {store['city']}"
                            if store.get("zip"):
                                addr = f"{addr} {store['zip']}"
                            in_stock_stores.append({
                                "store_number": loc_id,
                                "store_name": store.get("store_name",
                                                        f"Store #{loc_id}"),
                                "store_address": addr,
                                "quantity": qty,
                                "county": store.get("county", ""),
                            })
        except requests.RequestException as e:
            logger.warning(
                f"stockStatus failed for {fwgs_code} batch {i}: {e}"
            )

    return in_stock_stores


def get_stores_by_county(county_name):
    """Get stores for a specific county."""
    if not _store_cache:
        fetch_all_stores()
    return [
        s for s in _store_cache.values()
        if s.get("county", "").lower() == county_name.lower()
    ]


def haversine_miles(lat1, lon1, lat2, lon2):
    """Calculate distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def geocode_zip(zip_code):
    """Convert a US zip code to lat/lng using the Census geocoder."""
    try:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            "address": f"{zip_code}",
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            matches = data.get("result", {}).get("addressMatches", [])
            if matches:
                coords = matches[0].get("coordinates", {})
                return coords.get("y"), coords.get("x")  # lat, lng
    except requests.RequestException:
        pass

    # Fallback: find a store in this zip code and use its coordinates
    if not _store_cache:
        fetch_all_stores()
    for store in _store_cache.values():
        if store.get("zip", "").startswith(zip_code[:3]):
            lat, lng = store.get("latitude"), store.get("longitude")
            if lat and lng:
                return lat, lng

    return None, None


def get_nearby_stores(lat, lng, radius_miles=25):
    """Get all stores within radius_miles of a lat/lng point, sorted by distance."""
    if not _store_cache:
        fetch_all_stores()

    nearby = []
    for store in _store_cache.values():
        slat = store.get("latitude")
        slng = store.get("longitude")
        if slat is None or slng is None:
            continue
        dist = haversine_miles(lat, lng, slat, slng)
        if dist <= radius_miles:
            nearby.append({
                **store,
                "distance_miles": round(dist, 1),
            })

    nearby.sort(key=lambda s: s["distance_miles"])
    return nearby
