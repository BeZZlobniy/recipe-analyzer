from __future__ import annotations

import re
from typing import Any

from app.core.utils import dedupe_texts, normalize_text
from app.modules.structuring.fallback_parser import fallback_recipe_parser
from app.modules.structuring.input_cleaner import input_cleaner
from app.modules.structuring.schemas import SimpleRecipeIngredient, SimpleRecipePayload, StructuredRecipe
from app.services.ollama_service import ollama_service


class RecipeNormalizationService:
    def __init__(self) -> None:
        self._llm_recipe_cache: dict[str, SimpleRecipePayload] = {}

    def normalize(self, recipe_text: str) -> tuple[StructuredRecipe, str]:
        clean_recipe_text = input_cleaner.clean(recipe_text)
        raw_title = fallback_recipe_parser.guess_title(fallback_recipe_parser.prepare_lines(recipe_text))
        heuristic_recipe = fallback_recipe_parser.build_recipe(clean_recipe_text)
        llm_recipe = self._get_llm_recipe(clean_recipe_text)
        llm_recipe_acceptable = self._is_acceptable_llm_recipe(llm_recipe, heuristic_recipe, clean_recipe_text)
        if llm_recipe and llm_recipe_acceptable:
            self._llm_recipe_cache[clean_recipe_text] = llm_recipe

        effective_recipe = llm_recipe if llm_recipe_acceptable else heuristic_recipe
        ingredient_source = "llm_normalized" if effective_recipe is llm_recipe else "heuristic_fallback"

        if llm_recipe:
            effective_recipe = self._merge_llm_metadata(effective_recipe, llm_recipe, use_llm_title=llm_recipe_acceptable)
        effective_recipe = self._backfill_missing_quantities(effective_recipe, heuristic_recipe, clean_recipe_text)

        structured_ingredients = [
            structured
            for item in effective_recipe.ingredients
            for structured in fallback_recipe_parser.to_structured_ingredients(item, ingredient_source)
        ]
        resolved_title = fallback_recipe_parser.resolve_title(effective_recipe, clean_recipe_text)
        recipe = StructuredRecipe(
            title=self._choose_title(resolved_title, raw_title),
            servings_declared=fallback_recipe_parser.extract_servings(clean_recipe_text),
            ingredients=structured_ingredients,
            steps=dedupe_texts(effective_recipe.instructions or heuristic_recipe.instructions),
            notes=dedupe_texts(effective_recipe.tags),
            source_recipe_text=clean_recipe_text,
        )
        return recipe, clean_recipe_text

    def _get_llm_recipe(self, clean_recipe_text: str) -> SimpleRecipePayload | None:
        cached = self._llm_recipe_cache.get(clean_recipe_text)
        if cached is not None:
            return cached
        return self._parse_llm_recipe(ollama_service.structure_recipe_json(clean_recipe_text))

    def _choose_title(self, resolved_title: str, raw_title: str) -> str:
        title = resolved_title.strip()
        raw = raw_title.strip()
        title_low = normalize_text(title)
        raw_low = normalize_text(raw)
        if raw and raw_low not in {"рецепт", "продукты", "ингредиенты", "*"} and title_low != raw_low:
            return raw
        ingredient_title_tokens = {
            "чеснок",
            "соль",
            "перец",
            "петрушка",
            "кинза",
            "базилик",
            "укроп",
            "зелень",
            "лавровый лист",
        }
        if raw and title_low in ingredient_title_tokens:
            return raw
        if title_low in {"рецепт", "продукты", "ингредиенты", "*"}:
            return raw or title
        if title_low.startswith("(") or "для формы" in title_low:
            return raw or title
        if fallback_recipe_parser.parse_ingredient_line(title):
            return raw or title
        return title or raw

    def _backfill_missing_quantities(
        self,
        recipe: SimpleRecipePayload,
        heuristic_recipe: SimpleRecipePayload,
        clean_recipe_text: str,
    ) -> SimpleRecipePayload:
        heuristic_by_name: dict[str, list[SimpleRecipeIngredient]] = {}
        for item in heuristic_recipe.ingredients:
            heuristic_by_name.setdefault(normalize_text(item.name), []).append(item)

        merged_items: list[SimpleRecipeIngredient] = []
        for item in recipe.ingredients:
            quantity = item.quantity_text or item.quantity
            quantity_value = item.quantity_value
            quantity_unit = item.quantity_unit
            if not quantity:
                candidates = heuristic_by_name.get(normalize_text(item.name), [])
                while candidates and not candidates[0].quantity:
                    candidates.pop(0)
                if candidates:
                    fallback_item = candidates.pop(0)
                    quantity = fallback_item.quantity_text or fallback_item.quantity
                    quantity_value = quantity_value if quantity_value is not None else fallback_item.quantity_value
                    quantity_unit = quantity_unit or fallback_item.quantity_unit
                else:
                    quantity = fallback_recipe_parser.find_quantity_in_text(item.name, clean_recipe_text)
            merged_items.append(
                item.model_copy(
                    update={
                        "quantity": quantity,
                        "quantity_text": quantity,
                        "quantity_value": quantity_value,
                        "quantity_unit": quantity_unit,
                    }
                )
            )
        return SimpleRecipePayload(title=recipe.title, ingredients=merged_items, instructions=recipe.instructions, tags=recipe.tags)

    def _merge_llm_metadata(
        self,
        recipe: SimpleRecipePayload,
        llm_recipe: SimpleRecipePayload | None,
        use_llm_title: bool = False,
    ) -> SimpleRecipePayload:
        if llm_recipe is None:
            return recipe

        llm_by_name: dict[str, list[SimpleRecipeIngredient]] = {}
        for item in llm_recipe.ingredients:
            llm_by_name.setdefault(normalize_text(item.name), []).append(item)

        merged_items: list[SimpleRecipeIngredient] = []
        for item in recipe.ingredients:
            candidates = llm_by_name.get(normalize_text(item.name), [])
            llm_item = candidates.pop(0) if candidates else self._find_similar_llm_item(item, llm_recipe.ingredients)
            merged_items.append(
                item.model_copy(
                    update={
                        "name_en": (llm_item.name_en if llm_item and llm_item.name_en else item.name_en),
                        "optional": (llm_item.optional if llm_item else item.optional),
                        "llm_grams": (llm_item.llm_grams if llm_item and llm_item.llm_grams is not None else item.llm_grams),
                        "gram_confidence": (llm_item.gram_confidence if llm_item and llm_item.gram_confidence else item.gram_confidence),
                        "quantity_value": (llm_item.quantity_value if llm_item and llm_item.quantity_value is not None else item.quantity_value),
                        "quantity_unit": (llm_item.quantity_unit if llm_item and llm_item.quantity_unit else item.quantity_unit),
                        "quantity_text": (llm_item.quantity_text if llm_item and llm_item.quantity_text else item.quantity_text),
                    }
                )
            )
        return SimpleRecipePayload(
            title=(llm_recipe.title or recipe.title) if use_llm_title else recipe.title,
            ingredients=merged_items,
            instructions=recipe.instructions or llm_recipe.instructions,
            tags=recipe.tags or llm_recipe.tags,
        )

    def _find_similar_llm_item(
        self,
        item: SimpleRecipeIngredient,
        llm_items: list[SimpleRecipeIngredient],
    ) -> SimpleRecipeIngredient | None:
        item_tokens = {token for token in normalize_text(item.name).split() if len(token) >= 4}
        if not item_tokens:
            return None
        best_match: SimpleRecipeIngredient | None = None
        best_score = 0
        for candidate in llm_items:
            candidate_tokens = {token for token in normalize_text(candidate.name).split() if len(token) >= 4}
            score = len(item_tokens & candidate_tokens)
            if score > best_score:
                best_score = score
                best_match = candidate
        return best_match if best_score > 0 else None

    def _parse_llm_recipe(self, payload: dict[str, Any] | None) -> SimpleRecipePayload | None:
        if not isinstance(payload, dict) or not isinstance(payload.get("recipe"), dict):
            return None
        payload = self._coerce_llm_recipe_payload(payload["recipe"])
        try:
            return SimpleRecipePayload.model_validate(payload)
        except Exception:
            return None

    def _coerce_llm_recipe_payload(self, recipe: dict[str, Any]) -> dict[str, Any]:
        coerced: dict[str, Any] = {"title": "", "ingredients": [], "instructions": [], "tags": []}
        for key, value in recipe.items():
            normalized_key = self._normalize_llm_key(key)
            if normalized_key in {"title", "instructions", "tags"}:
                coerced[normalized_key] = value
            elif normalized_key == "ingredients" and isinstance(value, list):
                coerced["ingredients"] = [item for item in (self._coerce_llm_ingredient(entry) for entry in value) if item]
        return coerced

    def _coerce_llm_ingredient(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        coerced: dict[str, Any] = {"optional": False}
        for key, value in item.items():
            normalized_key = self._normalize_llm_key(key)
            if normalized_key in {
                "name",
                "name_ru",
                "name_en",
                "quantity",
                "quantity_text",
                "quantity_value",
                "quantity_unit",
                "optional",
                "llm_grams",
                "gram_confidence",
            }:
                coerced[normalized_key] = value
        if not coerced.get("name") and coerced.get("name_ru"):
            coerced["name"] = coerced["name_ru"]
        if not coerced.get("name_ru") and coerced.get("name"):
            coerced["name_ru"] = coerced["name"]
        return coerced if coerced.get("name") or coerced.get("name_ru") else None

    def _normalize_llm_key(self, key: Any) -> str:
        text = normalize_text(str(key))
        compact = re.sub(r"[^a-zа-яё]+", "_", text).strip("_")
        if compact in {
            "title",
            "name",
            "name_ru",
            "name_en",
            "quantity",
            "quantity_text",
            "quantity_value",
            "quantity_unit",
            "optional",
            "llm_grams",
            "gram_confidence",
            "ingredients",
            "instructions",
            "tags",
        }:
            return compact
        compact_no_sep = compact.replace("_", "")
        if "ingredient" in compact or "ингредиент" in compact:
            return "ingredients"
        if "instruction" in compact or "шаг" in compact or "инструкц" in compact:
            return "instructions"
        if "tag" in compact or "тег" in compact:
            return "tags"
        if "title" in compact or "назван" in compact or "блюд" in compact:
            return "title"
        if "gram_confidence" in compact or ("gram" in compact and "confidence" in compact) or "конфиден" in compact:
            return "gram_confidence"
        if "llm" in compact and "gram" in compact:
            return "llm_grams"
        if compact_no_sep in {"nameen", "nameenglish"} or ("name" in compact and "en" in compact):
            return "name_en"
        if compact_no_sep in {"nameru", "namerus"} or ("name" in compact and "ru" in compact):
            return "name_ru"
        if "quantity" in compact or "количеств" in compact:
            if "text" in compact or "текст" in compact:
                return "quantity_text"
            if "value" in compact or "знач" in compact:
                return "quantity_value"
            if "unit" in compact or "единиц" in compact:
                return "quantity_unit"
            return "quantity"
        if "optional" in compact or "опцион" in compact:
            return "optional"
        if compact.startswith("name") or "название" in compact:
            return "name"
        return compact

    def _is_acceptable_llm_recipe(
        self,
        llm_recipe: SimpleRecipePayload | None,
        heuristic_recipe: SimpleRecipePayload,
        clean_recipe_text: str,
    ) -> bool:
        if llm_recipe is None:
            return False
        llm_count = len(llm_recipe.ingredients)
        heuristic_count = len(heuristic_recipe.ingredients)
        title = normalize_text(llm_recipe.title)
        if llm_count == 0:
            return False
        if heuristic_count >= 4 and llm_count < max(3, int(heuristic_count * 0.6)):
            return False
        if title in {"рецепт", "ингредиенты", "приготовление", "для салата", "для соуса"}:
            title = ""
        unknown_en = sum(1 for item in llm_recipe.ingredients if normalize_text(item.name_en or "").startswith("unknown-"))
        broken_names = sum(
            1
            for item in llm_recipe.ingredients
            if len(normalize_text(item.name)) <= 2 or self._has_mixed_script_token(normalize_text(item.name))
        )
        if llm_count and (unknown_en / llm_count > 0.2 or broken_names > 0):
            return False
        recipe_tokens = {token for token in normalize_text(clean_recipe_text).split() if len(token) >= 3}
        supported_ingredients = 0
        for item in llm_recipe.ingredients:
            name_tokens = {token for token in normalize_text(item.name).split() if len(token) >= 4}
            if name_tokens and name_tokens & recipe_tokens:
                supported_ingredients += 1
        if llm_count >= 4 and supported_ingredients < max(2, int(llm_count * 0.5)):
            return False
        return True

    def _has_mixed_script_token(self, value: str) -> bool:
        for token in value.split():
            has_cyrillic = bool(re.search(r"[а-яё]", token))
            has_latin = bool(re.search(r"[a-z]", token))
            if has_cyrillic and has_latin:
                return True
        return False


recipe_normalization_service = RecipeNormalizationService()
