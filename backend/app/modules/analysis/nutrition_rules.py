from __future__ import annotations

from typing import Any

from app.core.utils import normalize_text
from app.modules.structuring.schemas import StructuredIngredient


DEFAULT_TARGETS = {
    "calories": 2000.0,
    "protein": 100.0,
    "fat": 70.0,
    "carbs": 300.0,
    "fiber": 25.0,
    "sodium": 1500.0,
}

UNIT_TO_GRAMS = {
    "г": 1.0,
    "кг": 1000.0,
    "мл": 1.0,
    "л": 1000.0,
    "ст. л.": 15.0,
    "ч. л.": 5.0,
    "стакан": 250.0,
    "пучок": 30.0,
}

PIECE_HINTS = {
    "картоф": 140.0,
    "свекл": 180.0,
    "морков": 90.0,
    "лук": 60.0,
    "луковиц": 60.0,
    "яблок": 160.0,
    "яйц": 50.0,
    "чеснок": 4.0,
}

VOLUME_HINTS = {
    "греч": 200.0,
    "рис": 200.0,
    "круп": 200.0,
    "вода": 250.0,
    "молок": 250.0,
}

ESTIMATE_DB = {
    "соль": {"grams": 1.5, "nutrients_per_100g": {"calories": 0, "protein": 0, "fat": 0, "carbs": 0, "fiber": 0, "sodium": 40000.0}},
    "перец": {"grams": 0.5, "nutrients_per_100g": {"calories": 251, "protein": 10.4, "fat": 3.3, "carbs": 64, "fiber": 25.3, "sodium": 20}},
    "оливковое масло": {"grams": 15.0, "nutrients_per_100g": {"calories": 884, "protein": 0, "fat": 100, "carbs": 0, "fiber": 0, "sodium": 2}},
    "сливочное масло": {"grams": 10.0, "nutrients_per_100g": {"calories": 717, "protein": 0.9, "fat": 81.1, "carbs": 0.1, "fiber": 0, "sodium": 11}},
    "базилик": {"grams": 3.0, "nutrients_per_100g": {"calories": 23, "protein": 3.2, "fat": 0.6, "carbs": 2.7, "fiber": 1.6, "sodium": 4}},
    "укроп": {"grams": 15.0, "nutrients_per_100g": {"calories": 43, "protein": 3.5, "fat": 1.1, "carbs": 7.0, "fiber": 2.1, "sodium": 61}},
    "петрушка": {"grams": 15.0, "nutrients_per_100g": {"calories": 36, "protein": 3.0, "fat": 0.8, "carbs": 6.3, "fiber": 3.3, "sodium": 56}},
}

MINOR_AMOUNT_MARKERS = {"по вкусу", "щепотка", "для жарки", "для подачи", "по желанию"}
MINOR_INGREDIENT_TOKENS = {"соль", "перец", "базилик", "укроп", "петрушка", "специи", "пряности"}


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
        grams_per_unit = UNIT_TO_GRAMS[ingredient.unit]
        if ingredient.unit == "стакан":
            grams_per_unit = estimate_cup_weight(ingredient)
        return float(ingredient.amount_value) * grams_per_unit, "explicit_unit", False

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
    if product and isinstance(product.get("nutrients_per_100g"), dict) and product.get("nutrients_per_100g"):
        confidence = "high" if product.get("data_confidence") == "high" else "medium"
        return product["nutrients_per_100g"], product.get("source") or "product_db", confidence
    for key, value in ESTIMATE_DB.items():
        if key in ingredient.name_canonical:
            return value["nutrients_per_100g"], "estimate", "low"
    return None, "unknown", "low"


def estimate_cup_weight(ingredient: StructuredIngredient) -> float:
    name = normalize_text(ingredient.name_canonical)
    for token, grams in VOLUME_HINTS.items():
        if token in name:
            return grams
    return 250.0


def estimate_default_grams(ingredient_name: str, default: float) -> float:
    for key, value in ESTIMATE_DB.items():
        if key in ingredient_name:
            return float(value["grams"])
    return default


def is_minor_ingredient(ingredient: StructuredIngredient) -> bool:
    low = normalize_text(ingredient.name_canonical)
    return any(token in low for token in MINOR_INGREDIENT_TOKENS)
