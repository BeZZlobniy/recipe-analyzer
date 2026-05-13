from __future__ import annotations

from app.modules.rag.normalization import recipe_normalization_service
from app.modules.structuring.fallback_parser import fallback_recipe_parser
from app.modules.structuring.schemas import SimpleRecipeIngredient, SimpleRecipePayload


def test_parse_ingredient_line_extracts_name_and_quantity():
    items = fallback_recipe_parser.parse_ingredient_line("Яйцо - 2 шт.")

    assert items is not None
    assert len(items) == 1
    assert items[0].name == "Яйцо"
    assert items[0].quantity == "2 шт"


def test_extract_servings_from_recipe_text():
    servings = fallback_recipe_parser.extract_servings("Паста карбонара на 2-4 порции")

    assert servings == "2-4"


def test_build_recipe_collects_title_ingredients_and_steps():
    recipe = fallback_recipe_parser.build_recipe(
        "\n".join(
            [
                "Блины с яблоками",
                "",
                "Ингредиенты:",
                "- Молоко - 500 мл",
                "- Яйцо - 2 шт.",
                "",
                "Приготовление:",
                "1. Смешать ингредиенты.",
                "2. Обжарить на сковороде.",
            ]
        )
    )

    assert recipe.title == "Блины с яблоками"
    assert len(recipe.ingredients) == 2
    assert recipe.ingredients[0].name == "Молоко"
    assert recipe.ingredients[0].quantity == "500 мл"
    assert recipe.instructions
    assert recipe.instructions[-1] == "Обжарить на сковороде."


def test_sanitize_name_preserves_meat_qualifier_from_parentheses():
    cleaned = fallback_recipe_parser.sanitize_name("Мясо (говядина и свинина)")

    assert "говядина" in cleaned
    assert "свинина" in cleaned


def test_normalization_prefers_explicit_quantity_text_over_inconsistent_llm_value():
    recipe = SimpleRecipePayload(
        title="Бисквитный рулет",
        ingredients=[
            SimpleRecipeIngredient(
                name="густое варенье",
                quantity="100 г",
                quantity_text="100 г",
                quantity_value=150.0,
                quantity_unit="г",
            )
        ],
    )

    normalized = recipe_normalization_service._backfill_missing_quantities(recipe, SimpleRecipePayload(title="x"), "")

    assert normalized.ingredients[0].quantity_value == 100.0
    assert normalized.ingredients[0].quantity_unit == "г"
