from __future__ import annotations

from typing import Any

from app.core.utils import normalize_text
from app.modules.analysis.nutrition_rules import (
    DEFAULT_TARGETS,
    estimate_grams,
    is_minor_ingredient,
    resolve_nutrients,
)
from app.modules.structuring.schemas import StructuredIngredient


class NutritionService:
    DEFAULT_TARGETS = DEFAULT_TARGETS

    def calculate(self, ingredients: list[StructuredIngredient], matches: list[dict[str, Any]], profile: dict[str, Any]) -> dict[str, Any]:
        totals_raw = {key: 0.0 for key in self.DEFAULT_TARGETS}
        detailed: list[dict[str, Any]] = []
        warnings: list[str] = []
        unresolved_ingredients: list[str] = []
        servings = max(int(profile.get("servings") or 4), 1)
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
        nutrition_per_serving = self._format_values({key: value / servings for key, value in totals_raw.items()}, targets)
        issues = self.generate_issues(nutrition_per_serving, ingredients, profile)
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
            "detected_issues": issues,
            "compatibility": self.compatibility_scores(issues),
            "analysis_quality": analysis_quality,
            "resolution_stats": resolution_stats,
            "unresolved_ingredients": list(dict.fromkeys(unresolved_ingredients)),
        }

    def generate_issues(self, nutrition_per_serving: dict[str, Any], ingredients: list[StructuredIngredient], profile: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        sodium_pct = float(nutrition_per_serving.get("sodium", {}).get("percent_of_target", 0) or 0)
        fat_pct = float(nutrition_per_serving.get("fat", {}).get("percent_of_target", 0) or 0)
        calories_pct = float(nutrition_per_serving.get("calories", {}).get("percent_of_target", 0) or 0)
        names = " ".join(item.name_canonical for item in ingredients)
        if sodium_pct >= 80:
            issues.append("Натрий на порцию близок к верхней границе нормы.")
        if fat_pct >= 45:
            issues.append("Доля жиров на порцию высокая.")
        if calories_pct >= 45:
            issues.append("Калорийность порции высокая для выбранной цели.")

        restrictions = " ".join(self._profile_restrictions(profile))
        diet_type = normalize_text(profile.get("diet_type"))
        if "лактоз" in restrictions and any(token in names for token in ("сыр", "сметан", "молок", "слив")):
            issues.append("При ограничении по лактозе обнаружены молочные ингредиенты.")
        if ("вегетари" in diet_type or "vegetarian" in diet_type) and any(token in names for token in ("говядин", "куриц", "рыб", "бекон", "свинин")):
            issues.append("Для вегетарианского профиля обнаружены мясные или рыбные ингредиенты.")
        if ("веган" in diet_type or "vegan" in diet_type) and any(token in names for token in ("яйц", "сыр", "сметан", "молок", "слив", "мед")):
            issues.append("Для веганского профиля обнаружены продукты животного происхождения.")
        return list(dict.fromkeys(issues))

    def compatibility_scores(self, issues: list[str]) -> dict[str, str]:
        diet_penalty = restriction_penalty = goal_penalty = 0
        for issue in issues:
            low = issue.lower()
            if "вегетариан" in low or "веган" in low:
                diet_penalty += 2
            if "лактоз" in low or "аллер" in low or "натрий" in low:
                restriction_penalty += 1
            if "калорий" in low or "жиров" in low:
                goal_penalty += 1
        return {"diet": self._level(diet_penalty), "restriction": self._level(restriction_penalty), "goal": self._level(goal_penalty)}

    def _scale_nutrients(self, nutrients_per_100g: dict[str, Any], grams: float) -> dict[str, float | None]:
        ratio = grams / 100.0
        return {
            key: (round(float(nutrients_per_100g[key]) * ratio, 2) if nutrients_per_100g.get(key) is not None else None)
            for key in self.DEFAULT_TARGETS
        }

    def _targets_from_profile(self, profile: dict[str, Any]) -> dict[str, float]:
        targets = dict(self.DEFAULT_TARGETS)
        if profile.get("goal") and "белк" in normalize_text(profile.get("goal")) and profile.get("weight_kg"):
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
        degraded = matched_ratio < 0.6 or trusted_ratio < 0.5 or unresolved_ratio > 0.4 or meaningful_fallback_ratio > 0.4
        score = round((explicit_ratio * 0.2 + matched_ratio * 0.35 + trusted_ratio * 0.35 + (1 - meaningful_fallback_ratio) * 0.1) * 100, 2)
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
            warnings.append("Качество расчета снижено: часть ключевых ингредиентов не была надежно сопоставлена с продуктовой базой.")
        if resolution_stats["meaningful_fallback_count"] >= max(2, resolution_stats["ingredient_count"] // 3):
            warnings.append("Для части значимых ингредиентов масса определена эвристически, а не по явному количеству.")
        return warnings

    def _level(self, penalty: int) -> str:
        return "low" if penalty >= 2 else "medium" if penalty == 1 else "high"

    def _profile_restrictions(self, profile: dict[str, Any]) -> list[str]:
        parts = [*(profile.get("allergies_json") or []), *(profile.get("diseases_json") or []), *(profile.get("preferences_json") or [])]
        if profile.get("restrictions_text"):
            parts.append(profile["restrictions_text"])
        return [normalize_text(item) for item in parts if normalize_text(item)]


nutrition_service = NutritionService()
