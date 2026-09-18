from fastapi.testclient import TestClient
from app.main import app


def test_health():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}


def test_api_rule_mode_responds(sample_cases, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "rule")
    from app.config import get_settings
    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post("/optimize-energy", json=sample_cases[0]["input"])
    assert response.status_code == 200
    body = response.json()
    assert body["scenario_id"] == sample_cases[0]["id"]
    assert len(body["hourly_plan"]) == 24
    assert len(body["directive_interpretation"]) == len(sample_cases[0]["input"]["operator_notes"])


def test_bad_request(sample_cases):
    client = TestClient(app)
    bad = dict(sample_cases[0]["input"])
    bad["hours"] = bad["hours"][:23]
    assert client.post("/optimize-energy", json=bad).status_code == 400
