from __future__ import annotations

import re
from typing import Any

from app.core.utils import dedupe_texts, load_data_json, normalize_spaces, normalize_text, parse_range
from app.modules.rag.ingredient_catalog import normalize_name_en
from app.modules.structuring.schemas import SimpleRecipeIngredient, SimpleRecipePayload, StructuredIngredient


_PARSER_DATA = load_data_json("fallback/parser_fallbacks.json")


class FallbackRecipeParser:
    QUANTITY_PATTERN = re.compile(
        r"(?P<value>\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?)\s*(?:[-–]\s*\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?\s*)?(?P<unit>кг|г|гр|мл|л|шт|стакан(?:а|ов)?|пучок(?:а|ов)?|веточк(?:а|и)?|ст\.?\s*л\.?|ст\.?\s*ложк(?:а|и)?|ч\.?\s*л\.?|ч\.?\s*ложк(?:а|и)?|щепотк(?:а|и)?|луковица|луковицы|зубчик|зубчика|зубка|кочан|ломтик(?:а|ов)?|филе)",
        flags=re.IGNORECASE,
    )
    STEP_START_PATTERN = re.compile(r"^\s*(?:\d+[.)]|шаг\s*\d+)", flags=re.IGNORECASE)
    SECTION_INGREDIENTS = set(_PARSER_DATA.get("section_ingredients", []))
    SECTION_STEPS = set(_PARSER_DATA.get("section_steps", []))
    UNIT_ALIASES = dict(_PARSER_DATA.get("unit_aliases", {}))
    NAME_REPLACEMENTS = dict(_PARSER_DATA.get("name_replacements", {}))
    GENERIC_QUALIFIER_BASES = set(_PARSER_DATA.get("generic_qualifier_bases", []))
    SEMANTIC_QUALIFIER_KEYWORDS = tuple(_PARSER_DATA.get("semantic_qualifier_keywords", []))
    NAME_DROP_TOKENS = tuple(_PARSER_DATA.get("name_drop_tokens", []))
    AMOUNTLESS_INGREDIENTS = set(_PARSER_DATA.get("amountless_ingredients", []))

    def build_recipe(self, clean_recipe_text: str) -> SimpleRecipePayload:
        lines = self.prepare_lines(clean_recipe_text)
        ingredients: list[SimpleRecipeIngredient] = []
        instructions: list[str] = []
        in_ingredients = False
        in_steps = False
        pending_step: str | None = None

        for line in lines:
            low = normalize_text(line)
            if self.is_ingredient_section(low):
                in_ingredients = True
                in_steps = False
                continue
            if self.is_step_section(low) or self.STEP_START_PATTERN.match(line):
                in_ingredients = False
                in_steps = True
                if self.STEP_START_PATTERN.match(line):
                    cleaned_step = self.clean_step(line)
                    if cleaned_step:
                        if pending_step:
                            instructions.append(pending_step)
                        pending_step = cleaned_step
                continue

            ingredient_candidate = self.parse_ingredient_line(line)
            if ingredient_candidate and (in_ingredients or not in_steps):
                ingredients.extend(ingredient_candidate)
                continue
            if in_ingredients:
                amountless = self.parse_amountless_ingredient_line(line)
                if amountless:
                    ingredients.append(amountless)
                    continue

            if in_steps:
                cleaned_step = self.clean_step(line)
                if not cleaned_step:
                    continue
                if pending_step and not self.STEP_START_PATTERN.match(line):
                    pending_step = f"{pending_step} {cleaned_step}".strip()
                else:
                    if pending_step:
                        instructions.append(pending_step)
                    pending_step = cleaned_step

        if pending_step:
            instructions.append(pending_step)

        return SimpleRecipePayload(
            title=self.guess_title(lines),
            ingredients=ingredients,
            instructions=dedupe_texts(instructions),
            tags=[],
        )

    def find_quantity_in_text(self, ingredient_name: str, clean_recipe_text: str) -> str | None:
        target = normalize_text(ingredient_name)
        for line in self.prepare_lines(clean_recipe_text):
            parsed = self.parse_ingredient_line(line)
            if not parsed:
                continue
            for item in parsed:
                if normalize_text(item.name) == target and item.quantity:
                    return item.quantity
        return None

    def resolve_title(self, recipe: SimpleRecipePayload, clean_recipe_text: str) -> str:
        title = normalize_spaces(recipe.title)
        if title and normalize_text(title) not in {"рецепт", "анализ рецепта", "потребуется"}:
            return title
        lines = [normalize_spaces(line) for line in clean_recipe_text.splitlines() if normalize_spaces(line)]
        return self.guess_title(lines)

    def extract_servings(self, text: str) -> str | None:
        normalized = normalize_text(text)
        match = re.search(r"(на\s+)?(\d+\s*[-–]\s*\d+|\d+)\s+порц", normalized)
        return match.group(2).replace(" ", "") if match else None

    def to_structured_ingredients(self, item: Any, source: str) -> list[StructuredIngredient]:
        source_name = normalize_spaces(getattr(item, "name_ru", None) or item.name)
        amount_value, amount_text, unit = self.parse_quantity(
            getattr(item, "quantity_text", None) or item.quantity,
            getattr(item, "quantity_value", None),
            getattr(item, "quantity_unit", None),
        )
        canonical = normalize_text(source_name)
        if amount_value is None and item.quantity is None:
            amount_value, amount_text, unit, canonical = self.extract_inline_quantity(source_name)
        variants = self.split_combined_ingredients(canonical)
        result: list[StructuredIngredient] = []
        for variant in variants:
            cleaned = self.sanitize_name(variant)
            if not cleaned:
                continue
            source_name_en = normalize_name_en(cleaned, getattr(item, "name_en", None))
            inferred_unit = unit
            if inferred_unit is None and any(
                token in cleaned for token in ("яйц", "луковиц", "зубчик", "кочан", "ломтик")
            ) and amount_value is not None:
                inferred_unit = "шт"
            result.append(
                StructuredIngredient(
                    name_raw=source_name,
                    name_canonical=cleaned,
                    name_en=source_name_en,
                    amount_value=amount_value,
                    amount_text=amount_text,
                    unit=inferred_unit,
                    llm_grams=getattr(item, "llm_grams", None),
                    gram_confidence=getattr(item, "gram_confidence", None),
                    form=None,
                    prep_state=None,
                    source=source,
                    confidence="medium" if getattr(item, "optional", False) else "high",
                )
            )
        return result

    def prepare_lines(self, text: str) -> list[str]:
        lines: list[str] = []
        for raw_line in text.splitlines():
            cleaned = normalize_spaces(raw_line)
            cleaned = re.sub(r"^#{1,6}\s*", "", cleaned).replace("**", "").replace("__", "")
            cleaned = cleaned.strip()
            if cleaned:
                lines.append(cleaned)
        return lines

    def parse_ingredient_line(self, line: str) -> list[SimpleRecipeIngredient] | None:
        low = normalize_text(line)
        if self.is_noise_line(low):
            return None

        normalized_line = normalize_spaces(line.replace("—", " - ").replace("–", " - "))
        if " - " in normalized_line:
            parts = re.split(r"\s+-\s+", normalized_line, maxsplit=1)
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()
                if self.looks_like_quantity(right):
                    return self.make_ingredient_entries(left, right)
                if self.looks_like_quantity(left):
                    return self.make_ingredient_entries(right, left)

        if self.looks_like_quantity_prefix(low):
            quantity, name = self.split_quantity_prefix(line)
            if name:
                return self.make_ingredient_entries(name, quantity)
        return None

    def make_ingredient_entries(self, name_text: str, quantity_text: str | None) -> list[SimpleRecipeIngredient]:
        name_text = normalize_spaces(name_text).lstrip("-*• ").strip(" ,.;:")
        quantity_text = normalize_spaces(quantity_text or "").strip(" ,.;:") or None
        low = normalize_text(name_text)
        if low in {"соль, перец", "соль и перец"}:
            return [
                SimpleRecipeIngredient(name="Соль", name_en="salt", quantity=quantity_text, optional=False),
                SimpleRecipeIngredient(name="Перец", name_en="black pepper", quantity=quantity_text, optional=False),
            ]
        return [SimpleRecipeIngredient(name=name_text, name_en=None, quantity=quantity_text, optional=False)]

    def parse_amountless_ingredient_line(self, line: str) -> SimpleRecipeIngredient | None:
        name = normalize_spaces(line).strip(" -*•,.;:")
        low = normalize_text(name)
        if not low or len(low.split()) > 3:
            return None
        cleaned = self.sanitize_name(low)
        if cleaned in self.AMOUNTLESS_INGREDIENTS or any(cleaned.startswith(item + " ") for item in self.AMOUNTLESS_INGREDIENTS):
            return SimpleRecipeIngredient(name=name, name_en=normalize_name_en(cleaned, None), quantity=None, optional=False)
        return None

    def looks_like_quantity(self, text: str) -> bool:
        low = normalize_text(text)
        return bool(
            self.QUANTITY_PATTERN.search(low)
            or low in {"по вкусу", "по желанию", "для подачи", "для жарки", "щепотка"}
            or re.match(r"^\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?\s*[-–]\s*\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)?\s*(шт|г|гр|ст\.?\s*л\.?|ст\.?\s*ложк(?:а|и)?|ч\.?\s*л\.?|ч\.?\s*ложк(?:а|и)?|ломтик(?:а|ов)?)?$", low)
        )

    def looks_like_quantity_prefix(self, text: str) -> bool:
        return bool(self.QUANTITY_PATTERN.match(text))

    def split_quantity_prefix(self, line: str) -> tuple[str | None, str | None]:
        low = normalize_text(line)
        match = self.QUANTITY_PATTERN.match(low)
        if not match:
            return None, None
        quantity = match.group(0).strip()
        name = low[match.end() :].strip(" ,.;:-")
        return quantity or None, name or None

    def parse_quantity(
        self,
        quantity: str | None,
        quantity_value_hint: float | None = None,
        quantity_unit_hint: str | None = None,
    ) -> tuple[float | None, str | None, str | None]:
        if not quantity:
            if quantity_value_hint is not None or quantity_unit_hint is not None:
                return quantity_value_hint, None, quantity_unit_hint
            return None, None, None
        text = normalize_spaces(quantity)
        low = normalize_text(text)
        if low in {"по вкусу", "по желанию", "для подачи", "для жарки", "щепотка"}:
            return None, text, None
        match = self.QUANTITY_PATTERN.search(low)
        if not match:
            return quantity_value_hint, text, quantity_unit_hint
        value = quantity_value_hint
        if value is None:
            parsed_range = parse_range(low)
            value = round(sum(parsed_range) / 2, 3) if parsed_range else self.parse_number(match.group("value"))
        unit_raw = (quantity_unit_hint or match.group("unit") or "").strip()
        unit = self.UNIT_ALIASES.get(unit_raw, unit_raw or None)
        return value, text, unit

    def extract_inline_quantity(self, ingredient_line: str) -> tuple[float | None, str | None, str | None, str]:
        text = normalize_spaces(ingredient_line).strip("-*• ")
        low = normalize_text(text)
        match = self.QUANTITY_PATTERN.match(low)
        if not match:
            return None, None, None, low
        parsed_range = parse_range(low)
        value = round(sum(parsed_range) / 2, 3) if parsed_range else self.parse_number(match.group("value"))
        unit_raw = (match.group("unit") or "").strip()
        unit = self.UNIT_ALIASES.get(unit_raw, unit_raw or None)
        remainder = low[match.end() :].strip(" ,.;:-")
        return value, match.group(0).strip(), unit, remainder or low

    @staticmethod
    def parse_number(value: str) -> float:
        normalized = value.replace(",", ".")
        if "/" not in normalized:
            return float(normalized)
        numerator, denominator = normalized.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return 0.0
        return float(numerator) / denominator_value

    def split_combined_ingredients(self, canonical: str) -> list[str]:
        low = normalize_text(canonical)
        if "соль и перец" in low or "соль, перец" in low:
            return ["соль", "перец"]
        return [low]

    def sanitize_name(self, value: str) -> str:
        low = normalize_text(value)
        qualifiers = self._extract_parenthetical_qualifiers(low)
        low = re.sub(r"\([^)]*\)", " ", low)
        low = re.sub(r"\b\d+(?:[.,]\d+)?\s*%", " ", low)
        for phrase in (
            "обычно используется",
            "для украшения",
            "по желанию",
            "по вкусу",
            "для подачи",
            "для жарки",
            "ключевая часть",
        ):
            low = low.replace(phrase, " ")
        for token in self.NAME_DROP_TOKENS:
            low = re.sub(rf"\b{token}\b", " ", low)
        low = self._apply_parenthetical_qualifiers(low, qualifiers)
        low = re.sub(r"\s+", " ", low).strip(" ,.;:-()")
        return self.NAME_REPLACEMENTS.get(low, low)

    def _extract_parenthetical_qualifiers(self, value: str) -> list[str]:
        qualifiers: list[str] = []
        for match in re.findall(r"\(([^)]*)\)", value):
            cleaned = self._sanitize_fragment(match)
            if cleaned:
                qualifiers.append(cleaned)
        return qualifiers

    def _sanitize_fragment(self, value: str) -> str:
        fragment = normalize_text(value)
        for phrase in ("по вкусу", "по желанию", "для подачи", "для жарки", "для работы с тестом"):
            fragment = fragment.replace(phrase, " ")
        fragment = re.sub(r"[^a-zа-яё\s-]", " ", fragment)
        fragment = re.sub(r"\s+", " ", fragment).strip(" ,.;:-")
        return fragment

    def _apply_parenthetical_qualifiers(self, base: str, qualifiers: list[str]) -> str:
        cleaned_base = re.sub(r"\s+", " ", base).strip(" ,.;:-")
        if not qualifiers:
            return cleaned_base

        semantic_qualifiers = [item for item in qualifiers if self._is_semantic_qualifier(item)]
        if cleaned_base in self.GENERIC_QUALIFIER_BASES and semantic_qualifiers:
            return f"{cleaned_base} {' '.join(semantic_qualifiers)}".strip()
        if semantic_qualifiers:
            return f"{cleaned_base} {' '.join(semantic_qualifiers)}".strip()
        return cleaned_base

    def _is_semantic_qualifier(self, value: str) -> bool:
        return any(keyword in value for keyword in self.SEMANTIC_QUALIFIER_KEYWORDS)

    def is_noise_line(self, low: str) -> bool:
        if self.is_ingredient_section(low) or self.is_step_section(low):
            return True
        if any(token in low for token in ("приятного аппетита", "подавать лучше всего", "фото приготовления рецепта")):
            return True
        return len(low) > 160

    def is_ingredient_section(self, low: str) -> bool:
        return low in self.SECTION_INGREDIENTS or "ингредиент" in low or low.startswith("продукты") or "потребуется" in low or low.startswith("для ")

    def is_step_section(self, low: str) -> bool:
        return low in self.SECTION_STEPS or "приготов" in low or "инструкц" in low or "способ приготовления" in low

    def clean_step(self, line: str) -> str:
        step = normalize_spaces(line)
        step = re.sub(r"^\d+[.)]\s*", "", step)
        return step.strip()

    def guess_title(self, lines: list[str]) -> str:
        for line in lines[:8]:
            low = normalize_text(line)
            if low in self.SECTION_INGREDIENTS or low in self.SECTION_STEPS or low.startswith("продукты"):
                continue
            if re.fullmatch(r"\d+", low):
                continue
            if len(line) <= 100 and not self.looks_like_quantity(low):
                return line.strip(" :-")
        return "Рецепт"


fallback_recipe_parser = FallbackRecipeParser()
