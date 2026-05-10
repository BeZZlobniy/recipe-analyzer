from __future__ import annotations

import re

from app.core.utils import load_data_json, normalize_text


_CATALOG_DATA = load_data_json("fallback/ingredient_catalog.json")

TRANSLATION_OVERRIDES = dict(_CATALOG_DATA.get("translation_overrides", {}))
DIRECT_FALLBACKS = dict(_CATALOG_DATA.get("direct_fallbacks", {}))
CATALOG_FALLBACKS = {**DIRECT_FALLBACKS, **TRANSLATION_OVERRIDES}
EXTRA_HINTS = {key: list(value) for key, value in _CATALOG_DATA.get("extra_hints", {}).items()}
EN_NORMALIZATIONS = dict(_CATALOG_DATA.get("en_normalizations", {}))
EN_STOPWORDS = set(_CATALOG_DATA.get("en_stopwords", []))
TRANSLITERATED_RU_TOKENS = set(_CATALOG_DATA.get("transliterated_ru_tokens", []))
INVALID_MODEL_NAME_TOKENS = set(_CATALOG_DATA.get("invalid_model_name_tokens", []))
MODEL_TRANSLATION_BLOCKLIST_BY_CANONICAL = {
    key: set(value)
    for key, value in _CATALOG_DATA.get("model_translation_blocklist_by_canonical", {}).items()
}
HEURISTIC_PATTERNS = list(_CATALOG_DATA.get("heuristic_patterns", []))
SPECIFIC_CHEESE_TOKENS = {"cheddar", "parmesan", "mozzarella", "hard", "goat", "processed"}


def normalize_name_en(canonical_name: str, raw_name_en: str | None) -> str | None:
    canonical = normalize_text(canonical_name)
    model_translation = normalize_model_name_en(raw_name_en)
    if model_translation and not is_conflicting_model_translation(canonical, model_translation):
        return model_translation
    return catalog_fallback_name_en(canonical)


def build_query_variants(canonical_name: str, name_en: str | None = None) -> list[str]:
    canonical = normalize_text(canonical_name)
    model_translation = normalize_model_name_en(name_en)
    fallback = catalog_fallback_name_en(canonical)
    if model_translation and is_conflicting_model_translation(canonical, model_translation):
        model_translation = None
    if model_translation:
        variants = [
            model_translation,
            *expand_english_queries(model_translation),
            fallback or "",
            *EXTRA_HINTS.get(canonical, [])[:1],
            canonical,
        ]
    else:
        variants = [
            fallback or "",
            *expand_english_queries(fallback),
            *EXTRA_HINTS.get(canonical, []),
            *heuristic_query_hints(canonical),
            canonical,
        ]
    seen: set[str] = set()
    queries: list[str] = []
    for value in variants:
        key = normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        queries.append(value)
    return queries


def normalize_model_name_en(raw_name_en: str | None) -> str | None:
    sanitized = sanitize_name_en(raw_name_en)
    if not is_valid_model_translation(sanitized):
        return None
    return EN_NORMALIZATIONS.get(sanitized, sanitized)


def catalog_fallback_name_en(canonical: str) -> str | None:
    fallback = _heuristic_match(canonical, "fallback")
    return CATALOG_FALLBACKS.get(canonical) or (fallback if isinstance(fallback, str) else None)


def is_valid_model_translation(value: str | None) -> bool:
    if not value:
        return False
    tokens = set(value.replace(",", " ").split())
    if not tokens:
        return False
    compact = value.replace(" ", "").replace(",", "")
    if compact in INVALID_MODEL_NAME_TOKENS:
        return False
    if tokens & INVALID_MODEL_NAME_TOKENS:
        return False
    if tokens & TRANSLITERATED_RU_TOKENS:
        return False
    return True


def is_conflicting_model_translation(canonical: str, model_translation: str) -> bool:
    blocked = MODEL_TRANSLATION_BLOCKLIST_BY_CANONICAL.get(canonical)
    if not blocked:
        return False
    normalized = normalize_text(model_translation)
    tokens = set(normalized.split())
    return normalized in blocked or bool(tokens & blocked)


def sanitize_name_en(value: str | None) -> str | None:
    if not value:
        return None
    text = normalize_text(value)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z,\s-]", " ", text)
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip(" ,")
    if not text:
        return None
    parts = [token for token in text.split() if token not in EN_STOPWORDS]
    if not parts:
        return None
    compact = " ".join(parts)
    return EN_NORMALIZATIONS.get(compact, compact)


def expand_english_queries(base: str | None) -> list[str]:
    if not base:
        return []
    normalized = sanitize_name_en(base)
    if not normalized:
        return []
    variants = [normalized]
    words = normalized.split()
    if words and words[-1] == "raw":
        variants.append(" ".join(words[:-1]))
    singular = _to_singular(normalized)
    if singular != normalized:
        variants.append(singular)
    if (
        "cheese" in normalized
        and normalized != "parmesan cheese"
        and not (SPECIFIC_CHEESE_TOKENS & set(words))
    ):
        variants.append("cheese")
    return [item for item in variants if item]


def heuristic_query_hints(canonical_name: str) -> list[str]:
    hints = _heuristic_match(canonical_name, "hints")
    return list(hints) if isinstance(hints, list) else []


def _heuristic_match(canonical_name: str, field: str) -> str | list[str] | None:
    canonical = normalize_text(canonical_name)
    if not canonical:
        return None
    for pattern in HEURISTIC_PATTERNS:
        if _matches_pattern(canonical, pattern):
            return pattern.get(field)
    return None


def _matches_pattern(canonical: str, pattern: dict) -> bool:
    equals = pattern.get("equals") or []
    if equals and canonical in equals:
        return True
    starts_with = pattern.get("starts_with") or []
    if starts_with and any(canonical.startswith(item) for item in starts_with):
        return True
    contains_all = pattern.get("contains_all") or []
    if contains_all and all(item in canonical for item in contains_all):
        return True
    contains = pattern.get("contains") or []
    return bool(contains and any(item in canonical for item in contains))


def _to_singular(text: str) -> str:
    replacements = {
        "tomatoes": "tomato",
        "apples": "apple",
        "eggs": "egg",
        "mushrooms": "mushroom",
        "anchovies": "anchovy",
    }
    words = text.split()
    singular_words = [replacements.get(word, word[:-1] if word.endswith("s") and len(word) > 3 else word) for word in words]
    return " ".join(singular_words)
