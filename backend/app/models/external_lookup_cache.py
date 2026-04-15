from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ExternalLookupCache(Base):
    __tablename__ = "external_lookup_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query_raw: Mapped[str] = mapped_column(String(255), nullable=False)
    query_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    query_lang: Mapped[str] = mapped_column(String(8), default="ru")
    response_json: Mapped[dict] = mapped_column(JSON, default=dict)
    resolved_product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
