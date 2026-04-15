from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProductSearchEntry(Base):
    __tablename__ = "product_search_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    search_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(8), default="ru", index=True)
    kind: Mapped[str] = mapped_column(String(32), default="normalized")

    product = relationship("Product", back_populates="search_entries")
