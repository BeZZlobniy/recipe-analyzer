from __future__ import annotations

from app.modules.evaluation.recipe_suite import (
    evaluate_analysis,
    expected_profile_statuses,
    resolve_profile,
)
from app.modules.rag.retrieval import SOURCE_HINT_PREFIX, RetrievalService


def test_expected_profile_statuses_detect_vegan_and_gluten_conflicts():
    recipe = {"flags": ["meat", "gluten", "dairy"]}
    profile = {"diet": "vegan", "allergy_flags": ["gluten"], "disease_flags": [], "preference_flags": []}

    statuses = expected_profile_statuses(recipe, profile)

    assert statuses["additional_restrictions"] == "conflict"
    assert statuses["allergy_issues"] == "conflict"


def test_resolve_profile_uses_name_contains_aliases():
    expectations = {
        "profiles": {
            "sergey_muscle_gain": {
                "name_contains": ["сергей"],
                "diet": "balanced",
            }
        }
    }

    slug, profile = resolve_profile("Сергей, набор мышечной массы", expectations)

    assert slug == "sergey_muscle_gain"
    assert profile["diet"] == "balanced"


def test_evaluate_analysis_flags_amount_match_and_profile_errors():
    expectations = {
        "global_match_rules": [{"ingredient": "укроп", "banned_match_contains": ["pickle"]}],
        "false_claim_patterns": ["животные продукты"],
    }
    recipe = {
        "index": 1,
        "title": "Тест",
        "required_ingredients": ["молоко", "укроп"],
        "amount_ranges": [{"ingredient": "молоко", "min_g": 180, "max_g": 300}],
        "flags": ["dairy", "gluten"],
        "expected_kb_sources": ["kb_lactose_intolerance.txt"],
    }
    profile = {
        "diet": "vegan",
        "allergy_flags": ["gluten"],
        "disease_flags": [],
        "preference_flags": [],
        "expected_kb_sources": ["kb_vegan.txt"],
        "noise_phrases": ["Без мяса"],
    }
    result = {
        "title": "Тест",
        "structured_recipe": {
            "ingredients": [
                {"name_canonical": "молоко"},
                {"name_canonical": "укроп"},
            ]
        },
        "detailed_ingredients": [
            {
                "ingredient": {"name_canonical": "молоко"},
                "estimated_grams": 60,
                "grams_reason": "explicit_unit",
                "match_confidence": "high",
                "nutrition_resolution_status": "resolved",
                "matched_name": "MILK",
            },
            {
                "ingredient": {"name_canonical": "укроп"},
                "estimated_grams": 5,
                "match_confidence": "high",
                "nutrition_resolution_status": "resolved",
                "matched_name": "Pickles, dill",
            },
        ],
        "rag_context": [{"source": "kb_vegan.txt"}],
        "detected_issues": ["Без мяса", "Укроп содержит животные продукты."],
        "recommendations": [],
        "warnings": [],
        "compatibility": {"diet": "high", "restriction": "high", "goal": "high"},
        "profile_assessment": {
            "goal_alignment": {"status": "ok"},
            "allergy_issues": {"status": "ok"},
            "disease_issues": {"status": "ok"},
            "preference_alignment": {"status": "ok"},
            "additional_restrictions": {"status": "ok"},
        },
        "analysis_quality": {"score": 99},
    }

    row = evaluate_analysis(result, recipe, "nikita_vegan_gluten_free", profile, expectations)

    assert row["parser"]["score"] == 100
    assert row["amounts"]["failed_amounts"]
    assert row["matching"]["suspicious_matches"]
    assert row["profile_eval"]["missing_expected_conflicts"]
    assert row["text_grounding"]["false_claims"]
    assert row["text_grounding"]["profile_noise_phrases"]
    assert row["overall_score"] < 80


def test_evaluate_analysis_matches_simple_russian_ingredient_forms():
    row = evaluate_analysis(
        {
            "title": "Бисквитный рулет",
            "structured_recipe": {"ingredients": [{"name_canonical": "яйца куриные"}]},
            "detailed_ingredients": [],
            "rag_context": [],
            "profile_assessment": {},
            "compatibility": {},
        },
        {"index": 20, "title": "Бисквитный рулет", "required_ingredients": ["яйцо"], "flags": []},
        "sergey_muscle_gain",
        {"diet": "balanced"},
        {},
    )

    assert row["parser"]["missing_required_ingredients"] == []


def test_retrieval_extracts_source_hints_without_polluting_queries():
    service = RetrievalService()

    hints, queries = service._extract_source_hints(
        [f"{SOURCE_HINT_PREFIX}kb_low_sodium.txt", "низкая соль", f"{SOURCE_HINT_PREFIX}kb_hypertension.txt"]
    )

    assert hints == ["kb_low_sodium.txt", "kb_hypertension.txt"]
    assert queries == ["низкая соль"]


def test_retrieval_replaces_duplicate_sources_before_dropping_protected_sources():
    service = RetrievalService()
    items = [
        {"source": "kb_high_protein.txt", "score": 0.5},
        {"source": "kb_high_protein.txt", "score": 0.2},
        {"source": "kb_low_sodium.txt", "score": 0.3},
    ]

    index = service._lowest_priority_replacement_index(
        items,
        {"kb_high_protein.txt", "kb_low_sodium.txt", "kb_vegetarian.txt"},
    )

    assert index == 1
