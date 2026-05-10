from __future__ import annotations

from app.modules.rag.ingredient_catalog import build_query_variants, normalize_name_en


def test_qwen_translation_is_used_before_catalog_fallback():
    assert normalize_name_en("сметана", "sour cream") == "sour cream"
    assert build_query_variants("сметана", "sour cream")[0] == "sour cream"


def test_transliterated_qwen_translation_falls_back_to_catalog():
    assert normalize_name_en("сметана", "smetana") == "sour cream"
    assert build_query_variants("сметана", "smetana")[0] == "sour cream"


def test_model_translation_preserves_ground_meat_for_usda_search():
    assert normalize_name_en("фарш мясной", "ground beef") == "ground beef"
    assert build_query_variants("фарш мясной", "ground beef")[0] == "ground beef"


def test_conflicting_qwen_translation_falls_back_to_canonical_catalog_entry():
    assert normalize_name_en("крупа манная", "buckwheat groats") == "semolina flour"
    assert build_query_variants("крупа манная", "buckwheat groats")[0] == "semolina flour"


def test_catalog_heuristic_patterns_are_loaded_from_json():
    assert normalize_name_en("мясо говядина свинина", None) == "ground beef and pork"
    assert build_query_variants("мясо говядина свинина", None)[:3] == [
        "ground beef and pork",
        "ground beef",
        "ground pork",
    ]


def test_common_qwen_descriptors_are_normalized_for_usda_search():
    assert normalize_name_en("масло сливочное растопленное", "melted butter") == "butter"
    assert normalize_name_en("лук репчатый красный", "red onion") == "onion raw"
    assert normalize_name_en("листы лазаньи", "lasagna sheets") == "pasta dry"
