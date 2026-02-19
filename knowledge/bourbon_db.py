import json
import os
from database.models import upsert_bourbon, get_all_bourbons

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
ALLOCATED_FILE = os.path.join(DATA_DIR, "allocated_bourbons.json")


def load_knowledge_base():
    with open(ALLOCATED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def sync_knowledge_base_to_db():
    data = load_knowledge_base()
    count = 0
    for bourbon in data["bourbons"]:
        upsert_bourbon(bourbon)
        count += 1
    return count


def get_search_terms_by_tier(max_tier=4):
    data = load_knowledge_base()
    terms = []
    for bourbon in data["bourbons"]:
        if bourbon["rarity_tier"] <= max_tier:
            for term in bourbon.get("search_terms", []):
                terms.append({
                    "bourbon_id": bourbon["id"],
                    "term": term,
                    "tier": bourbon["rarity_tier"],
                    "name": bourbon["name"],
                })
    terms.sort(key=lambda x: x["tier"])
    return terms


def match_product_to_bourbon(product_name):
    data = load_knowledge_base()
    product_lower = product_name.lower()
    best_match = None
    best_score = 0

    for bourbon in data["bourbons"]:
        for term in bourbon.get("search_terms", []):
            term_lower = term.lower()
            if term_lower in product_lower:
                score = len(term_lower)
                if score > best_score:
                    best_score = score
                    best_match = bourbon
    return best_match


def get_bourbons_by_tier(tier):
    data = load_knowledge_base()
    return [b for b in data["bourbons"] if b["rarity_tier"] == tier]


def get_bourbon_by_id(bourbon_id):
    data = load_knowledge_base()
    for b in data["bourbons"]:
        if b["id"] == bourbon_id:
            return b
    return None


def get_tier_label(tier):
    labels = {
        1: "Unicorn",
        2: "Highly Allocated",
        3: "Allocated",
        4: "Worth Tracking",
    }
    return labels.get(tier, "Unknown")


def get_knowledge_base_stats():
    data = load_knowledge_base()
    bourbons = data["bourbons"]
    tiers = {}
    for b in bourbons:
        t = b["rarity_tier"]
        tiers[t] = tiers.get(t, 0) + 1
    return {
        "total": len(bourbons),
        "tiers": tiers,
        "version": data["metadata"]["version"],
        "last_updated": data["metadata"]["last_updated"],
    }
