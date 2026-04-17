from __future__ import annotations

from app.api.routes import analyze as analyze_route


def _fake_analysis_result(recipe_text: str) -> dict:
    return {
        "title": "Тестовый рецепт",
        "clean_recipe_text": recipe_text,
        "structured_recipe": {
            "title": "Тестовый рецепт",
            "servings_declared": "2",
            "ingredients": [
                {
                    "name_raw": "Яйцо",
                    "name_canonical": "яйцо",
                    "name_en": "egg raw",
                    "amount_value": 2.0,
                    "amount_text": "2 шт.",
                    "unit": "шт",
                    "source": "test",
                    "confidence": "high",
                }
            ],
            "steps": ["Смешать ингредиенты."],
            "notes": [],
            "source_recipe_text": recipe_text,
        },
        "matched_ingredients": [],
        "nutrition_total": {
            "calories": {"value": 320.0, "target": 2000.0, "percent_of_target": 16.0},
        },
        "nutrition_per_serving": {
            "calories": {"value": 160.0, "target": 2000.0, "percent_of_target": 8.0},
        },
        "detailed_ingredients": [],
        "analysis_quality": {
            "score": 98.0,
            "status": "ok",
            "explicit_amount_ratio": 1.0,
            "matched_ratio": 1.0,
            "trusted_nutrition_ratio": 1.0,
            "unresolved_ratio": 0.0,
            "meaningful_fallback_ratio": 0.0,
        },
        "resolution_stats": {
            "ingredient_count": 1,
            "explicit_amount_count": 1,
            "matched_count": 1,
            "trusted_nutrition_count": 1,
            "fallback_grams_count": 0,
            "meaningful_fallback_count": 0,
            "unresolved_count": 0,
        },
        "unresolved_ingredients": [],
        "rag_context": [],
        "summary": "Тестовый анализ выполнен успешно.",
        "detected_issues": ["demo issue"],
        "recommendations": ["demo recommendation"],
        "warnings": [],
        "compatibility": {"diet": "high", "restriction": "medium", "goal": "low"},
    }


def test_auth_login_and_me(client, seeded_user):
    login_response = client.post(
        "/api/auth/login",
        json={"username": seeded_user["username"], "password": seeded_user["password"]},
    )

    assert login_response.status_code == 200
    assert login_response.json()["user"]["username"] == seeded_user["username"]

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["user"]["active_profile_id"] == seeded_user["profile_id"]


def test_profiles_list_and_create(authenticated_client, seeded_user):
    list_response = authenticated_client.get("/api/profiles")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    create_response = authenticated_client.post(
        "/api/profiles",
        json={
            "name": "Cutting Profile",
            "sex": "female",
            "age": 27,
            "weight_kg": 62.0,
            "height_cm": 170.0,
            "diet_type": "vegetarian",
            "goal": "fat loss",
            "allergies_json": ["лактоза"],
            "diseases_json": [],
            "preferences_json": ["овощи"],
            "restrictions_text": "меньше сахара",
        },
    )

    assert create_response.status_code == 201
    assert create_response.json()["name"] == "Cutting Profile"

    second_list_response = authenticated_client.get("/api/profiles")

    assert second_list_response.status_code == 200
    assert len(second_list_response.json()) == 2


def test_analyze_history_and_dashboard_flow(monkeypatch, authenticated_client, seeded_user):
    monkeypatch.setattr(
        analyze_route.analysis_service,
        "analyze_recipe",
        lambda db, recipe_text, profile: _fake_analysis_result(recipe_text),
    )

    analyze_response = authenticated_client.post(
        "/api/analyze",
        json={"profile_id": seeded_user["profile_id"], "recipe_text": "Яйцо - 2 шт."},
    )

    assert analyze_response.status_code == 200
    analysis_payload = analyze_response.json()
    analysis_id = analysis_payload["analysis_id"]
    assert analysis_payload["title"] == "Тестовый рецепт"
    assert analysis_payload["nutrition_per_serving"]["calories"]["value"] == 160.0

    history_response = authenticated_client.get("/api/history")

    assert history_response.status_code == 200
    assert len(history_response.json()) == 1
    assert history_response.json()[0]["id"] == analysis_id

    detail_response = authenticated_client.get(f"/api/history/{analysis_id}")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["analysis_result"]["summary"] == "Тестовый анализ выполнен успешно."
    assert detail_payload["analysis_result"]["compatibility"]["goal"] == "low"

    dashboard_response = authenticated_client.get("/api/dashboard")

    assert dashboard_response.status_code == 200
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["total_analyses"] == 1
    assert dashboard_payload["average_calories_per_recipe"] == 320.0
    assert dashboard_payload["average_calories_per_serving"] == 160.0
    assert dashboard_payload["compatibility_distribution"]["diet"]["high"] == 1
    assert dashboard_payload["compatibility_distribution"]["restriction"]["medium"] == 1
    assert dashboard_payload["compatibility_distribution"]["goal"]["low"] == 1
