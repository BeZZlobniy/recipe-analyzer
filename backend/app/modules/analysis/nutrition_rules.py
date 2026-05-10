from __future__ import annotations

import re
from typing import Any

from app.core.utils import load_data_json, normalize_text
from app.modules.structuring.schemas import StructuredIngredient


DEFAULT_TARGETS = {
    "calories": 2000.0,
    "protein": 100.0,
    "fat": 70.0,
    "carbs": 300.0,
    "fiber": 25.0,
    "sodium": 1500.0,
}

_FALLBACK_DATA = load_data_json("fallback/nutrition_fallbacks.json")

UNIT_TO_GRAMS = dict(_FALLBACK_DATA.get("unit_to_grams", {}))
PIECE_HINTS = dict(_FALLBACK_DATA.get("piece_hints", {}))
VOLUME_HINTS = dict(_FALLBACK_DATA.get("volume_hints", {}))
ESTIMATE_DB = dict(_FALLBACK_DATA.get("estimate_db", {}))
MINOR_AMOUNT_MARKERS = set(_FALLBACK_DATA.get("minor_amount_markers", []))
MINOR_INGREDIENT_TOKENS = set(_FALLBACK_DATA.get("minor_ingredient_tokens", []))
BROAD_MEAT_ESTIMATE_OVERRIDES = set(_FALLBACK_DATA.get("broad_meat_estimate_overrides", []))


def estimate_grams(ingredient: StructuredIngredient, product: dict[str, Any] | None) -> tuple[float, str, bool]:
    amount_text = normalize_text(ingredient.amount_text)
    if amount_text in MINOR_AMOUNT_MARKERS:
        grams = float(estimate_default_grams(ingredient.name_canonical, 5.0))
        return grams, f"эвристика:{amount_text}", True
    if ingredient.amount_value is None:
        if ingredient.llm_grams is not None:
            return float(ingredient.llm_grams), f"llm_grams:{ingredient.gram_confidence or 'low'}", True
        grams = float(estimate_default_grams(ingredient.name_canonical, 50.0))
        return grams, "эвристика:amount_missing", True

    if ingredient.unit in UNIT_TO_GRAMS:
        amount_value = float(ingredient.amount_value)
        if ingredient.unit == "кг" and amount_value >= 100:
            text_value = _first_number(ingredient.amount_text)
            if text_value is not None and text_value < 100:
                return text_value * UNIT_TO_GRAMS[ingredient.unit], "explicit_unit", False
            return amount_value, "explicit_unit:kg_value_already_grams", True
        grams_per_unit = UNIT_TO_GRAMS[ingredient.unit]
        if ingredient.unit == "стакан":
            grams_per_unit = estimate_cup_weight(ingredient)
        return amount_value * grams_per_unit, "explicit_unit", False

    if ingredient.unit == "шт":
        weight = float(product["grams_per_piece_estimate"]) if product and product.get("grams_per_piece_estimate") else 80.0
        used_generic_piece = product is None or not product.get("grams_per_piece_estimate")
        for token, grams in PIECE_HINTS.items():
            if token in ingredient.name_canonical:
                weight = grams
                used_generic_piece = False
                break
        if used_generic_piece and ingredient.llm_grams is not None:
            return float(ingredient.llm_grams), f"llm_grams:{ingredient.gram_confidence or 'low'}", True
        return float(ingredient.amount_value) * weight, "piece_estimate", True

    if ingredient.llm_grams is not None:
        return float(ingredient.llm_grams), f"llm_grams:{ingredient.gram_confidence or 'low'}", True
    return float(ingredient.amount_value), "numeric_without_unit", True


def resolve_nutrients(ingredient: StructuredIngredient, product: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str, str]:
    estimate = find_estimate(ingredient.name_canonical)
    normalized_name = normalize_text(ingredient.name_canonical)
    if estimate and normalized_name in BROAD_MEAT_ESTIMATE_OVERRIDES:
        return estimate["nutrients_per_100g"], "estimate", "medium"
    if product and isinstance(product.get("nutrients_per_100g"), dict) and product.get("nutrients_per_100g"):
        nutrients = dict(product["nutrients_per_100g"])
        if estimate:
            for key, value in estimate["nutrients_per_100g"].items():
                if nutrients.get(key) is None:
                    nutrients[key] = value
        confidence = "high" if product.get("data_confidence") == "high" else "medium"
        return nutrients, product.get("source") or "product_db", confidence
    if estimate:
        return estimate["nutrients_per_100g"], "estimate", "low"
    return None, "unknown", "low"


def estimate_cup_weight(ingredient: StructuredIngredient) -> float:
    name = normalize_text(ingredient.name_canonical)
    for token, grams in VOLUME_HINTS.items():
        if token in name:
            return grams
    return 250.0


def estimate_default_grams(ingredient_name: str, default: float) -> float:
    estimate = find_estimate(ingredient_name)
    if estimate:
        return float(estimate["grams"])
    return default


def find_estimate(ingredient_name: str) -> dict[str, Any] | None:
    normalized = normalize_text(ingredient_name)
    for key, value in ESTIMATE_DB.items():
        if key in normalized:
            return value
    return None


def _first_number(value: Any) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def is_minor_ingredient(ingredient: StructuredIngredient) -> bool:
    low = normalize_text(ingredient.name_canonical)
    return any(token in low for token in MINOR_INGREDIENT_TOKENS)
