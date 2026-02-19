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
