from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.schemas import AnalyzeRequest, AnalyzeResponse, CompatibilityResponse
from app.models.profile import UserProfile
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User
from app.modules.analysis.service import analysis_service
from app.modules.structuring.schemas import StructuredRecipe


router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("", response_model=AnalyzeResponse)
def analyze_recipe(payload: AnalyzeRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(UserProfile, payload.profile_id)
    if not profile or profile.user_id != user.id:
        raise HTTPException(status_code=404, detail="Profile not found")
    profile_data = {
        "name": profile.name,
        "sex": profile.sex,
        "age": profile.age,
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "diet_type": profile.diet_type,
        "goal": profile.goal,
        "allergies_json": profile.allergies_json or [],
        "diseases_json": profile.diseases_json or [],
        "preferences_json": profile.preferences_json or [],
        "restrictions_text": profile.restrictions_text,
    }
    result = analysis_service.analyze_recipe(db, payload.recipe_text, profile_data)
    analysis = RecipeAnalysis(
        user_id=user.id,
        profile_id=profile.id,
        title=result["title"],
        recipe_text=payload.recipe_text,
        structured_recipe_json=result["structured_recipe"],
        analysis_result_json=result,
        summary=result["summary"],
        diet_compatibility=result["compatibility"]["diet"],
        restriction_compatibility=result["compatibility"]["restriction"],
        goal_compatibility=result["compatibility"]["goal"],
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return AnalyzeResponse(
        analysis_id=analysis.id,
        title=result["title"],
        clean_recipe_text=result["clean_recipe_text"],
        structured_recipe=StructuredRecipe(**result["structured_recipe"]),
        matched_ingredients=result["matched_ingredients"],
        nutrition_total=result["nutrition_total"],
        nutrition_per_serving=result["nutrition_per_serving"],
        detailed_ingredients=result["detailed_ingredients"],
        analysis_quality=result["analysis_quality"],
        resolution_stats=result["resolution_stats"],
        unresolved_ingredients=result["unresolved_ingredients"],
        rag_context=result["rag_context"],
        summary=result["summary"],
        detected_issues=result["detected_issues"],
        recommendations=result["recommendations"],
        warnings=result["warnings"],
        compatibility=CompatibilityResponse(**result["compatibility"]),
    )
