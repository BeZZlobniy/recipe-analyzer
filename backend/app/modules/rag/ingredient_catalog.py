from __future__ import annotations

import re

from app.core.utils import normalize_text


# Small curated overrides for ambiguous or USDA-unfriendly ingredient names.
TRANSLATION_OVERRIDES = {
    "пармезан": "parmesan cheese",
    "сыр пармезан": "parmesan cheese",
    "салат романо": "romaine lettuce raw",
    "айсберг": "iceberg lettuce raw",
    "перец": "black pepper",
    "черный перец": "black pepper",
    "сахар": "granulated sugar",
    "гречневая крупа": "buckwheat groats",
    "панировочные сухари": "breadcrumbs",
    "лимонный сок": "lemon juice raw",
    "помидоры черри": "tomatoes raw",
}

# Basic fallbacks used only when LLM did not provide a usable english name.
DIRECT_FALLBACKS = {
    "куриное филе": "chicken breast",
    "помидоры": "tomatoes raw",
    "белый хлеб": "white bread",
    "оливковое масло": "olive oil",
    "сливочное масло": "butter",
    "молоко": "milk",
    "мука": "wheat flour",
    "мука пшеничная": "wheat flour",
    "пшеничная мука": "wheat flour",
    "яблоко": "apple raw",
    "яблоки": "apple raw",
    "соль": "salt",
    "яйцо": "egg raw",
    "чеснок": "garlic",
    "анчоусы": "anchovies",
    "горчица": "mustard",
    "лапша": "pasta",
    "шампиньоны": "mushrooms",
    "лук": "onion",
    "укроп": "dill",
    "петрушка": "parsley",
    "вода": "water",
    "базилик": "basil",
}

EXTRA_HINTS = {
    "лапша": ["spaghetti", "dry pasta"],
    "яйцо": ["whole egg"],
    "мука": ["all-purpose flour", "flour"],
    "мука пшеничная": ["all-purpose flour", "flour"],
    "пшеничная мука": ["all-purpose flour", "flour"],
    "помидоры": ["tomato raw", "tomato"],
    "помидоры черри": ["cherry tomatoes"],
    "яблоко": ["apples raw", "apple"],
    "яблоки": ["apples raw", "apple"],
    "гречневая крупа": ["buckwheat"],
    "шампиньоны": ["champignon mushrooms"],
    "лук": ["yellow onion"],
    "панировочные сухари": ["bread crumbs"],
}

EN_NORMALIZATIONS = {
    "romano lettuce": "romaine lettuce raw",
    "romaine lettuce": "romaine lettuce raw",
    "parmesan": "parmesan cheese",
    "pepper": "black pepper",
    "black pepper": "black pepper",
    "egg": "egg raw",
    "eggs": "egg raw",
    "tomato": "tomatoes raw",
    "tomatoes": "tomatoes raw",
    "cherry tomatoes": "tomatoes raw",
    "apple": "apple raw",
    "apples": "apple raw",
    "lemon juice": "lemon juice raw",
    "buckwheat": "buckwheat groats",
    "sugar": "granulated sugar",
}

EN_STOPWORDS = {
    "fresh",
    "raw",
    "chopped",
    "diced",
    "sliced",
    "grated",
    "ground",
    "for",
    "garnish",
    "optional",
}


def fallback_name_en(canonical_name: str) -> str | None:
    canonical = normalize_text(canonical_name)
    return TRANSLATION_OVERRIDES.get(canonical) or DIRECT_FALLBACKS.get(canonical)


def normalize_name_en(canonical_name: str, raw_name_en: str | None) -> str | None:
    canonical = normalize_text(canonical_name)
    if canonical in TRANSLATION_OVERRIDES:
        return TRANSLATION_OVERRIDES[canonical]

    sanitized = sanitize_name_en(raw_name_en)
    if not sanitized:
        return DIRECT_FALLBACKS.get(canonical)

    if "," in sanitized and canonical in DIRECT_FALLBACKS:
        return DIRECT_FALLBACKS[canonical]
    return EN_NORMALIZATIONS.get(sanitized, sanitized)


def build_query_variants(canonical_name: str, name_en: str | None = None) -> list[str]:
    canonical = normalize_text(canonical_name)
    base = normalize_name_en(canonical, name_en)
    variants = [base or "", *expand_english_queries(base), *EXTRA_HINTS.get(canonical, []), canonical]
    seen: set[str] = set()
    queries: list[str] = []
    for value in variants:
        key = normalize_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        queries.append(value)
    return queries


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
    if "cheese" in normalized and normalized != "parmesan cheese":
        variants.append("cheese")
    return [item for item in variants if item]


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
