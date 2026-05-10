from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.analysis.nutrition import nutrition_service
from app.modules.analysis.portions import portion_service
from app.modules.rag.ingredient_resolution import rag_ingredient_resolution_service
from app.modules.rag.normalization import recipe_normalization_service
from app.modules.rag.service import rag_service


class AnalysisService:
    def analyze_recipe(
        self,
        db: Session,
        recipe_text: str,
        profile: dict[str, Any],
        target_recipe_calories: float | None = None,
    ) -> dict[str, Any]:
        structured_recipe, clean_recipe_text = recipe_normalization_service.normalize(recipe_text)
        estimated_recipe_servings = portion_service.estimate_recipe_servings(structured_recipe, clean_recipe_text)

        matched_ingredients = rag_ingredient_resolution_service.resolve(db, clean_recipe_text, structured_recipe)
        nutrition_result = nutrition_service.calculate(
            structured_recipe.ingredients,
            matched_ingredients,
            {
                **profile,
                "servings": max(estimated_recipe_servings, 1),
                "target_recipe_calories": target_recipe_calories,
            },
        )

        recommended_recipe_servings = portion_service.recommend_recipe_servings(
            estimated_recipe_servings=estimated_recipe_servings,
            nutrition_total=nutrition_result["nutrition_total"],
            target_recipe_calories=target_recipe_calories,
        )
        nutrition_result["nutrition_per_serving"] = nutrition_service.recalculate_per_serving(
            nutrition_result["nutrition_total"],
            recommended_recipe_servings,
            nutrition_result.get("nutrition_targets"),
        )

        portion_guidance = portion_service.build_guidance(
            estimated_recipe_servings=estimated_recipe_servings,
            recommended_recipe_servings=recommended_recipe_servings,
            nutrition_total=nutrition_result["nutrition_total"],
            target_recipe_calories=target_recipe_calories,
        )
        nutrition_result["portion_guidance"] = portion_guidance

        rag_context = rag_service.retrieve_context(
            clean_recipe_text,
            structured_recipe,
            matched_ingredients,
            nutrition_result,
            {
                **profile,
                "servings": recommended_recipe_servings,
                "target_recipe_calories": target_recipe_calories,
            },
        )
        rag_result = rag_service.generate_analysis(
            clean_recipe_text,
            structured_recipe,
            matched_ingredients,
            nutrition_result,
            {
                **profile,
                "servings": recommended_recipe_servings,
                "target_recipe_calories": target_recipe_calories,
            },
            rag_context,
        )

        return {
            "title": structured_recipe.title,
            "clean_recipe_text": clean_recipe_text,
            "structured_recipe": structured_recipe.model_dump(),
            "matched_ingredients": matched_ingredients,
            "nutrition_total": nutrition_result["nutrition_total"],
            "nutrition_per_serving": nutrition_result["nutrition_per_serving"],
            "detailed_ingredients": nutrition_result["detailed_ingredients"],
            "analysis_quality": nutrition_result["analysis_quality"],
            "resolution_stats": nutrition_result["resolution_stats"],
            "unresolved_ingredients": nutrition_result["unresolved_ingredients"],
            "rag_context": rag_context,
            "summary": rag_result["summary"],
            "detected_issues": rag_result["detected_issues"],
            "recommendations": rag_result["recommendations"],
            "warnings": rag_result["warnings"],
            "compatibility": rag_result["compatibility"],
            "profile_assessment": rag_result["profile_assessment"],
            "servings": recommended_recipe_servings,
            "portion_guidance": portion_guidance,
            "target_recipe_calories": target_recipe_calories,
        }


analysis_service = AnalysisService()
