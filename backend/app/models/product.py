from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    display_name_ru: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    display_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    nutrients_json: Mapped[dict] = mapped_column(JSON, default=dict)
    grams_per_piece_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_confidence: Mapped[str] = mapped_column(String(16), default="medium")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    aliases = relationship("ProductAlias", back_populates="product", cascade="all, delete-orphan")
    search_entries = relationship("ProductSearchEntry", back_populates="product", cascade="all, delete-orphan")
