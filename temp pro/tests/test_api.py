"""
API endpoint tests (tests/test_api.py).
Each test gets a fresh RateLimiter + temporary SQLite DB — no shared state.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.database as db_module
from app.limiter import RateLimiter


# ---------------------------------------------------------------------------
# Fixture — one fresh client per test
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    db_file = tmp_path / "test.db"
    fresh_limiter = RateLimiter(default_capacity=10.0, default_refill_rate=1.0)

    with (
        patch("app.routes.limiter.limiter", fresh_limiter),
        patch("app.routes.limiter.db", db_module),
        patch.object(db_module, "DB_PATH", db_file),
    ):
        db_module.init_db()
        from app.main import app
        with TestClient(app) as c:
            yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Configure
# ---------------------------------------------------------------------------

def test_configure_creates_bucket(client):
    r = client.post("/api/configure", json={
        "client_id": "u1", "capacity": 5.0, "refill_rate": 2.0
    })
    assert r.status_code == 200
    body = r.json()
    assert body["capacity"] == 5.0
    assert body["client_id"] == "u1"


def test_configure_zero_capacity_rejected(client):
    r = client.post("/api/configure", json={
        "client_id": "u2", "capacity": 0, "refill_rate": 1.0
    })
    assert r.status_code == 422


def test_configure_negative_rate_rejected(client):
    r = client.post("/api/configure", json={
        "client_id": "u3", "capacity": 10.0, "refill_rate": -1.0
    })
    assert r.status_code == 422


def test_configure_blank_client_rejected(client):
    r = client.post("/api/configure", json={
        "client_id": "  ", "capacity": 10.0, "refill_rate": 1.0
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------

def test_check_allowed(client):
    r = client.post("/api/check", json={"client_id": "a1"})
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is True
    assert body["retry_after"] is None
    assert "tokens_before" in body
    assert "remaining" in body
    assert "capacity" in body
    assert "response_ms" in body


def test_check_denied_when_empty(client):
    for _ in range(10):
        client.post("/api/check", json={"client_id": "drain"})
    r = client.post("/api/check", json={"client_id": "drain"})
    assert r.status_code == 200
    body = r.json()
    assert body["allowed"] is False
    assert body["retry_after"] is not None


def test_check_blank_client_rejected(client):
    r = client.post("/api/check", json={"client_id": ""})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def test_status_unknown_404(client):
    r = client.get("/api/status/ghost")
    assert r.status_code == 404


def test_status_known(client):
    client.post("/api/check", json={"client_id": "s1"})
    r = client.get("/api/status/s1")
    assert r.status_code == 200
    body = r.json()
    assert body["client_id"] == "s1"
    assert body["tokens"] <= body["capacity"]


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def test_reset_known_client(client):
    for _ in range(10):
        client.post("/api/check", json={"client_id": "rst"})
    r = client.post("/api/reset/rst")
    assert r.status_code == 200
    snap = client.get("/api/status/rst").json()
    assert pytest.approx(snap["tokens"], abs=0.1) == snap["capacity"]


def test_reset_unknown_client_404(client):
    r = client.post("/api/reset/nobody")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Request history
# ---------------------------------------------------------------------------

def test_requests_endpoint_returns_list(client):
    client.post("/api/check", json={"client_id": "hist"})
    r = client.get("/api/requests?client_id=hist&minutes=60")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1


# ---------------------------------------------------------------------------
# Analytics endpoints
# ---------------------------------------------------------------------------

def test_analytics_summary_empty(client):
    r = client.get("/api/analytics/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["allow_pct"] == 0.0


def test_analytics_summary_counts(client):
    # Configure with tiny refill so 6th+ requests are denied
    client.post("/api/configure", json={
        "client_id": "x", "capacity": 5.0, "refill_rate": 0.0
    })
    for _ in range(5):
        client.post("/api/check", json={"client_id": "x"})
    for _ in range(3):
        client.post("/api/check", json={"client_id": "x"})  # denied

    r = client.get("/api/analytics/summary?minutes=60")
    body = r.json()
    assert body["total"] == 8
    assert body["allowed"] == 5
    assert body["denied"] == 3


def test_analytics_activity(client):
    client.post("/api/check", json={"client_id": "act"})
    r = client.get("/api/analytics/activity?minutes=60")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_analytics_clients(client):
    client.post("/api/check", json={"client_id": "cl1"})
    client.post("/api/check", json={"client_id": "cl2"})
    r = client.get("/api/analytics/clients?minutes=60")
    assert r.status_code == 200
    ids = [item["client_id"] for item in r.json()]
    assert "cl1" in ids
    assert "cl2" in ids


def test_analytics_tokens(client):
    client.post("/api/check", json={"client_id": "tok"})
    r = client.get("/api/analytics/tokens?client_id=tok&minutes=60")
    assert r.status_code == 200
    assert len(r.json()) >= 1
