from __future__ import annotations

from app.modules.rag.ingredient_catalog import build_query_variants, normalize_name_en
from app.modules.rag.normalization import recipe_normalization_service
from app.modules.rag.service import rag_service
from app.modules.rag.usda_resolution_utils import is_safe_candidate
from app.modules.analysis.nutrition_rules import estimate_grams
from app.modules.structuring.fallback_parser import fallback_recipe_parser
from app.modules.structuring.schemas import SimpleRecipeIngredient, SimpleRecipePayload, StructuredIngredient, StructuredRecipe


def test_normalization_backfills_piece_unit_when_llm_drops_it():
    llm_recipe = SimpleRecipePayload(
        title="\u0420\u0430\u0433\u0443",
        ingredients=[
            SimpleRecipeIngredient(
                name="\u041a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c",
                quantity="6-7",
                quantity_text="6-7",
                quantity_value=6.5,
                quantity_unit=None,
            )
        ],
    )
    heuristic_recipe = SimpleRecipePayload(
        title="\u0420\u0430\u0433\u0443",
        ingredients=[SimpleRecipeIngredient(name="\u041a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c", quantity="6-7 \u0448\u0442.")],
    )

    merged = recipe_normalization_service._backfill_missing_quantities(
        llm_recipe,
        heuristic_recipe,
        "\u041a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c - 6-7 \u0448\u0442.",
    )

    assert merged.ingredients[0].quantity_text == "6-7 \u0448\u0442."


def test_piece_unit_hint_with_dot_is_normalized_for_grams():
    amount_value, amount_text, unit = fallback_recipe_parser.parse_quantity("6-7", 6.5, "\u0448\u0442.")
    ingredient = StructuredIngredient(
        name_raw="\u041a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c",
        name_canonical="\u043a\u0430\u0440\u0442\u043e\u0444\u0435\u043b\u044c",
        amount_value=amount_value,
        amount_text=amount_text,
        unit=unit,
    )

    grams, _, _ = estimate_grams(ingredient, product=None)

    assert unit == "\u0448\u0442"
    assert grams == 910.0


def test_pork_brisket_does_not_resolve_through_beef_translation_or_candidate():
    assert normalize_name_en("\u0433\u0440\u0443\u0434\u0438\u043d\u043a\u0430 \u0441\u0432\u0438\u043d\u0430\u044f", "beef") == "pork belly raw"
    assert build_query_variants("\u0433\u0440\u0443\u0434\u0438\u043d\u043a\u0430 \u0441\u0432\u0438\u043d\u0430\u044f", "beef")[0] == "pork belly raw"
    assert not is_safe_candidate(
        {
            "name_raw": "\u0413\u0440\u0443\u0434\u0438\u043d\u043a\u0430 \u0441\u0432\u0438\u043d\u0430\u044f",
            "name_canonical": "\u0433\u0440\u0443\u0434\u0438\u043d\u043a\u0430 \u0441\u0432\u0438\u043d\u0430\u044f",
            "name_en": "beef",
        },
        {"display_name_en": "Beef, New Zealand, imported, manufacturing beef, raw"},
    )


