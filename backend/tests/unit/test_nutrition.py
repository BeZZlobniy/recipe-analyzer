from __future__ import annotations

from app.modules.analysis.nutrition import nutrition_service
from app.modules.analysis.nutrition_rules import estimate_grams, resolve_nutrients
from app.modules.analysis.personalization import personalization_service
from app.modules.analysis.portions import portion_service
from app.modules.structuring.schemas import StructuredIngredient, StructuredRecipe


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


def test_estimate_grams_corrects_llm_kg_value_already_in_grams():
    ingredient = StructuredIngredient(
        name_raw="Свинина",
        name_canonical="свинина",
        amount_value=1000.0,
        amount_text="1 кг",
        unit="кг",
    )

    grams, reason, used_fallback = estimate_grams(ingredient, product=None)

    assert grams == 1000.0
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

    result = nutrition_service.calculate([ingredient], matches, {"servings": 2, "goal": "maintenance"})

    assert result["nutrition_total"]["calories"]["value"] == 200.0
    assert result["nutrition_per_serving"]["calories"]["value"] == 100.0
    assert result["analysis_quality"]["matched_ratio"] == 1.0
    assert result["analysis_quality"]["unresolved_ratio"] == 0.0
    assert result["unresolved_ingredients"] == []


def test_personalization_builds_profile_context_for_rag():
    context = personalization_service.build_profile_context(
        {
            "diet_type": "Вегетарианец",
            "goal": "Поддержание здорового питания",
            "allergies_json": ["Лактоза", "молочные продукты"],
            "diseases_json": [],
            "preferences_json": ["Не люблю острое"],
            "restrictions_text": "меньше соли",
            "target_recipe_calories": 650,
        }
    )

    assert context["diet_code"] == "vegetarian"
    assert context["goal_code"] == "maintenance"
    assert "dairy" in context["allergy_codes"]
    assert "avoid_spicy" in context["preference_codes"]
    assert "vegetarian diet" in context["rag_queries"]
    assert "lactose intolerance dairy allergy" in context["rag_queries"]
    assert {"kind": "allergy", "value": "Лактоза"} in context["profile_constraints"]
    assert any("food allergy hidden sources" in query for query in context["rag_queries"])
    assert context["target_recipe_calories"] == 650.0


def test_personalization_keeps_unknown_profile_constraints_for_rag():
    context = personalization_service.build_profile_context(
        {
            "diet_type": "Обычное питание",
            "goal": "Контроль самочувствия",
            "allergies_json": ["цитрусовые"],
            "diseases_json": ["подагра"],
            "preferences_json": ["не ем свинину"],
            "restrictions_text": "минимум жареного и острых соусов",
        }
    )

    assert {"kind": "disease", "value": "подагра"} in context["profile_constraints"]
    assert {"kind": "preference", "value": "не ем свинину"} in context["profile_constraints"]
    assert "gout" in context["disease_codes"]
    assert "avoid_pork" in context["preference_codes"]
    assert "avoid_fried" in context["preference_codes"]
    assert "gout uric acid purine foods" in context["rag_queries"]
    assert "no pork pork-free diet" in context["rag_queries"]
    assert any("medical nutrition therapy recipe restrictions" in query for query in context["rag_queries"])
    assert any("personal food restriction forbidden ingredients" in query for query in context["rag_queries"])


def test_personalization_keeps_custom_food_restrictions_out_of_allergy_codes():
    context = personalization_service.build_profile_context(
        {
            "diet_type": "Веган",
            "goal": "Поддержание здорового питания",
            "allergies_json": ["Глютен"],
            "diseases_json": [],
            "preferences_json": [],
            "restrictions_text": "Без мяса, рыбы, молочных продуктов, яиц, меда и пшеничной муки.",
        }
    )

    assert context["allergy_codes"] == ["gluten"]
    assert "dairy" in context["restriction_food_codes"]
    assert "eggs" in context["restriction_food_codes"]
    assert "gluten free" in context["rag_queries"]


def test_portion_guidance_uses_target_recipe_calories_as_recipe_divisor():
    recipe = StructuredRecipe(
        title="Беляши",
        ingredients=[],
        steps=["Разделить тесто на 8 равных частей."],
        notes=[],
    )
    nutrition_total = {"calories": {"value": 1600.0}}

    estimated = portion_service.estimate_recipe_servings(recipe, "Разделить тесто на 8 равных частей.")
    recommended = portion_service.recommend_recipe_servings(
        estimated_recipe_servings=estimated,
        nutrition_total=nutrition_total,
        target_recipe_calories=650,
    )
    guidance = portion_service.build_guidance(
        estimated_recipe_servings=estimated,
        recommended_recipe_servings=recommended,
        nutrition_total=nutrition_total,
        target_recipe_calories=650,
    )

    assert estimated == 8
    assert recommended == 3
    assert guidance["estimated_recipe_servings"] == 8
    assert guidance["recommended_recipe_servings"] == 3
    assert guidance["calories_per_recommended_serving"] == 533.33
    assert "650" in str(guidance["summary"])
