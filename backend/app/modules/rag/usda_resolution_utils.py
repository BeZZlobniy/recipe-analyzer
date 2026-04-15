from __future__ import annotations

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

BLOCKED_TOKENS = {"salad", "sauce", "snack", "dessert", "seasoned", "prepared", "meal", "mix", "steak", "burger", "sandwich"}


def build_queries(ingredient_name: str, ingredient_name_en: str | None = None) -> list[str]:
    return build_query_variants(ingredient_name, ingredient_name_en)


def score_candidate(product: Product, query: str, rank: int, query_index: int) -> float:
    query_tokens = {token for token in normalize_text(query).split() if len(token) >= 3}
    display = normalize_text(product.display_name_en or product.display_name_ru)
    display_tokens = {token for token in display.split() if len(token) >= 3}
    if not query_tokens or not display_tokens:
        return 0.0
    overlap = len(query_tokens & display_tokens) / max(len(query_tokens), 1)
    if overlap == 0:
        return 0.0
    data_type_bonus = DATA_TYPE_PRIORITY.get(product.category or "", 0.8)
    blocked_penalty = 1.5 if BLOCKED_TOKENS & display_tokens else 0.0
    score = overlap * 3.0 + data_type_bonus - rank * 0.15 - query_index * 0.1 - blocked_penalty
    return round(score, 3)


def is_safe_candidate(ingredient_payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    ingredient_tokens = {token for token in normalize_text(ingredient_payload.get("name_en") or "").split() if len(token) >= 3}
    if not ingredient_tokens:
        ingredient_tokens = {token for token in normalize_text(ingredient_payload.get("name_canonical") or "").split() if len(token) >= 3}
    display_tokens = {token for token in normalize_text(candidate.get("display_name_en") or candidate.get("display_name_ru")).split() if len(token) >= 3}
    if not ingredient_tokens or not display_tokens:
        return False
    if not (ingredient_tokens & display_tokens):
        return False
    if BLOCKED_TOKENS & display_tokens:
        return False
    return True


def is_exact_candidate(ingredient_payload: dict[str, Any], candidate: dict[str, Any]) -> bool:
    ingredient_name_en = normalize_text(ingredient_payload.get("name_en") or "")
    display_name = normalize_text(candidate.get("display_name_en") or candidate.get("display_name_ru") or "")
    if not ingredient_name_en or not display_name:
        return False
    display_tokens = set(display_name.split())
    if BLOCKED_TOKENS & display_tokens:
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
