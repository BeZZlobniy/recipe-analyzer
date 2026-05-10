from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash


DEMO_PROFILE_SEED = [
    {
        "name": "Анна, вегетарианка без лактозы",
        "legacy_names": ["DemoProfile"],
        "sex": "female",
        "age": 29,
        "weight_kg": 63.0,
        "height_cm": 168.0,
        "diet_type": "Вегетарианец",
        "goal": "Поддержание здорового питания",
        "allergies_json": ["Лактоза", "молочные продукты"],
        "diseases_json": [],
        "preferences_json": ["Сытная еда", "Больше белка"],
        "restrictions_text": "Не люблю острое. Избегаю мяса, птицы и рыбы.",
    },
    {
        "name": "Сергей, набор мышечной массы",
        "legacy_names": [],
        "sex": "male",
        "age": 34,
        "weight_kg": 86.0,
        "height_cm": 184.0,
        "diet_type": "Сбалансированное питание",
        "goal": "Набор мышечной массы",
        "allergies_json": [],
        "diseases_json": [],
        "preferences_json": ["Высокобелковая диета", "Можно мясо и рыбу"],
        "restrictions_text": "Хочу больше белка и умеренную калорийность на порцию.",
    },
    {
        "name": "Мария, контроль сахара",
        "legacy_names": [],
        "sex": "female",
        "age": 47,
        "weight_kg": 72.0,
        "height_cm": 164.0,
        "diet_type": "Низкоуглеводное питание",
        "goal": "Снижение веса",
        "allergies_json": [],
        "diseases_json": ["Диабет 2 типа"],
        "preferences_json": ["Меньше сахара", "Больше клетчатки"],
        "restrictions_text": "Ограничить сахар, мед, сладкие десерты и большие порции быстрых углеводов.",
    },
    {
        "name": "Ирина, низкая соль",
        "legacy_names": [],
        "sex": "female",
        "age": 58,
        "weight_kg": 78.0,
        "height_cm": 166.0,
        "diet_type": "Средиземноморское питание",
        "goal": "Поддержание здорового питания",
        "allergies_json": ["Креветки", "морепродукты"],
        "diseases_json": ["Гипертония"],
        "preferences_json": ["Меньше соли", "Больше овощей"],
        "restrictions_text": "Следить за натрием, избегать пересоленных продуктов и морепродуктов.",
    },
    {
        "name": "Никита, веган без глютена",
        "legacy_names": [],
        "sex": "male",
        "age": 26,
        "weight_kg": 70.0,
        "height_cm": 178.0,
        "diet_type": "Веган",
        "goal": "Поддержание здорового питания",
        "allergies_json": ["Глютен"],
        "diseases_json": [],
        "preferences_json": ["Растительная еда", "Не люблю острое"],
        "restrictions_text": "Без мяса, рыбы, молочных продуктов, яиц, меда и пшеничной муки.",
    },
]


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
    from app.models import Product, User, UserProfile

    Base.metadata.create_all(bind=engine)
    kb_catalog_service.ensure_built()
    with SessionLocal() as db:
        db.execute(delete(Product).where(Product.source.in_(["nutrition_db", "canonical_products"])))
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
            db.refresh(user)

        seeded_profiles: list[UserProfile] = []
        now = datetime.now(timezone.utc)
        for profile_payload in DEMO_PROFILE_SEED:
            legacy_names = profile_payload.get("legacy_names", [])
            profile = db.scalar(
                select(UserProfile).where(
                    UserProfile.user_id == user.id,
                    UserProfile.name.in_([profile_payload["name"], *legacy_names]),
                )
            )
            fields = {key: value for key, value in profile_payload.items() if key != "legacy_names"}
            if profile is None:
                profile = UserProfile(user_id=user.id, created_at=now, **fields)
                db.add(profile)
            else:
                for key, value in fields.items():
                    setattr(profile, key, value)
                profile.updated_at = now
            seeded_profiles.append(profile)

        db.commit()
        for profile in seeded_profiles:
            db.refresh(profile)
        if user.active_profile_id is None and seeded_profiles:
            user.active_profile_id = seeded_profiles[0].id
            db.commit()