def test_balanced_profile_drops_invented_vegetarian_and_disease_conflicts():
    recipe = StructuredRecipe(title="\u0420\u0430\u0433\u0443", ingredients=[], steps=[], notes=[])
    fallback = {
        "summary": "",
        "detected_issues": ["\u0412\u044b\u0441\u043e\u043a\u0430\u044f \u0434\u043e\u043b\u044f \u0436\u0438\u0440\u043e\u0432 \u043d\u0430 \u043f\u043e\u0440\u0446\u0438\u044e."],
        "recommendations": ["\u0423\u043c\u0435\u043d\u044c\u0448\u0438\u0442\u044c \u0436\u0438\u0440\u043d\u044b\u0435 \u0438\u043d\u0433\u0440\u0435\u0434\u0438\u0435\u043d\u0442\u044b."],
        "warnings": [],
        "compatibility": {"diet": "medium", "restriction": "medium", "goal": "medium"},
        "profile_assessment": {
            "goal_alignment": {
                "key": "goal_alignment",
                "title": "\u0421\u043e\u043e\u0442\u0432\u0435\u0442\u0441\u0442\u0432\u0438\u0435 \u0446\u0435\u043b\u0438",
                "status": "warning",
                "compatibility": "medium",
                "summary": "\u0415\u0441\u0442\u044c \u043d\u044e\u0430\u043d\u0441\u044b \u043f\u043e \u0436\u0438\u0440\u0430\u043c.",
                "evidence": ["\u0412\u044b\u0441\u043e\u043a\u0430\u044f \u0434\u043e\u043b\u044f \u0436\u0438\u0440\u043e\u0432."],
                "recommendations": [],
            },
            "allergy_issues": {
                "key": "allergy_issues",
                "title": "\u0410\u043b\u043b\u0435\u0440\u0433\u0438\u0438",
                "status": "ok",
                "compatibility": "high",
                "summary": "\u0410\u043b\u043b\u0435\u0440\u0433\u0438\u0438 \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435 \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u044b.",
                "evidence": [],
                "recommendations": [],
            },
            "disease_issues": {
                "key": "disease_issues",
                "title": "\u0417\u0430\u0431\u043e\u043b\u0435\u0432\u0430\u043d\u0438\u044f",
                "status": "ok",
                "compatibility": "high",
                "summary": "\u0417\u0430\u0431\u043e\u043b\u0435\u0432\u0430\u043d\u0438\u044f \u0432 \u043f\u0440\u043e\u0444\u0438\u043b\u0435 \u043d\u0435 \u0443\u043a\u0430\u0437\u0430\u043d\u044b.",
                "evidence": [],
                "recommendations": [],
            },
            "preference_alignment": {
                "key": "preference_alignment",
                "title": "\u041f\u0440\u0435\u0434\u043f\u043e\u0447\u0442\u0435\u043d\u0438\u044f",
                "status": "ok",
                "compatibility": "high",
                "summary": "\u041c\u044f\u0441\u043e \u0438 \u0440\u044b\u0431\u0430 \u0440\u0430\u0437\u0440\u0435\u0448\u0435\u043d\u044b.",
                "evidence": [],
                "recommendations": [],
            },
            "additional_restrictions": {
                "key": "additional_restrictions",
                "title": "\u0422\u0438\u043f \u043f\u0438\u0442\u0430\u043d\u0438\u044f \u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f",
                "status": "ok",
                "compatibility": "high",
                "summary": "\u0421\u0431\u0430\u043b\u0430\u043d\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u043f\u0438\u0442\u0430\u043d\u0438\u0435.",
                "evidence": [],
                "recommendations": [],
            },
        },
    }
    result = {
        **fallback,
        "profile_assessment": {
            **fallback["profile_assessment"],
            "disease_issues": {
                **fallback["profile_assessment"]["disease_issues"],
                "status": "conflict",
                "compatibility": "low",
                "summary": "\u0420\u0435\u0446\u0435\u043f\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u0441\u0432\u0438\u043d\u0438\u043d\u0443, \u0447\u0442\u043e \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0442 \u0432\u0435\u0433\u0435\u0442\u0430\u0440\u0438\u0430\u043d\u0441\u043a\u043e\u043c\u0443 \u043f\u0438\u0442\u0430\u043d\u0438\u044e.",
                "evidence": ["\u0421\u0432\u0438\u043d\u0438\u043d\u0430 \u043f\u0440\u0438\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u0435\u0442."],
                "recommendations": ["\u0417\u0430\u043c\u0435\u043d\u0438\u0442\u044c \u043c\u044f\u0441\u043e \u043d\u0430 \u0431\u043e\u0431\u043e\u0432\u044b\u0435."],
            },
            "preference_alignment": {
                **fallback["profile_assessment"]["preference_alignment"],
                "status": "conflict",
                "compatibility": "low",
                "summary": "\u0420\u0435\u0446\u0435\u043f\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043c\u044f\u0441\u043e, \u0447\u0442\u043e \u043f\u0440\u043e\u0442\u0438\u0432\u043e\u0440\u0435\u0447\u0438\u0442 \u0432\u044b\u0441\u043e\u043a\u043e\u0431\u0435\u043b\u043a\u043e\u0432\u043e\u0439 \u0434\u0438\u0435\u0442\u0435 \u0431\u0435\u0437 \u043c\u044f\u0441\u0430.",
                "evidence": ["\u0412\u044b\u0441\u043e\u043a\u043e\u0431\u0435\u043b\u043a\u043e\u0432\u0430\u044f \u0434\u0438\u0435\u0442\u0430", "\u041c\u043e\u0436\u043d\u043e \u043c\u044f\u0441\u043e \u0438 \u0440\u044b\u0431\u0443"],
                "recommendations": [],
            },
        },
    }
    nutrition_result = {
        "profile_context": {
            "diet_code": None,
            "raw_diet_type": "\u0421\u0431\u0430\u043b\u0430\u043d\u0441\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u043e\u0435 \u043f\u0438\u0442\u0430\u043d\u0438\u0435",
            "raw_diseases": [],
            "raw_allergies": [],
            "raw_preferences": ["\u0412\u044b\u0441\u043e\u043a\u043e\u0431\u0435\u043b\u043a\u043e\u0432\u0430\u044f \u0434\u0438\u0435\u0442\u0430", "\u041c\u043e\u0436\u043d\u043e \u043c\u044f\u0441\u043e \u0438 \u0440\u044b\u0431\u0443"],
            "preference_codes": [],
            "allergy_codes": [],
        },
        "detailed_ingredients": [],
    }

    sanitized = rag_service._sanitize_irrelevant_profile_blocks(recipe, result, fallback, nutrition_result)

    assert sanitized["profile_assessment"]["disease_issues"]["status"] == "ok"
    assert sanitized["profile_assessment"]["preference_alignment"]["status"] == "ok"
    assert "\u0432\u0435\u0433\u0435\u0442" not in str(sanitized).lower()


