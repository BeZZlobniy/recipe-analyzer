from __future__ import annotations

import math
import re
from typing import Any

from app.core.utils import format_portions, normalize_text
from app.modules.structuring.schemas import StructuredRecipe


class PortionService:
    STEP_PATTERNS = [
        re.compile(r"разделить на\s+(\d+)\s+(?:част|шарик|кусоч|пирож|порц|беляш)", flags=re.IGNORECASE),
        re.compile(r"получ(?:ит|а)ся\s+(\d+)\s+(?:шт|порц|беляш|котлет|олад)", flags=re.IGNORECASE),
        re.compile(r"из\s+(\d+)\s+(?:част|шарик|кусоч)", flags=re.IGNORECASE),
        re.compile(r"на\s+(\d+)\s+равн(?:ых|ые)\s+част", flags=re.IGNORECASE),
    ]

    def estimate_recipe_servings(self, recipe: StructuredRecipe, recipe_text: str | None = None) -> int:
        declared = (recipe.servings_declared or "").strip()
        if declared:
            parsed = self._parse_servings_value(declared)
            if parsed:
                return parsed

        for step in recipe.steps:
            parsed = self._extract_servings_from_text(step)
            if parsed:
                return parsed

        if recipe_text:
            parsed = self._extract_servings_from_text(recipe_text)
            if parsed:
                return parsed

        return 1

    def recommend_recipe_servings(
        self,
        *,
        estimated_recipe_servings: int,
        nutrition_total: dict[str, Any],
        target_recipe_calories: float | None,
    ) -> int:
        target = self._coerce_positive_number(target_recipe_calories)
        total_calories = float(nutrition_total.get("calories", {}).get("value", 0) or 0)
        if target and total_calories > 0:
            return max(1, int(math.ceil(total_calories / target)))
        return max(estimated_recipe_servings, 1)

    def build_guidance(
        self,
        *,
        estimated_recipe_servings: int,
        recommended_recipe_servings: int,
        nutrition_total: dict[str, Any],
        target_recipe_calories: float | None,
    ) -> dict[str, Any]:
        total_calories = float(nutrition_total.get("calories", {}).get("value", 0) or 0)
        target = self._coerce_positive_number(target_recipe_calories)
        calories_per_recommended = round(total_calories / max(recommended_recipe_servings, 1), 2) if total_calories else 0.0

        summary: str | None = None
        if target:
            summary = (
                f"Чтобы уложиться примерно в {target:.0f} ккал, рецепт стоит разделить на "
                f"{format_portions(recommended_recipe_servings)}."
            )
        elif recommended_recipe_servings > 1:
            summary = (
                f"По структуре рецепта его разумно делить примерно на {format_portions(recommended_recipe_servings)}."
            )

        return {
            "estimated_recipe_servings": estimated_recipe_servings,
            "recommended_recipe_servings": recommended_recipe_servings,
            "target_recipe_calories": target,
            "calories_total": round(total_calories, 2),
            "calories_per_recommended_serving": calories_per_recommended,
            "summary": summary,
        }

    def _parse_servings_value(self, value: str) -> int | None:
        normalized = normalize_text(value)
        range_match = re.search(r"(\d+)\s*-\s*(\d+)", normalized)
        if range_match:
            left = int(range_match.group(1))
            right = int(range_match.group(2))
            return max(1, int(round((left + right) / 2)))
        if normalized.isdigit():
            return max(1, int(normalized))
        return None

    def _extract_servings_from_text(self, text: str) -> int | None:
        normalized = normalize_text(text)
        for pattern in self.STEP_PATTERNS:
            match = pattern.search(normalized)
            if match:
                return max(1, int(match.group(1)))
        return None

    def _coerce_positive_number(self, value: Any) -> float | None:
        if value in {None, ""}:
            return None
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return round(numeric, 2) if numeric > 0 else None


portion_service = PortionService()
