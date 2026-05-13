from __future__ import annotations

import re
from typing import Any

from app.core.utils import normalize_text
from app.models.product import Product
from app.modules.rag.ingredient_catalog import build_query_variants


DATA_TYPE_PRIORITY = {
    "Survey (FNDDS)": 3.0,
    "SR Legacy": 2.8,
    "Foundation": 2.6,
    "Experimental": 2.3,
    "Branded": 1.0,
}

BLOCKED_TOKENS = {
    "salad",
    "sauce",
    "snack",
    "dessert",
    "seasoned",
    "prepared",
    "cured",
    "pickle",
    "pickles",
    "pickled",
    "bockwurst",
    "backfat",
    "fatback",
    "bratwurst",
    "frankfurter",
    "giblets",
    "hocks",
    "sausage",
    "sausages",
    "meal",
    "mix",
    "steak",
    "burger",
    "sandwich",
    "cracker",
    "crackers",
    "guacamole",
    "dip",
    "pretzel",
    "pretzels",
    "filled",
}


def build_queries(ingredient_name: str, ingredient_name_en: str | None = None) -> list[str]:
    return build_query_variants(ingredient_name, ingredient_name_en)


def score_candidate(product: Product, query: str, rank: int, query_index: int) -> float:
    query_tokens = _tokens(query)
    display = normalize_text(product.display_name_en or product.display_name_ru)
    display_tokens = _tokens(display)
    if not query_tokens or not display_tokens:
        return 0.0
    if BLOCKED_TOKENS & display_tokens:
        return 0.0
    overlap = len(query_tokens & display_tokens) / max(len(query_tokens), 1)
    if overlap == 0:
        return 0.0
    data_type_bonus = DATA_TYPE_PRIORITY.get(product.category or "", 0.8)
    score = overlap * 3.0 + data_type_bonus - rank * 0.15 - query_index * 0.1
    return round(score, 3)


def is_safe_candidate(ingredient_payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    ingredient_tokens = _tokens(ingredient_payload.get("name_en") or "")
    if not ingredient_tokens:
        ingredient_tokens = _tokens(ingredient_payload.get("name_canonical") or "")
    display_tokens = _tokens(candidate.get("display_name_en") or candidate.get("display_name_ru"))
    if not ingredient_tokens or not display_tokens:
        return False
    if not (ingredient_tokens & display_tokens):
        return False
    if BLOCKED_TOKENS & display_tokens:
        return False
    if _has_food_family_conflict(ingredient_payload, candidate):
        return False
    if _has_unsafe_preparation(ingredient_tokens, display_tokens):
        return False
    return True


def is_exact_candidate(ingredient_payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    ingredient_name_en = normalize_text(ingredient_payload.get("name_en") or "")
    display_name = normalize_text(candidate.get("display_name_en") or candidate.get("display_name_ru") or "")
    if not ingredient_name_en or not display_name:
        return False
    display_tokens = _tokens(display_name)
    if BLOCKED_TOKENS & display_tokens:
        return False
    if _has_food_family_conflict(ingredient_payload, candidate):
        return False
    if _has_unsafe_preparation(_tokens(ingredient_name_en), display_tokens):
        return False
    if ingredient_name_en == display_name:
        return True
    if display_name.startswith(ingredient_name_en):
        return True
    return ingredient_name_en in display_name and len(display_name.split()) <= len(ingredient_name_en.split()) + 2


def extract_nutrients(details: dict[str, Any]) -> dict[str, float | None]:
    nutrients = details.get("foodNutrients") or []
    by_name: dict[str, float | None] = {}
    for item in nutrients:
        nutrient = item.get("nutrient") or {}
        name = nutrient.get("name") or item.get("nutrientName")
        amount = item.get("amount")
        if amount is None:
            amount = item.get("value")
        if name:
            by_name[name] = as_float(amount)
    return {
        "calories": by_name.get("Energy"),
        "protein": by_name.get("Protein"),
        "fat": by_name.get("Total lipid (fat)"),
        "carbs": by_name.get("Carbohydrate, by difference"),
        "fiber": by_name.get("Fiber, total dietary"),
        "sodium": by_name.get("Sodium, Na"),
    }


def piece_estimate(display_name: str) -> float | None:
    low = normalize_text(display_name)
    if "egg" in low:
        return 50.0
    if "onion" in low:
        return 60.0
    if "tomato" in low:
        return 120.0
    return None


def candidate_ids(payload: dict[str, Any] | None) -> list[int]:
    if not isinstance(payload, dict):
        return []
    ids = payload.get("candidate_product_ids")
    if not isinstance(ids, list):
        return []
    return [int(item) for item in ids if str(item).isdigit()]


def serialize_product(product: Product | None) -> dict[str, Any] | None:
    if product is None:
        return None
    return {
        "id": product.id,
        "source": product.source,
        "source_product_id": product.source_product_id,
        "display_name_ru": product.display_name_ru,
        "display_name_en": product.display_name_en,
        "category": product.category,
        "nutrients_per_100g": product.nutrients_json or {},
        "grams_per_piece_estimate": product.grams_per_piece_estimate,
        "data_confidence": product.data_confidence,
    }


def as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tokens(value: Any) -> set[str]:
    tokens: set[str] = set()
    for token in re.split(r"[^a-zа-я0-9]+", normalize_text(value)):
        if len(token) < 3:
            continue
        tokens.add(_normalize_token(token))
    return tokens


def _normalize_token(token: str) -> str:
    if re.fullmatch(r"[a-z]+", token) and token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _has_unsafe_preparation(ingredient_tokens: set[str], display_tokens: set[str]) -> bool:
    ground_tokens = {"ground", "minced"}
    asks_for_ground = bool(ingredient_tokens & ground_tokens)
    return bool(display_tokens & ground_tokens) and not asks_for_ground


def _has_food_family_conflict(ingredient_payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    ingredient_text = " ".join(
        str(ingredient_payload.get(key) or "")
        for key in ("name_raw", "name_canonical", "name_en")
    )
    candidate_text = " ".join(
        str(candidate.get(key) or "")
        for key in ("display_name_ru", "display_name_en")
    )
    ingredient_family = _food_family_from_text(ingredient_text)
    candidate_family = _food_family_from_text(candidate_text)
    return bool(ingredient_family and candidate_family and ingredient_family != candidate_family)


def _food_family_from_text(value: str | None) -> str | None:
    text = normalize_text(value)
    if not text:
        return None
    family_markers = {
        "pork": ("pork", "ham", "bacon", "\u0441\u0432\u0438\u043d"),
        "beef": ("beef", "\u0433\u043e\u0432\u044f\u0434"),
        "chicken": ("chicken", "turkey", "\u043a\u0443\u0440", "\u0438\u043d\u0434"),
        "fish": ("fish", "mackerel", "salmon", "\u0440\u044b\u0431", "\u0441\u043a\u0443\u043c\u0431\u0440"),
    }
    for family, markers in family_markers.items():
        if any(marker in text for marker in markers):
            return family
    return None
