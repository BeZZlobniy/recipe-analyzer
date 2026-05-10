from __future__ import annotations

from app.modules.rag.service import rag_service
from app.modules.structuring.schemas import StructuredIngredient, StructuredRecipe


def test_profile_conflict_guard_restores_missed_vegan_meat_conflict():
    recipe = StructuredRecipe(
        title="Мясные котлеты",
        ingredients=[
            StructuredIngredient(name_raw="Свинина", name_canonical="свинина", amount_text="1 кг"),
            StructuredIngredient(name_raw="Яйца", name_canonical="яйца", amount_text="4 шт."),
        ],
        steps=[],
        notes=[],
    )
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegan",
            "raw_diet_type": "Веган",
            "allergy_codes": ["gluten"],
            "profile_items": ["Веган", "Глютен"],
        },
        "detailed_ingredients": [
            {"ingredient": {"name_raw": "Свинина", "name_canonical": "свинина"}},
            {"ingredient": {"name_raw": "Яйца", "name_canonical": "яйца"}},
        ],
        "warnings": [],
        "unresolved_ingredients": [],
        "portion_guidance": {},
    }
    llm_result = {
        "summary": "Рецепт выглядит нейтрально для выбранного профиля, явных конфликтов нет.",
        "detected_issues": ["Явных конфликтов с выбранным профилем не выявлено."],
        "recommendations": ["Можно сохранить рецепт."],
        "warnings": [],
        "compatibility": {"diet": "high", "restriction": "high", "goal": "high"},
        "profile_assessment": {
            "additional_restrictions": {
                "summary": "Конфликтов не найдено.",
                "evidence": [],
                "recommendations": [],
            }
        },
    }

    result = rag_service._merge_with_fallback(recipe, nutrition_result, [], llm_result, [])

    assert result["compatibility"]["diet"] == "low"
    assert any("Веганский тип питания" in issue for issue in result["detected_issues"])
    assert result["profile_assessment"]["additional_restrictions"]["status"] == "conflict"


def test_profile_conflict_guard_does_not_match_eggplant_or_millet_as_restricted_foods():
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegan",
            "allergy_codes": ["gluten"],
        },
        "matched_ingredients": [
            {
                "ingredient": {
                    "name_raw": "Баклажаны",
                    "name_canonical": "баклажаны",
                    "name_en": "eggplant raw",
                },
                "matched_name": "Eggplant, raw",
            },
            {
                "ingredient": {
                    "name_raw": "Пшено",
                    "name_canonical": "пшено",
                    "name_en": "millet",
                },
                "matched_name": "Millet, raw",
            },
        ],
        "detailed_ingredients": [],
    }

    assert rag_service._detect_hard_profile_conflicts(nutrition_result) == []


def test_profile_analysis_sanitizes_false_non_plant_llm_claims():
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegan",
            "raw_diet_type": "Веган",
            "allergy_codes": [],
        },
        "matched_ingredients": [
            {"ingredient": {"name_raw": "Лук", "name_canonical": "лук", "name_en": "onion raw"}},
            {"ingredient": {"name_raw": "Помидоры", "name_canonical": "помидоры", "name_en": "tomatoes raw"}},
            {"ingredient": {"name_raw": "Соль", "name_canonical": "соль", "name_en": "salt"}},
            {"ingredient": {"name_raw": "Перец", "name_canonical": "перец", "name_en": "black pepper"}},
        ],
        "detailed_ingredients": [],
        "warnings": [],
        "unresolved_ingredients": [],
        "nutrition_total": {},
        "nutrition_per_serving": {},
        "analysis_quality": {},
        "portion_guidance": {},
    }
    result = {
        "summary": "Ингредиент лук не является растительной едой.",
        "detected_issues": [
            "Ингредиент лук не является растительной едой.",
            "Ингредиент помидоры не являются растительной едой.",
            "Ингредиент соль не является растительной едой.",
            "Ингредиент перец не является растительной едой.",
        ],
        "recommendations": ["Исключить лук, потому что он не является растительной едой."],
        "warnings": [],
        "compatibility": {"diet": "low", "restriction": "medium", "goal": "high"},
        "profile_assessment": {
            "additional_restrictions": {
                "summary": "Ингредиент лук не является растительной едой.",
                "evidence": ["Ингредиент помидоры не являются растительной едой."],
                "recommendations": ["Исключить соль, потому что она не является растительной едой."],
            }
        },
    }

    sanitized = rag_service._sanitize_obvious_personalization_hallucinations(result, nutrition_result)

    serialized = str(sanitized)
    assert "не является растительной едой" not in serialized
    assert sanitized["compatibility"]["diet"] == "high"
    assert sanitized["profile_assessment"]["additional_restrictions"]["status"] == "ok"