def test_allergy_warning_is_dropped_without_matching_recipe_allergen():
    recipe = StructuredRecipe(title="\u0411\u0430\u0431\u0430\u0433\u0430\u043d\u0443\u0448", ingredients=[], steps=[], notes=[])
    fallback = {
        "summary": "",
        "detected_issues": [],
        "recommendations": [],
        "warnings": [],
        "compatibility": {"diet": "high", "restriction": "high", "goal": "high"},
        "profile_assessment": {
            "allergy_issues": {
                "key": "allergy_issues",
                "title": "\u0410\u043b\u043b\u0435\u0440\u0433\u0438\u0438",
                "status": "ok",
                "compatibility": "high",
                "summary": "\u0421\u0440\u0435\u0434\u0438 \u0440\u0430\u0441\u043f\u043e\u0437\u043d\u0430\u043d\u043d\u044b\u0445 \u0438\u043d\u0433\u0440\u0435\u0434\u0438\u0435\u043d\u0442\u043e\u0432 \u043f\u0440\u044f\u043c\u043e\u0433\u043e \u0441\u043e\u0432\u043f\u0430\u0434\u0435\u043d\u0438\u044f \u0441 \u044d\u0442\u0438\u043c\u0438 \u0430\u043b\u043b\u0435\u0440\u0433\u0435\u043d\u0430\u043c\u0438 \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d\u043e.",
                "evidence": [],
                "recommendations": [],
            },
            "disease_issues": {
                "key": "disease_issues",
                "title": "\u0417\u0430\u0431\u043e\u043b\u0435\u0432\u0430\u043d\u0438\u044f",
                "status": "ok",
                "compatibility": "high",
                "summary": "",
                "evidence": [],
                "recommendations": [],
            },
        },
    }
    result = {
        **fallback,
        "profile_assessment": {
            **fallback["profile_assessment"],
            "allergy_issues": {
                **fallback["profile_assessment"]["allergy_issues"],
                "status": "warning",
                "compatibility": "medium",
                "summary": "\u0420\u0435\u0446\u0435\u043f\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043a\u0440\u0435\u0432\u0435\u0442\u043a\u0438, \u0447\u0442\u043e \u0432\u044b\u0437\u044b\u0432\u0430\u0435\u0442 \u0430\u043b\u043b\u0435\u0440\u0433\u0438\u044e.",
                "evidence": ["\u041a\u0440\u0435\u0432\u0435\u0442\u043a\u0438 \u0443\u043a\u0430\u0437\u0430\u043d\u044b \u043a\u0430\u043a \u0438\u043d\u0433\u0440\u0435\u0434\u0438\u0435\u043d\u0442."],
                "recommendations": [],
            },
        },
    }
    nutrition_result = {
        "profile_context": {
            "raw_allergies": ["\u041a\u0440\u0435\u0432\u0435\u0442\u043a\u0438", "\u043c\u043e\u0440\u0435\u043f\u0440\u043e\u0434\u0443\u043a\u0442\u044b"],
            "raw_diseases": [],
            "allergy_codes": ["shellfish"],
            "diet_code": None,
        },
        "detailed_ingredients": [
            {"ingredient": {"name_raw": "\u0431\u0430\u043a\u043b\u0430\u0436\u0430\u043d\u044b", "name_canonical": "\u0431\u0430\u043a\u043b\u0430\u0436\u0430\u043d\u044b", "name_en": "eggplant raw"}}
        ],
    }

    sanitized = rag_service._sanitize_irrelevant_profile_blocks(recipe, result, fallback, nutrition_result)

    assert sanitized["profile_assessment"]["allergy_issues"]["status"] == "ok"
    assert "\u043a\u0440\u0435\u0432\u0435\u0442" not in str(sanitized["profile_assessment"]["allergy_issues"]).lower()


