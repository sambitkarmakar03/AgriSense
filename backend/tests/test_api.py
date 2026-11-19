from app.api.schemas import RegisterRequest


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
    updated = client.put(
        "/kb/irrigation",
        headers=headers,
        json={"yaml_text": current.json()["yaml_text"], "expected_version": "v2"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == "v3"
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
