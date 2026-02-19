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
    product_normalized = _normalize(product_name)
    prod_word_set = set(product_normalized.split())
    best_match = None
    best_score = 0

    for bourbon in data["bourbons"]:
        # 1) Search-term substring matching (most reliable)
        for term in bourbon.get("search_terms", []):
            term_normalized = _normalize(term)
            if len(term_normalized) >= 5 and term_normalized in product_normalized:
                score = len(term_normalized)
                if score > best_score:
                    best_score = score
                    best_match = bourbon

        # 2) Search-term word-set matching (all key words present, any order)
        #    Handles FWGS verbose names like "Colonel E H Taylor Jr Straight
        #    Bourbon Barrel Proof" matching search term "E.H. Taylor Barrel Proof"
        for term in bourbon.get("search_terms", []):
            term_normalized = _normalize(term)
            term_words = [w for w in term_normalized.split()
                          if len(w) >= 2 or w.isdigit()]
            term_distinctive = [w for w in term_words
                                if w not in _COMMON_SPIRIT_WORDS]
            if len(term_words) >= 2 and term_distinctive:
                if all(w in prod_word_set for w in term_words):
                    score = sum(len(w) for w in term_words) + 10
                    # Age statement check
                    term_nums = [w for w in term_words if w.isdigit()]
                    prod_nums = [w for w in prod_word_set if w.isdigit()]
                    if term_nums and not all(n in prod_nums for n in term_nums):
                        score = 0
                    if score > best_score:
                        best_score = score
                        best_match = bourbon

        # 3) Name word-ratio matching (strict fallback)
        name_normalized = _normalize(bourbon["name"])
        name_words = [w for w in name_normalized.split()
                      if len(w) > 2 or w.isdigit()]
        if not name_words:
            continue

        distinctive = [w for w in name_words if w not in _COMMON_SPIRIT_WORDS]
        matched_words = sum(1 for w in name_words if w in prod_word_set)
        distinctive_matched = sum(1 for w in distinctive
                                  if w in prod_word_set)
        ratio = matched_words / len(name_words)

        # Require: high overall ratio, AND at least one distinctive word,
        # AND majority of distinctive words must match
        if (ratio >= 0.75
                and distinctive_matched >= 1
                and (not distinctive
                     or distinctive_matched / len(distinctive) >= 0.6)):
            score = distinctive_matched * 20 + matched_words * 5
            name_nums = [w for w in name_words if w.isdigit()]
            prod_nums = [w for w in prod_word_set if w.isdigit()]
            if name_nums and all(n in prod_nums for n in name_nums):
                score += 50
            elif name_nums and not any(n in prod_nums for n in name_nums):
                score = 0
            if score > best_score:
                best_score = score
                best_match = bourbon

    return best_match


# Words too generic to distinguish bourbon products from other spirits
_COMMON_SPIRIT_WORDS = {
    "straight", "bourbon", "whiskey", "whisky", "rye", "scotch",
    "single", "barrel", "malt", "proof", "full", "from", "the",
    "year", "old", "reserve", "special", "limited", "edition",
    "small", "batch", "bottled", "bond", "select", "cask",
    "strength", "aged", "distillery", "pot", "still",
}


def _normalize(text):
    """Normalize text for fuzzy matching: lowercase, strip punctuation."""
    import re
    text = text.lower()
    text = re.sub(r"[''`]", "", text)       # remove apostrophes
    text = re.sub(r"[^a-z0-9\s]", " ", text)  # punctuation to spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
