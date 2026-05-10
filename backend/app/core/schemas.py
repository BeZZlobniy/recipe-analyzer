from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.structuring.schemas import StructuredRecipe


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthUserResponse(BaseModel):
    id: int
    username: str
    active_profile_id: int | None = None


class AuthResponse(BaseModel):
    user: AuthUserResponse


class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    sex: str | None = None
    age: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    diet_type: str | None = None
    goal: str | None = None
    allergies_json: list[str] = Field(default_factory=list)
    diseases_json: list[str] = Field(default_factory=list)
    preferences_json: list[str] = Field(default_factory=list)
    restrictions_text: str | None = None


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(ProfileBase):
    pass


class ProfileResponse(ProfileBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AnalyzeRequest(BaseModel):
    profile_id: int
    recipe_text: str = Field(min_length=1)
    target_recipe_calories: float | None = Field(default=None, gt=0)


class CompatibilityResponse(BaseModel):
    diet: str
    restriction: str
    goal: str


class ProfileAssessmentBlockResponse(BaseModel):
    key: str
    title: str
    status: str
    compatibility: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ProfileAssessmentResponse(BaseModel):
    goal_alignment: ProfileAssessmentBlockResponse
    allergy_issues: ProfileAssessmentBlockResponse
    disease_issues: ProfileAssessmentBlockResponse
    preference_alignment: ProfileAssessmentBlockResponse
    additional_restrictions: ProfileAssessmentBlockResponse


class PortionGuidanceResponse(BaseModel):
    estimated_recipe_servings: int
    recommended_recipe_servings: int
    calories_total: float
    calories_per_recommended_serving: float
    target_recipe_calories: float | None = None
    summary: str | None = None


class AnalyzeResponse(BaseModel):
    analysis_id: int
    title: str
    clean_recipe_text: str
    structured_recipe: StructuredRecipe
    matched_ingredients: list[dict[str, Any]]
    nutrition_total: dict[str, Any]
    nutrition_per_serving: dict[str, Any]
    detailed_ingredients: list[dict[str, Any]]
    analysis_quality: dict[str, Any]
    resolution_stats: dict[str, Any]
    unresolved_ingredients: list[str]
    rag_context: list[dict[str, Any]]
    summary: str
    detected_issues: list[str]
    recommendations: list[str]
    warnings: list[str]
    compatibility: CompatibilityResponse
    profile_assessment: ProfileAssessmentResponse
    servings: int
    target_recipe_calories: float | None = None
    portion_guidance: PortionGuidanceResponse


class HistoryItemResponse(BaseModel):
    id: int
    profile_id: int
    title: str
    summary: str | None = None
    created_at: datetime
    diet_compatibility: str | None = None
    restriction_compatibility: str | None = None
    goal_compatibility: str | None = None

    class Config:
        from_attributes = True


class AnalysisDetailResponse(BaseModel):
    id: int
    profile_id: int
    title: str
    recipe_text: str
    structured_recipe: StructuredRecipe
    analysis_result: dict[str, Any]
    summary: str | None
    created_at: datetime


class DashboardResponse(BaseModel):
    total_analyses: int
    average_calories_per_recipe: float
    average_calories_per_serving: float
    top_issues: list[dict[str, Any]]
    compatibility_distribution: dict[str, dict[str, int]]
    recent_analyses: list[HistoryItemResponse]
