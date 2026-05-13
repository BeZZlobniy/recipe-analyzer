from __future__ import annotations

from app.modules.rag.usda_resolution_utils import is_safe_candidate


def test_safe_candidate_accepts_common_usda_plural_display_name():
    assert is_safe_candidate(
        {"name_en": "onion raw", "name_canonical": "лук репчатый красный"},
        {"display_name_en": "Onions, raw"},
    )


def test_safe_candidate_rejects_pickle_for_dill_herb():
    assert not is_safe_candidate(
        {"name_en": "dill fresh", "name_canonical": "укроп"},
        {"display_name_en": "Pickles, dill"},
    )
