from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ProductAlias(Base):
    __tablename__ = "product_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(8), default="ru", index=True)
    alias_type: Mapped[str] = mapped_column(String(32), default="alias")
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    product = relationship("Product", back_populates="aliases")
