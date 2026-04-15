from __future__ import annotations

from typing import Any

from app.core.utils import dedupe_texts, normalize_spaces
from app.modules.rag.retrieval import retrieval_service
from app.modules.structuring.schemas import StructuredRecipe
from app.services.ollama_service import ollama_service


class RagService:
    def retrieve_context(
        self,
        recipe_text: str,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        queries = []
        for key in ("diet_type", "goal", "restrictions_text"):
            if profile.get(key):
                queries.append(str(profile[key]))
        queries.extend(profile.get("allergies_json") or [])
        queries.extend(profile.get("diseases_json") or [])
        queries.extend(profile.get("preferences_json") or [])
        queries.extend([recipe.title, recipe_text[:500]])
        queries.extend([item.name_canonical for item in recipe.ingredients[:10]])
        queries.extend(nutrition_result.get("detected_issues", [])[:6])
        if nutrition_result["nutrition_per_serving"]["calories"]["value"] >= 500:
            queries.append("high calories per serving")
        if nutrition_result["nutrition_per_serving"]["sodium"]["value"] >= 700:
            queries.append("high sodium")
        return retrieval_service.search(dedupe_texts(queries)[:12], top_k=6)

    def generate_analysis(
        self,
        recipe_text: str,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        profile: dict[str, Any],
        rag_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        analysis_input = {
            "recipe_text": recipe_text,
            "structured_recipe": recipe.model_dump(),
            "nutrition_total": nutrition_result["nutrition_total"],
            "nutrition_per_serving": nutrition_result["nutrition_per_serving"],
            "detected_issues": nutrition_result["detected_issues"],
            "compatibility": nutrition_result["compatibility"],
            "analysis_quality": nutrition_result["analysis_quality"],
            "unresolved_ingredients": nutrition_result["unresolved_ingredients"],
            "profile": profile,
            "rag_context": rag_context,
        }
        try:
            llm_result = ollama_service.generate_profile_analysis(analysis_input)
        except Exception:
            llm_result = None
        return self._merge_with_fallback(recipe, nutrition_result, rag_context, llm_result)

    def _merge_with_fallback(
        self,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        rag_context: list[dict[str, Any]],
        llm_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        fallback = self._fallback_response(recipe, nutrition_result, rag_context)
        if not isinstance(llm_result, dict):
            return fallback
        compatibility = self._merge_compatibility(
            fallback["compatibility"],
            llm_result.get("compatibility") if isinstance(llm_result.get("compatibility"), dict) else None,
        )
        return {
            "summary": llm_result.get("summary") or fallback["summary"],
            "detected_issues": llm_result.get("detected_issues") or fallback["detected_issues"],
            "recommendations": llm_result.get("recommendations") or fallback["recommendations"],
            "warnings": dedupe_texts((llm_result.get("warnings") or []) + fallback["warnings"]),
            "compatibility": {
                "diet": compatibility.get("diet") or fallback["compatibility"]["diet"],
                "restriction": compatibility.get("restriction") or fallback["compatibility"]["restriction"],
                "goal": compatibility.get("goal") or fallback["compatibility"]["goal"],
            },
        }

    def _merge_compatibility(
        self,
        fallback: dict[str, str],
        llm: dict[str, str] | None,
    ) -> dict[str, str]:
        if not isinstance(llm, dict):
            return fallback

        allowed = {"low", "medium", "high"}
        severity_rank = {"low": 0, "medium": 1, "high": 2}
        merged: dict[str, str] = {}

        for key in ("diet", "restriction", "goal"):
            fallback_level = fallback.get(key, "medium")
            llm_level = llm.get(key, fallback_level)
            if llm_level not in allowed:
                llm_level = fallback_level

            # Do not let a vague LLM "medium" overwrite a more informative rule-based score.
            if llm_level == "medium" and fallback_level in {"low", "high"}:
                merged[key] = fallback_level
                continue

            # If LLM returned a weaker signal than the deterministic layer, keep deterministic.
            if severity_rank[llm_level] < severity_rank[fallback_level]:
                merged[key] = fallback_level
                continue

            merged[key] = llm_level

        return merged

    def _fallback_response(
        self,
        recipe: StructuredRecipe,
        nutrition_result: dict[str, Any],
        rag_context: list[dict[str, Any]],
    ) -> dict[str, Any]:
        issues = nutrition_result["detected_issues"]
        compatibility = nutrition_result["compatibility"]
        kcal = nutrition_result["nutrition_per_serving"]["calories"]["value"]
        quality = nutrition_result["analysis_quality"]

        summary_parts = [f"Рецепт «{recipe.title}» проанализирован для выбранного профиля."]
        if quality["status"] == "degraded":
            summary_parts.append(
                "Точность расчета снижена, потому что часть ингредиентов не была надежно сопоставлена с USDA FoodData Central."
            )
        if issues:
            summary_parts.append("Выявлены ограничения: " + "; ".join(issues[:2]) + ".")
        else:
            summary_parts.append("Критичных конфликтов с профилем не выявлено.")
        summary_parts.append(f"Ориентировочная калорийность на порцию: {kcal}.")

        recommendations: list[str] = []
        if quality["status"] == "degraded":
            recommendations.append("Уточнить состав и количество ингредиентов, чтобы улучшить точность расчета БЖУ.")
        if compatibility["goal"] == "low":
            recommendations.append("Уменьшить размер порции или скорректировать наиболее калорийные ингредиенты.")
        if compatibility["restriction"] == "low":
            recommendations.append("Проверить состав блюда на соответствие ограничениям профиля перед употреблением.")
        if not recommendations:
            recommendations.append("Сохранить рецепт в истории и использовать как базовую заготовку для дальнейшей корректировки.")

        warnings = list(nutrition_result.get("warnings", []))
        if any(item["ingredient"]["confidence"] == "low" for item in nutrition_result["detailed_ingredients"]):
            warnings.append("Часть ингредиентов определена с низкой уверенностью.")
        if nutrition_result.get("unresolved_ingredients"):
            warnings.append(
                "Не удалось надежно определить нутриенты для: "
                + ", ".join(nutrition_result["unresolved_ingredients"][:5])
                + "."
            )
        if not rag_context:
            warnings.append("RAG-контекст не найден, анализ сформирован по встроенным правилам.")

        return {
            "summary": normalize_spaces(" ".join(summary_parts)),
            "detected_issues": issues,
            "recommendations": dedupe_texts(recommendations),
            "warnings": dedupe_texts(warnings),
            "compatibility": compatibility,
        }


rag_service = RagService()
