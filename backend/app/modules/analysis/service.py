from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.modules.analysis.nutrition import nutrition_service
from app.modules.analysis.portions import portion_service
from app.modules.rag.ingredient_resolution import rag_ingredient_resolution_service
from app.modules.rag.normalization import recipe_normalization_service
from app.modules.rag.service import rag_service


class AnalysisService:
    def analyze_recipe(self, db: Session, recipe_text: str, profile: dict[str, Any]) -> dict[str, Any]:
        structured_recipe, clean_recipe_text = recipe_normalization_service.normalize(recipe_text)
        servings = portion_service.estimate_servings(structured_recipe, profile)
        enriched_profile = {**profile, "servings": servings}
        matched_ingredients = rag_ingredient_resolution_service.resolve(db, clean_recipe_text, structured_recipe)
        nutrition_result = nutrition_service.calculate(structured_recipe.ingredients, matched_ingredients, enriched_profile)
        rag_context = rag_service.retrieve_context(clean_recipe_text, structured_recipe, nutrition_result, profile)
        rag_result = rag_service.generate_analysis(clean_recipe_text, structured_recipe, nutrition_result, profile, rag_context)
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
        }


analysis_service = AnalysisService()
