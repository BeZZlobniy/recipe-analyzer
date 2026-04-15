import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.schemas import AnalysisDetailResponse, HistoryItemResponse
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User
from app.modules.structuring.schemas import StructuredRecipe


router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=list[HistoryItemResponse])
def list_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(RecipeAnalysis).filter(RecipeAnalysis.user_id == user.id).order_by(RecipeAnalysis.created_at.desc()).all()


@router.get("/{analysis_id}", response_model=AnalysisDetailResponse)
def get_history_item(analysis_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(RecipeAnalysis, analysis_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="Analysis not found")
    analysis_result = item.analysis_result_json
    if isinstance(analysis_result, str):
        try:
            analysis_result = json.loads(analysis_result)
        except json.JSONDecodeError:
            analysis_result = {}
    return AnalysisDetailResponse(
        id=item.id,
        profile_id=item.profile_id,
        title=item.title,
        recipe_text=item.recipe_text,
        structured_recipe=StructuredRecipe(**item.structured_recipe_json),
        analysis_result=analysis_result,
        summary=item.summary,
        created_at=item.created_at,
    )
