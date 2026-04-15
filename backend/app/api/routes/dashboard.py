from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.schemas import DashboardResponse, HistoryItemResponse
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def get_dashboard(profile_id: int | None = Query(default=None), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(RecipeAnalysis).filter(RecipeAnalysis.user_id == user.id)
    if profile_id is not None:
        query = query.filter(RecipeAnalysis.profile_id == profile_id)
    items = query.order_by(RecipeAnalysis.created_at.desc()).all()

    total = len(items)
    recipe_calories = 0.0
    serving_calories = 0.0
    issues_counter = Counter()
    compatibility_distribution = {
        "diet": {"high": 0, "medium": 0, "low": 0},
        "restriction": {"high": 0, "medium": 0, "low": 0},
        "goal": {"high": 0, "medium": 0, "low": 0},
    }
    for item in items:
        result = item.analysis_result_json or {}
        recipe_calories += float(result.get("nutrition_total", {}).get("calories", {}).get("value", 0) or 0)
        serving_calories += float(result.get("nutrition_per_serving", {}).get("calories", {}).get("value", 0) or 0)
        for issue in result.get("detected_issues", []):
            issues_counter[issue] += 1
        compatibility = result.get("compatibility", {})
        for key in compatibility_distribution:
            level = compatibility.get(key)
            if level in compatibility_distribution[key]:
                compatibility_distribution[key][level] += 1

    return DashboardResponse(
        total_analyses=total,
        average_calories_per_recipe=round(recipe_calories / total, 2) if total else 0.0,
        average_calories_per_serving=round(serving_calories / total, 2) if total else 0.0,
        top_issues=[{"issue": issue, "count": count} for issue, count in issues_counter.most_common(5)],
        compatibility_distribution=compatibility_distribution,
        recent_analyses=[HistoryItemResponse.model_validate(item) for item in items[:5]],
    )
