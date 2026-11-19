from app.db.models import User


def register(client, email="farmer@example.test", password="correct-horse-123"):
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "consent_accepted": True,
            "consent_text_version": "privacy-v1",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_field(client, token):
    response = client.post(
        "/fields",
        headers=auth(token),
        json={"name": "North plot", "crop": "Maize", "crop_stage": "Flowering", "lat": 20.0, "lon": 77.0},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_register_login_me_and_consent(client):
    registered = register(client, "admin@example.test")
    assert registered["user"]["role"] == "agronomist"
    assert len(registered["access_token"]) > 20
    me = client.get("/me", headers=auth(registered["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.test"

    login = client.post("/auth/login", json={"email": "ADMIN@example.test", "password": "correct-horse-123"})
    assert login.status_code == 200
    assert login.json()["user"]["role"] == "agronomist"
    rejected = client.post(
        "/auth/register",
        json={"email": "no-consent@example.test", "password": "correct-horse-123", "consent_accepted": False},
    )
    assert rejected.status_code == 400



def test_passwords_are_stored_as_argon2_hashes(client, database_session):
    registered = register(client)
    user = database_session.get(User, registered["user"]["id"])
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert user.password_hash != "correct-horse-123"


def test_auth_rejects_bad_password_and_missing_token(client):
    register(client)
    login = client.post("/auth/login", json={"email": "farmer@example.test", "password": "wrong-password"})
    assert login.status_code == 401
    me = client.get("/me")
    assert me.status_code == 401


def test_field_crud_and_owner_access_control(client):
    owner = register(client)
    other = register(client, "other@example.test")
    field = create_field(client, owner["access_token"])
    field_id = field["id"]
    assert client.get("/fields", headers=auth(owner["access_token"])).json()[0]["id"] == field_id
    assert client.get(f"/fields/{field_id}", headers=auth(other["access_token"])).status_code == 404
    assert client.put(
        f"/fields/{field_id}", headers=auth(other["access_token"]), json={"crop": "Wheat"}
    ).status_code == 404
    assert client.delete(f"/fields/{field_id}", headers=auth(other["access_token"])).status_code == 404
    for path in (
        f"/fields/{field_id}/readings",
        f"/fields/{field_id}/weather",
        f"/fields/{field_id}/irrigation/history",
    ):
        assert client.get(path, headers=auth(other["access_token"])).status_code == 404
    assert client.put(
        f"/fields/{field_id}", headers=auth(owner["access_token"]), json={"crop": None}
    ).status_code == 422

    updated = client.put(f"/fields/{field_id}", headers=auth(owner["access_token"]), json={"crop": "Wheat"})
    assert updated.status_code == 200
    assert updated.json()["crop"] == "Wheat"
    assert client.delete(f"/fields/{field_id}", headers=auth(owner["access_token"])).status_code == 204


def test_manual_csv_readings_and_history(client):
    user = register(client)
    field = create_field(client, user["access_token"])
    headers = auth(user["access_token"])
    manual = client.post(
        f"/fields/{field['id']}/readings",
        headers=headers,
        json={"soil_moisture_pct": 25, "temp_c": 30, "humidity_pct": 70},
    )
    assert manual.status_code == 201
    assert manual.json()["source"] == "manual"
    imported = client.post(
        f"/fields/{field['id']}/readings/csv",
        headers=headers,
        files={"file": ("readings.csv", "soil_moisture_pct,temp_c,humidity_pct\n35,32,65\n", "text/csv")},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["imported"] == 1
    assert imported.json()["readings"][0]["source"] == "csv"
    history = client.get(f"/fields/{field['id']}/readings", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) == 2


def test_irrigation_decision_history_and_manual_override(client):
    user = register(client)
    field = create_field(client, user["access_token"])
    headers = auth(user["access_token"])
    decision = client.post(
        f"/fields/{field['id']}/irrigation/decide",
        headers=headers,
        json={"soil_moisture_pct": 20, "temp_c": 39, "humidity_pct": 55, "rain_forecast_mm_24h": 0},
    )
    assert decision.status_code == 201, decision.text
    decision_data = decision.json()
    assert decision_data["action"] == "ON"
    assert decision_data["fired_rules_json"] == ["IR-1", "IR-3"]
    history = client.get(f"/fields/{field['id']}/irrigation/history", headers=headers)
    assert history.status_code == 200
    assert history.json()[0]["id"] == decision_data["id"]

    other = register(client, "other@example.test")
    foreign_override = client.post(
        f"/irrigation/{decision_data['id']}/override",
        headers=auth(other["access_token"]),
        json={"override_action": "OFF"},
    )
    assert foreign_override.status_code == 404

    override = client.post(
        f"/irrigation/{decision_data['id']}/override",
        headers=headers,
        json={"override_action": "OFF", "override_note": "Field already saturated"},
    )
    assert override.status_code == 200, override.text
    assert override.json()["action"] == "ON"
    assert override.json()["override_action"] == "OFF"
    assert override.json()["override_note"] == "Field already saturated"


def test_knowledge_base_retrieval_versioning_and_role_access(client):
    admin = register(client, "admin@example.test")
    headers = auth(admin["access_token"])
    current = client.get("/kb/irrigation", headers=headers)
    assert current.status_code == 200
    assert current.json()["version"] == "v2"
    historical_v1 = client.get("/kb/irrigation?version=v1", headers=headers)
    historical_v2 = client.get("/kb/irrigation?version=v2", headers=headers)
    assert historical_v1.status_code == historical_v2.status_code == 200
    assert "id: IR-4" not in historical_v1.json()["yaml_text"]
    assert "id: IR-4" in historical_v2.json()["yaml_text"]
    broken_thresholds = current.json()["yaml_text"].replace("low_below_pct: 30", "low_below_pct: invalid")
    invalid = client.put("/kb/irrigation", headers=headers, json={"yaml_text": broken_thresholds})
    assert invalid.status_code == 422
    unquoted_action = current.json()["yaml_text"].replace('action: "ON"', "action: ON", 1)
    invalid_action = client.put("/kb/irrigation", headers=headers, json={"yaml_text": unquoted_action})
    assert invalid_action.status_code == 422
    updated = client.put(
        "/kb/irrigation",
        headers=headers,
        json={"yaml_text": current.json()["yaml_text"], "expected_version": "v2"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "v3"
    assert client.get("/kb/irrigation?version=v3", headers=headers).json()["version"] == "v3"
    assert client.get("/kb/irrigation?version=v99", headers=headers).status_code == 404
    versions = client.get("/kb/irrigation/versions", headers=headers)
    assert [item["version"] for item in versions.json()] == ["v1", "v2", "v3"]

    farmer = register(client, "farmer@example.test")
    denied = client.put(
        "/kb/irrigation",
        headers=auth(farmer["access_token"]),
        json={"yaml_text": current.json()["yaml_text"]},
    )
    assert denied.status_code == 403


def test_health_about_and_weather_fallback(client):
    user = register(client)
    headers = auth(user["access_token"])
    field_response = client.post(
        "/fields",
        headers=headers,
        json={"name": "No coordinates", "crop": "Rice", "crop_stage": "Vegetative"},
    )
    field_id = field_response.json()["id"]
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    about = client.get("/about/system")
    assert about.status_code == 200
    assert "feedback" in about.json()
    weather = client.get(f"/fields/{field_id}/weather", headers=headers)
    assert weather.status_code == 200
    assert weather.json()["status"] == "fallback"
    assert weather.json()["rain_forecast_mm_24h"] is None


def test_weather_api_offline_falls_back_to_latest_sensor_reading(client, monkeypatch):
    import httpx
    from app.api import weather as weather_api

    user = register(client)
    headers = auth(user["access_token"])
    field = create_field(client, user["access_token"])
    reading = client.post(
        f"/fields/{field['id']}/readings",
        headers=headers,
        json={"soil_moisture_pct": 42, "temp_c": 29, "humidity_pct": 76},
    )
    assert reading.status_code == 201

    async def fail_weather(_lat, _lon):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(weather_api, "fetch_open_meteo", fail_weather)
    response = client.get(f"/fields/{field['id']}/weather", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "fallback"
    assert response.json()["source"] == "latest_reading"
    assert response.json()["temp_c"] == 29
    assert response.json()["humidity_pct"] == 76
    assert response.json()["rain_forecast_mm_24h"] is None


def test_openapi_artifact_matches_application(client):
    import json
    from pathlib import Path
    from app.main import app

    artifact = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
    assert json.loads(artifact.read_text(encoding="utf-8")) == app.openapi()


def test_account_deletion_removes_owned_data(client, database_session):
    user = register(client)
    field = create_field(client, user["access_token"])
    response = client.delete("/me", headers=auth(user["access_token"]))
    assert response.status_code == 204
    assert database_session.get(User, user["user"]["id"]) is None
    assert client.get(f"/fields/{field['id']}", headers=auth(user["access_token"])).status_code == 401


def test_csv_upload_rate_limit_is_per_user(client, monkeypatch):
    from app.api import readings as readings_api
    from app.core.rate_limit import UploadRateLimiter

    monkeypatch.setattr(readings_api, "csv_upload_limiter", UploadRateLimiter(max_requests=1, window_seconds=60))
    user = register(client)
    field = create_field(client, user["access_token"])
    headers = auth(user["access_token"])
    payload = "soil_moisture_pct,temp_c,humidity_pct\n35,32,65\n"
    first = client.post(
        f"/fields/{field['id']}/readings/csv",
        headers=headers,
        files={"file": ("readings.csv", payload, "text/csv")},
    )
    second = client.post(
        f"/fields/{field['id']}/readings/csv",
        headers=headers,
        files={"file": ("readings.csv", payload, "text/csv")},
    )
    assert first.status_code == 201
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_expired_jwt_is_rejected(client):
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.core.config import get_settings

    settings = get_settings()
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/me", headers=auth(expired))
    assert response.status_code == 401


def test_missing_jwt_secret_does_not_create_an_account(client, database_session, monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy import func, select
    from app.core import security

    monkeypatch.setattr(security, "get_settings", lambda: SimpleNamespace(jwt_secret="", jwt_algorithm="HS256"))
    response = client.post(
        "/auth/register",
        json={"email": "no-secret@example.test", "password": "correct-horse-123", "consent_accepted": True},
    )
    assert response.status_code == 503
    assert database_session.scalar(select(func.count()).select_from(User)) == 0