def test_false_plant_and_gluten_claims_are_removed_from_analysis_text():
    result = {
        "detected_issues": [
            "\u041e\u0440\u0435\u0445\u0438 \u0433\u0440\u0435\u0446\u043a\u0438\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u0436\u0438\u0440\u044b.",
            "\u0421\u0443\u0445\u0430\u0440\u0438 \u043f\u0430\u043d\u0438\u0440\u043e\u0432\u043e\u0447\u043d\u044b\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u044b.",
            "\u0421\u0443\u0445\u0430\u0440\u0438 \u043f\u0430\u043d\u0438\u0440\u043e\u0432\u043e\u0447\u043d\u044b\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0433\u043b\u044e\u0442\u0435\u043d.",
            "\u041f\u0440\u0438\u0441\u0443\u0442\u0441\u0442\u0432\u0443\u044e\u0442 \u0433\u0440\u0435\u0446\u043a\u0438\u0435 \u043e\u0440\u0435\u0445\u0438 (\u0430\u043b\u043b\u0435\u0440\u0433\u0435\u043d \u0433\u043b\u044e\u0442\u0435\u043d).",
        ],
        "recommendations": [],
        "compatibility": {"diet": "medium", "restriction": "medium", "goal": "medium"},
        "profile_assessment": {
            "additional_restrictions": {
                "key": "additional_restrictions",
                "title": "\u0422\u0438\u043f \u043f\u0438\u0442\u0430\u043d\u0438\u044f \u0438 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u044f",
                "status": "warning",
                "compatibility": "medium",
                "summary": "\u0415\u0441\u0442\u044c \u043d\u044e\u0430\u043d\u0441\u044b.",
                "evidence": [
                    "\u0420\u0435\u0446\u0435\u043f\u0442 \u0441\u043e\u0434\u0435\u0440\u0436\u0438\u0442 \u043e\u0440\u0435\u0445\u0438, \u043a\u043e\u0442\u043e\u0440\u044b\u0435 \u043d\u0435 \u044f\u0432\u043b\u044f\u044e\u0442\u0441\u044f \u0440\u0430\u0441\u0442\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u043c\u0438 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u0430\u043c\u0438.",
                    "\u0421\u0443\u0445\u0430\u0440\u0438 \u043f\u0430\u043d\u0438\u0440\u043e\u0432\u043e\u0447\u043d\u044b\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0433\u043b\u044e\u0442\u0435\u043d.",
                ],
                "recommendations": [],
            }
        },
    }
    nutrition_result = {"profile_context": {"diet_code": None}, "detailed_ingredients": []}

    sanitized = rag_service._sanitize_obvious_personalization_hallucinations(result, nutrition_result)
    serialized = str(sanitized).lower()

    assert "\u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u0436\u0438\u0440\u044b" not in serialized
    assert "\u0436\u0438\u0432\u043e\u0442\u043d\u044b\u0435 \u043f\u0440\u043e\u0434\u0443\u043a\u0442\u044b" not in serialized
    assert "\u043e\u0440\u0435\u0445\u0438 (\u0430\u043b\u043b\u0435\u0440\u0433\u0435\u043d \u0433\u043b\u044e\u0442\u0435\u043d" not in serialized
    assert "\u0441\u0443\u0445\u0430\u0440\u0438 \u043f\u0430\u043d\u0438\u0440\u043e\u0432\u043e\u0447\u043d\u044b\u0435 \u0441\u043e\u0434\u0435\u0440\u0436\u0430\u0442 \u0433\u043b\u044e\u0442\u0435\u043d" in serialized
