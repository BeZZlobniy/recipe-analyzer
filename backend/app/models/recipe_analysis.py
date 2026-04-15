from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class RecipeAnalysis(Base):
    __tablename__ = "recipe_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("user_profiles.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    recipe_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured_recipe_json: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis_result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    diet_compatibility: Mapped[str | None] = mapped_column(String(16), nullable=True)
    restriction_compatibility: Mapped[str | None] = mapped_column(String(16), nullable=True)
    goal_compatibility: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="analyses")
    profile = relationship("UserProfile", back_populates="analyses")
