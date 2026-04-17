from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.db import Base, get_db
from app.core.security import get_password_hash
from app.models.profile import UserProfile
from app.models.recipe_analysis import RecipeAnalysis
from app.models.user import User


def _import_models() -> None:
    import app.models.profile  # noqa: F401
    import app.models.recipe_analysis  # noqa: F401
    import app.models.user  # noqa: F401


@pytest.fixture
def session_factory(tmp_path):
    _import_models()
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    try:
        yield testing_session_local
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def app(monkeypatch, session_factory):
    import app.main as main_module

    monkeypatch.setattr(main_module, "bootstrap_database", lambda: None)
    test_app = main_module.create_app()

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    test_app.dependency_overrides[get_db] = override_get_db
    return test_app


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def seeded_user(session_factory):
    with session_factory() as db:
        user = User(
            username="tester",
            password_hash=get_password_hash("secret123"),
            created_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        profile = UserProfile(
            user_id=user.id,
            name="Test Profile",
            sex="male",
            age=30,
            weight_kg=80.0,
            height_cm=180.0,
            diet_type="vegetarian",
            goal="balanced diet",
            allergies_json=[],
            diseases_json=[],
            preferences_json=[],
            restrictions_text=None,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

        user.active_profile_id = profile.id
        db.add(user)
        db.commit()

        return {
            "user_id": user.id,
            "username": user.username,
            "password": "secret123",
            "profile_id": profile.id,
        }


@pytest.fixture
def authenticated_client(client, seeded_user):
    response = client.post(
        "/api/auth/login",
        json={"username": seeded_user["username"], "password": seeded_user["password"]},
    )
    assert response.status_code == 200
    return client


@pytest.fixture
def analysis_record(session_factory, seeded_user):
    payload = {
        "title": "Stored Recipe",
        "clean_recipe_text": "Stored Recipe",
        "structured_recipe": {
            "title": "Stored Recipe",
            "servings_declared": "2",
            "ingredients": [],
            "steps": [],
            "notes": [],
            "source_recipe_text": "Stored Recipe",
        },
        "nutrition_total": {
            "calories": {"value": 320.0},
        },
        "nutrition_per_serving": {
            "calories": {"value": 160.0},
        },
        "summary": "Stored summary",
        "detected_issues": ["demo issue"],
        "compatibility": {"diet": "high", "restriction": "medium", "goal": "low"},
    }
    with session_factory() as db:
        analysis = RecipeAnalysis(
            user_id=seeded_user["user_id"],
            profile_id=seeded_user["profile_id"],
            title=payload["title"],
            recipe_text="Stored Recipe",
            structured_recipe_json=payload["structured_recipe"],
            analysis_result_json=payload,
            summary=payload["summary"],
            diet_compatibility="high",
            restriction_compatibility="medium",
            goal_compatibility="low",
        )
        db.add(analysis)
        db.commit()
        db.refresh(analysis)
        return analysis.id
