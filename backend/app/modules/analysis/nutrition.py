from __future__ import annotations

from typing import Any

from app.core.utils import normalize_text
from app.modules.analysis.nutrition_rules import (
    DEFAULT_TARGETS,
    estimate_grams,
    is_minor_ingredient,
    resolve_nutrients,
)
from app.modules.analysis.personalization import personalization_service
from app.modules.structuring.schemas import StructuredIngredient


class NutritionService:
    DEFAULT_TARGETS = DEFAULT_TARGETS

    def calculate(
        self,
        ingredients: list[StructuredIngredient],
        matches: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        totals_raw = {key: 0.0 for key in self.DEFAULT_TARGETS}
        detailed: list[dict[str, Any]] = []
        warnings: list[str] = []
        unresolved_ingredients: list[str] = []
        servings = max(int(profile.get("servings") or 1), 1)
        matched_by_name = {item["ingredient"]["name_canonical"]: item for item in matches}

        explicit_amount_count = 0
        matched_count = 0
        trusted_nutrition_count = 0
        fallback_grams_count = 0
        meaningful_fallback_count = 0

        for ingredient in ingredients:
            match = matched_by_name.get(ingredient.name_canonical, {})
            product = match.get("matched_product")
            if ingredient.amount_value is not None:
                explicit_amount_count += 1
            if match.get("match_status") == "matched":
                matched_count += 1

            estimated_grams, grams_reason, used_fallback_grams = estimate_grams(ingredient, product)
            nutrients, nutrition_source, nutrition_confidence = resolve_nutrients(ingredient, product)

            if used_fallback_grams:
                fallback_grams_count += 1
                if not is_minor_ingredient(ingredient):
                    meaningful_fallback_count += 1
            if nutrients and nutrition_source not in {"estimate", "unknown"}:
                trusted_nutrition_count += 1

            if nutrients is None:
                unresolved_ingredients.append(ingredient.name_canonical)
                warnings.append(f"Нет данных о нутриентах для ингредиента '{ingredient.name_canonical}'.")
                nutrient_values = {key: None for key in self.DEFAULT_TARGETS}
                nutrition_status = "unresolved"
            else:
                nutrient_values = self._scale_nutrients(nutrients, estimated_grams)
                nutrition_status = "resolved" if nutrition_source not in {"estimate", "unknown"} else "estimated"
                for key, value in nutrient_values.items():
                    if value is not None:
                        totals_raw[key] += float(value)

            detailed.append(
                {
                    "ingredient": ingredient.model_dump(),
                    "matched_name": match.get("matched_name"),
                    "matched_source": match.get("matched_source"),
                    "match_method": match.get("match_method"),
                    "match_confidence": match.get("match_confidence"),
                    "nutrition_source": nutrition_source,
                    "nutrition_confidence": nutrition_confidence,
                    "nutrition_resolution_status": nutrition_status,
                    "matched_product": product,
                    "estimated_grams": round(estimated_grams, 2),
                    "grams_reason": grams_reason,
                    "used_fallback_grams": used_fallback_grams,
                    "selection_reason": match.get("selection_reason"),
                    "top_candidates": match.get("top_candidates", []),
                    "nutrients": nutrient_values,
                }
            )

        targets = self._targets_from_profile(profile)
        nutrition_total = self._format_values(totals_raw, targets)
        nutrition_per_serving = self.recalculate_per_serving(nutrition_total, servings)

        resolution_stats = {
            "ingredient_count": len(ingredients),
            "explicit_amount_count": explicit_amount_count,
            "matched_count": matched_count,
            "trusted_nutrition_count": trusted_nutrition_count,
            "fallback_grams_count": fallback_grams_count,
            "meaningful_fallback_count": meaningful_fallback_count,
            "unresolved_count": len(unresolved_ingredients),
        }
        analysis_quality = self._build_quality(resolution_stats)
        warnings.extend(self._quality_warnings(analysis_quality, resolution_stats))

        return {
            "nutrition_total": nutrition_total,
            "nutrition_per_serving": nutrition_per_serving,
            "detailed_ingredients": detailed,
            "warnings": list(dict.fromkeys(warnings)),
            "analysis_quality": analysis_quality,
            "resolution_stats": resolution_stats,
            "unresolved_ingredients": list(dict.fromkeys(unresolved_ingredients)),
            "profile_context": personalization_service.build_profile_context(profile),
            "nutrition_targets": targets,
        }

    def recalculate_per_serving(self, nutrition_total: dict[str, Any], servings: int, targets: dict[str, float] | None = None) -> dict[str, Any]:
        divisor = max(int(servings or 1), 1)
        effective_targets = targets or {
            key: float(item.get("target") or self.DEFAULT_TARGETS[key])
            for key, item in nutrition_total.items()
            if key in self.DEFAULT_TARGETS
        }
        per_serving_values = {
            key: float(item.get("value") or 0) / divisor
            for key, item in nutrition_total.items()
            if key in effective_targets
        }
        return self._format_values(per_serving_values, effective_targets)

    def _scale_nutrients(self, nutrients_per_100g: dict[str, Any], grams: float) -> dict[str, float | None]:
        ratio = grams / 100.0
        return {
            key: (round(float(nutrients_per_100g[key]) * ratio, 2) if nutrients_per_100g.get(key) is not None else None)
            for key in self.DEFAULT_TARGETS
        }

    def _targets_from_profile(self, profile: dict[str, Any]) -> dict[str, float]:
        targets = dict(self.DEFAULT_TARGETS)
        goal_text = normalize_text(profile.get("goal"))
        if goal_text and any(token in goal_text for token in ("белк", "protein", "мыш", "gain")) and profile.get("weight_kg"):
            targets["protein"] = max(100.0, float(profile["weight_kg"]) * 1.6)
        return targets

    def _format_values(self, values: dict[str, float], targets: dict[str, float]) -> dict[str, Any]:
        return {
            key: {
                "value": round(value, 2),
                "target": round(targets[key], 2),
                "percent_of_target": round((value / targets[key] * 100) if targets[key] else 0, 2),
            }
            for key, value in values.items()
        }

    def _build_quality(self, resolution_stats: dict[str, int]) -> dict[str, Any]:
        total = max(resolution_stats["ingredient_count"], 1)
        explicit_ratio = resolution_stats["explicit_amount_count"] / total
        matched_ratio = resolution_stats["matched_count"] / total
        trusted_ratio = resolution_stats["trusted_nutrition_count"] / total
        unresolved_ratio = resolution_stats["unresolved_count"] / total
        meaningful_fallback_ratio = resolution_stats["meaningful_fallback_count"] / total
        score = round((explicit_ratio * 0.2 + matched_ratio * 0.35 + trusted_ratio * 0.35 + (1 - meaningful_fallback_ratio) * 0.1) * 100, 2)
        degraded = score < 70 or matched_ratio < 0.6 or trusted_ratio < 0.5 or unresolved_ratio > 0.4
        return {
            "score": score,
            "status": "degraded" if degraded else "ok",
            "explicit_amount_ratio": round(explicit_ratio, 2),
            "matched_ratio": round(matched_ratio, 2),
            "trusted_nutrition_ratio": round(trusted_ratio, 2),
            "unresolved_ratio": round(unresolved_ratio, 2),
            "meaningful_fallback_ratio": round(meaningful_fallback_ratio, 2),
        }

    def _quality_warnings(self, quality: dict[str, Any], resolution_stats: dict[str, int]) -> list[str]:
        warnings: list[str] = []
        if quality["status"] == "degraded":
            warnings.append("Качество расчёта снижено: часть ключевых ингредиентов не была надёжно сопоставлена с продуктовой базой.")
        if quality["score"] < 85 and resolution_stats["meaningful_fallback_count"] >= max(2, resolution_stats["ingredient_count"] // 3):
            warnings.append("Для части значимых ингредиентов масса определена эвристически, а не по явному количеству.")
        return warnings


nutrition_service = NutritionService()
