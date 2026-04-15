from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def bootstrap_database() -> None:
    from app.services.kb_catalog_service import kb_catalog_service
    from app.models.external_lookup_cache import ExternalLookupCache
    from app.models.profile import UserProfile
    from app.models.product import Product
    from app.models.product_alias import ProductAlias
    from app.models.product_search_entry import ProductSearchEntry
    from app.models.recipe_analysis import RecipeAnalysis
    from app.models.user import User
    from app.modules.rag.ingredient_resolution import rag_ingredient_resolution_service

    Base.metadata.create_all(bind=engine)
    kb_catalog_service.ensure_built()
    with SessionLocal() as db:
        db.execute(delete(ProductSearchEntry))
        db.execute(delete(ProductAlias))
        db.execute(delete(Product).where(Product.source.in_(["nutrition_db", "canonical_products"])))
        rag_ingredient_resolution_service.clear_legacy_off_data(db)
        db.commit()
        user = db.scalar(select(User).where(User.username == settings.demo_username))
        if user is None:
            user = User(
                username=settings.demo_username,
                password_hash=get_password_hash(settings.demo_password),
                created_at=datetime.now(timezone.utc),
            )
            db.add(user)
            db.commit()
