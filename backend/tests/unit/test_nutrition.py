from __future__ import annotations

from app.modules.analysis.nutrition import nutrition_service
from app.modules.analysis.nutrition_rules import estimate_grams, resolve_nutrients
from app.modules.structuring.schemas import StructuredIngredient


def test_estimate_grams_uses_explicit_tablespoon_conversion():
    ingredient = StructuredIngredient(
        name_raw="Оливковое масло",
        name_canonical="оливковое масло",
        amount_value=2.0,
        amount_text="2 ст. л.",
        unit="ст. л.",
    )

    grams, reason, used_fallback = estimate_grams(ingredient, product=None)

    assert grams == 30.0
    assert reason == "explicit_unit"
    assert used_fallback is False


def test_estimate_grams_uses_piece_hint_for_eggs():
    ingredient = StructuredIngredient(
        name_raw="Яйцо",
        name_canonical="яйцо",
        amount_value=2.0,
        amount_text="2 шт.",
        unit="шт",
    )

    grams, reason, used_fallback = estimate_grams(ingredient, product=None)

    assert grams == 100.0
    assert reason == "piece_estimate"
    assert used_fallback is True


def test_resolve_nutrients_prefers_product_source():
    ingredient = StructuredIngredient(
        name_raw="Пармезан",
        name_canonical="пармезан",
        amount_value=50.0,
        amount_text="50 г",
        unit="г",
    )
    product = {
        "source": "usda",
        "data_confidence": "high",
        "nutrients_per_100g": {
            "calories": 400.0,
            "protein": 30.0,
            "fat": 28.0,
            "carbs": 4.0,
            "fiber": 0.0,
            "sodium": 1200.0,
        },
    }

    nutrients, source, confidence = resolve_nutrients(ingredient, product)

    assert nutrients == product["nutrients_per_100g"]
    assert source == "usda"
    assert confidence == "high"


def test_nutrition_service_calculates_totals_and_quality():
    ingredient = StructuredIngredient(
        name_raw="Пармезан",
        name_canonical="пармезан",
        amount_value=50.0,
        amount_text="50 г",
        unit="г",
    )
    matches = [
        {
            "ingredient": {"name_canonical": "пармезан"},
            "match_status": "matched",
            "matched_name": "parmesan cheese",
            "matched_source": "usda",
            "match_method": "query",
            "match_confidence": "high",
            "selection_reason": "exact",
            "top_candidates": [],
            "matched_product": {
                "source": "usda",
                "data_confidence": "high",
                "nutrients_per_100g": {
                    "calories": 400.0,
                    "protein": 30.0,
                    "fat": 28.0,
                    "carbs": 4.0,
                    "fiber": 0.0,
                    "sodium": 1200.0,
                },
            },
        }
    ]

    result = nutrition_service.calculate([ingredient], matches, {"servings": 2})

    assert result["nutrition_total"]["calories"]["value"] == 200.0
    assert result["nutrition_per_serving"]["calories"]["value"] == 100.0
    assert result["analysis_quality"]["matched_ratio"] == 1.0
    assert result["analysis_quality"]["unresolved_ratio"] == 0.0
    assert result["unresolved_ingredients"] == []
