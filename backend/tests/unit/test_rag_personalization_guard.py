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


def test_profile_conflict_guard_detects_ham_for_vegetarian_profile():
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegetarian",
            "allergy_codes": [],
        },
        "matched_ingredients": [
            {
                "ingredient": {
                    "name_raw": "Ветчина",
                    "name_canonical": "ветчина",
                    "name_en": "ham",
                },
                "matched_name": "Ham",
            }
        ],
        "detailed_ingredients": [],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert any(item["assessment_key"] == "additional_restrictions" for item in conflicts)


def test_profile_conflict_guard_detects_pasta_for_gluten_allergy():
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegan",
            "allergy_codes": ["gluten"],
        },
        "matched_ingredients": [
            {
                "ingredient": {
                    "name_raw": "Макароны пшеничные",
                    "name_canonical": "макароны",
                    "name_en": "wheat pasta",
                },
                "matched_name": "Pasta, dry, enriched",
            }
        ],
        "detailed_ingredients": [],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert any(item["assessment_key"] == "allergy_issues" for item in conflicts)


def test_profile_conflict_guard_detects_shrimp_for_vegan_profile():
    nutrition_result = {
        "profile_context": {
            "diet_code": "vegan",
            "allergy_codes": [],
        },
        "matched_ingredients": [
            {
                "ingredient": {
                    "name_raw": "Креветки очищенные",
                    "name_canonical": "креветки очищенные",
                    "name_en": "shrimp",
                },
                "matched_name": "Shrimp, raw",
            }
        ],
        "detailed_ingredients": [],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert any(item["assessment_key"] == "additional_restrictions" for item in conflicts)


def test_profile_guard_treats_eggs_and_dairy_as_allowed_for_vegetarian_diet_block():
    text = "Яйца куриные конфликтуют с вегетарианским питанием, а сметана не является растительной."

    assert rag_service._contains_false_vegetarian_claim(text, {"diet_code": "vegetarian"})
    assert not rag_service._contains_false_vegetarian_claim(text, {"diet_code": "vegan"})


def test_profile_guard_removes_unsupported_disliked_ingredient_claims():
    assert rag_service._is_unsupported_preference_claim(
        "Рецепт содержит чеснок, который пользователь не любит.",
        {"raw_preferences": ["Растительная еда", "Не люблю острое"], "raw_restrictions": []},
    )
    assert not rag_service._is_unsupported_preference_claim(
        "Блюдо острое, а пользователь не любит острое.",
        {"raw_preferences": ["Не люблю острое"], "raw_restrictions": []},
    )


def test_kb_source_hints_cover_profile_and_recipe_risks():
    recipe = StructuredRecipe(
        title="Жареный сэндвич с ветчиной и сыром",
        ingredients=[
            StructuredIngredient(name_raw="Хлеб", name_canonical="хлеб", amount_text="4 кусочка"),
            StructuredIngredient(name_raw="Ветчина", name_canonical="ветчина", amount_text="100 г"),
            StructuredIngredient(name_raw="Сыр", name_canonical="сыр", amount_text="90 г"),
        ],
        steps=[],
        notes=[],
    )
    hints = rag_service._kb_source_hints(
        {
            "diet_code": "vegetarian",
            "goal_code": "maintenance",
            "allergy_codes": ["dairy"],
            "restriction_food_codes": [],
            "disease_codes": [],
            "preference_codes": ["high_protein"],
        },
        [
            {
                "name_canonical": "ветчина",
                "name_en": "ham",
                "matched_name": "Ham",
            },
            {
                "name_canonical": "сыр",
                "name_en": "cheese",
                "matched_name": "Cheese, Parmesan, hard",
            },
            {
                "name_canonical": "хлеб",
                "name_en": "bread",
                "matched_name": "Bread, white",
            },
        ],
        {"portion_guidance": {"target_recipe_calories": 650}},
        [{"code": "high_sodium", "label": "Высокий натрий"}],
        recipe,
    )

    assert "kb_vegetarian.txt" in hints
    assert "kb_lactose_intolerance.txt" in hints
    assert "kb_gluten_free.txt" in hints
    assert "kb_low_sodium.txt" in hints
    assert "kb_high_protein.txt" in hints


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


def test_profile_analysis_filters_raw_profile_text_from_detected_issues():
    nutrition_result = {
        "profile_context": {
            "diet_code": "balanced",
            "raw_preferences": ["Высокобелковая диета", "Можно мясо и рыбу"],
            "raw_restrictions": ["Хочу больше белка и умеренную калорийность на порцию."],
        },
        "detailed_ingredients": [],
    }
    result = {
        "summary": "Рецепт подходит.",
        "detected_issues": [
            "Высокобелковая диета",
            "Можно мясо и рыбу",
            "Высокая доля жиров на рекомендованную порцию.",
        ],
        "recommendations": [],
        "compatibility": {"diet": "high", "restriction": "high", "goal": "medium"},
        "profile_assessment": {},
    }

    sanitized = rag_service._sanitize_obvious_personalization_hallucinations(result, nutrition_result)

    assert sanitized["detected_issues"] == ["Высокая доля жиров на рекомендованную порцию."]


def test_profile_compatibility_uses_status_not_llm_low_label():
    assert rag_service._normalize_block_compatibility("low", "warning", "high") == "medium"
    assert rag_service._normalize_block_compatibility("low", "ok", "medium") == "high"
    assert rag_service._normalize_block_compatibility("high", "conflict", "high") == "low"

    compatibility = rag_service._compatibility_from_assessment(
        {"diet": "medium", "restriction": "medium", "goal": "medium"},
        {
            "goal_alignment": {"status": "warning", "compatibility": "low"},
            "allergy_issues": {"status": "ok", "compatibility": "high"},
            "disease_issues": {"status": "warning", "compatibility": "low"},
            "preference_alignment": {"status": "ok", "compatibility": "high"},
            "additional_restrictions": {"status": "ok", "compatibility": "high"},
        },
    )

    assert compatibility == {"diet": "high", "restriction": "medium", "goal": "medium"}


def test_profile_analysis_filters_low_sodium_hallucinations():
    nutrition_result = {
        "profile_context": {"diet_code": "balanced", "raw_diseases": ["гипертония"]},
        "nutrition_per_serving": {"sodium": {"value": 84.0, "percent_of_target": 5.6}},
        "detailed_ingredients": [],
    }
    result = {
        "summary": "Рецепт подходит.",
        "detected_issues": [
            "Содержание натрия 84 мг, что составляет 5.6% от рекомендуемой нормы.",
            "Высокий натрий: несколько обработанных соленых ингредиентов.",
        ],
        "recommendations": ["Уменьшить соль."],
        "compatibility": {"diet": "high", "restriction": "low", "goal": "medium"},
        "profile_assessment": {
            "disease_issues": {
                "status": "warning",
                "compatibility": "low",
                "summary": "Высокий натрий может быть проблемой при гипертонии.",
                "evidence": ["Содержание натрия 84 мг, что составляет 5.6% от рекомендуемой нормы."],
                "recommendations": ["Снизить соль."],
            }
        },
    }

    sanitized = rag_service._sanitize_obvious_personalization_hallucinations(result, nutrition_result)

    assert sanitized["detected_issues"] == ["Явных конфликтов с выбранным профилем не выявлено."]
    assert sanitized["recommendations"] == []
    assert sanitized["profile_assessment"]["disease_issues"]["status"] == "ok"
    assert sanitized["compatibility"]["restriction"] == "high"


def test_profile_analysis_filters_false_vegan_conflict_for_plant_items():
    assert rag_service._is_false_non_plant_claim("Грецкие орехи и соль противоречат веганскому питанию.")
    assert rag_service._is_false_non_plant_claim("Оливковое масло не является животным продуктом.")


def test_profile_conflict_guard_detects_cream_for_dairy_restriction():
    nutrition_result = {
        "profile_context": {"allergy_codes": ["dairy"], "restriction_food_codes": []},
        "detailed_ingredients": [{"ingredient": {"name_raw": "сливки жирные", "name_canonical": "сливки"}}],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert any(item["assessment_key"] == "allergy_issues" for item in conflicts)


def test_profile_conflict_guard_detects_baguette_for_gluten_restriction():
    nutrition_result = {
        "profile_context": {"allergy_codes": ["gluten"], "restriction_food_codes": []},
        "detailed_ingredients": [{"ingredient": {"name_raw": "багет", "name_canonical": "багет"}}],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert any(item["assessment_key"] == "allergy_issues" for item in conflicts)


def test_profile_conflict_guard_does_not_treat_tomato_paste_or_millet_as_gluten():
    nutrition_result = {
        "profile_context": {"allergy_codes": ["gluten"], "restriction_food_codes": []},
        "detailed_ingredients": [
            {"ingredient": {"name_raw": "томатная паста", "name_canonical": "томатная паста"}},
            {"ingredient": {"name_raw": "пшено", "name_canonical": "пшено"}},
        ],
    }

    conflicts = rag_service._detect_hard_profile_conflicts(nutrition_result)

    assert conflicts == []


def test_profile_analysis_filters_false_millet_and_egg_claims():
    assert rag_service._is_false_gluten_claim("Пшено является продуктом из пшеницы.")
    assert rag_service._is_false_gluten_claim("Блюдо содержит пшено (пшеничную муку).")
    assert rag_service._contains_false_vegetarian_claim(
        "Содержание яиц в рецепте несовместимо с вегетарианским питанием.",
        {"diet_code": "vegetarian"},
    )


def test_profile_analysis_filters_foreign_and_unsupported_low_carb_claims():
    profile_context = {"raw_goal": "контроль сахара", "raw_preferences": [], "raw_restrictions": []}
    low_carb_context = {"diet_code": "low_carb"}

    assert rag_service._contains_cjk_text("钠含量为360 mg")
    assert rag_service._is_unsupported_diet_pattern_claim(
        "Говядина в рецепте противоречит низкоуглеводному питанию.",
        profile_context,
    )
    assert rag_service._is_false_low_carb_allowed_food_claim(
        "Молоко и сливочное масло содержат животные жиры, которые несовместимы с низкоуглеводным питанием.",
        low_carb_context,
    )
    assert rag_service._is_analysis_artifact_issue("portion_guidance:recommended_recipe_servings=6")
    assert rag_service._is_analysis_artifact_issue("nutrition_signals.high_sodium")
