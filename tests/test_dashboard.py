"""Tests for the web dashboard."""
import os
import pytest

from compound_agent.dashboard import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app_no_deps():
    """Flask app with no injected dependencies."""
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client_no_deps(app_no_deps):
    return app_no_deps.test_client()


class _FakeConfig:
    agent_mode = "multi-agent"


class _FakeAgentState:
    current_state = "idle"


class _FakeMemory:
    def get_engagement_stats(self, days=7):
        return {
            "total": 10,
            "positive": 5,
            "negative": 1,
            "bookmark": 2,
            "ignored": 2,
            "engagement_rate": 0.8,
        }

    def get_preferred_categories(self, top_n=10):
        return [("tech", 0.9), ("science", 0.7)]

    def get_source_rankings(self, min_shown=1):
        return [("hn", 0.85), ("arxiv", 0.6)]


class _FakeEventLog:
    def get_events(self, limit=50):
        return [
            {
                "event_id": "abc-123",
                "event_type": "cycle_start",
                "agent": "orchestrator",
                "timestamp": "2024-01-01T00:00:00Z",
                "task": {},
                "result": {},
            }
        ]


@pytest.fixture
def app_full():
    app = create_app(
        config=_FakeConfig(),
        memory=_FakeMemory(),
        event_log=_FakeEventLog(),
        agent_state=_FakeAgentState(),
    )
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client_full(app_full):
    return app_full.test_client()


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_health_returns_200(self, client_no_deps):
        resp = client_no_deps.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok(self, client_no_deps):
        data = resp = client_no_deps.get("/health").get_json()
        assert data["status"] == "ok"

    def test_health_has_timestamp(self, client_no_deps):
        data = client_no_deps.get("/health").get_json()
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# /api/status
# ---------------------------------------------------------------------------

class TestApiStatus:
    def test_status_returns_200(self, client_full):
        resp = client_full.get("/api/status")
        assert resp.status_code == 200

    def test_status_returns_agent_mode(self, client_full):
        data = client_full.get("/api/status").get_json()
        assert data["agent_mode"] == "multi-agent"

    def test_status_returns_state(self, client_full):
        data = client_full.get("/api/status").get_json()
        assert data["state"] == "idle"

    def test_status_no_config_returns_unknown(self, client_no_deps):
        data = client_no_deps.get("/api/status").get_json()
        assert data["agent_mode"] == "unknown"


# ---------------------------------------------------------------------------
# /api/events
# ---------------------------------------------------------------------------

class TestApiEvents:
    def test_events_returns_200(self, client_full):
        resp = client_full.get("/api/events")
        assert resp.status_code == 200

    def test_events_returns_list(self, client_full):
        data = client_full.get("/api/events").get_json()
        assert isinstance(data["events"], list)

    def test_events_contains_expected_event(self, client_full):
        data = client_full.get("/api/events").get_json()
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "cycle_start"

    def test_events_no_event_log_returns_empty(self, client_no_deps):
        data = client_no_deps.get("/api/events").get_json()
        assert data["events"] == []

    def test_events_count_field_matches(self, client_full):
        data = client_full.get("/api/events").get_json()
        assert data["count"] == len(data["events"])


# ---------------------------------------------------------------------------
# /api/memory
# ---------------------------------------------------------------------------

class TestApiMemory:
    def test_memory_returns_200(self, client_full):
        resp = client_full.get("/api/memory")
        assert resp.status_code == 200

    def test_memory_has_engagement_stats(self, client_full):
        data = client_full.get("/api/memory").get_json()
        assert "engagement_7d" in data
        assert data["engagement_7d"]["total"] == 10

    def test_memory_has_categories(self, client_full):
        data = client_full.get("/api/memory").get_json()
        cats = data["preferred_categories"]
        assert len(cats) == 2
        assert cats[0]["category"] == "tech"
        assert cats[0]["score"] == 0.9

    def test_memory_has_source_rankings(self, client_full):
        data = client_full.get("/api/memory").get_json()
        sources = data["source_rankings"]
        assert sources[0]["source"] == "hn"
        assert sources[0]["quality"] == 0.85

    def test_memory_no_memory_returns_empty(self, client_no_deps):
        data = client_no_deps.get("/api/memory").get_json()
        assert data == {}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class TestAuth:
    def test_no_password_allows_access(self, client_no_deps, monkeypatch):
        # DASHBOARD_PASSWORD is "" by default — access allowed
        resp = client_no_deps.get("/health")
        assert resp.status_code == 200

    def test_wrong_password_returns_401(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        from compound_agent.dashboard import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        # /api/status requires auth (not /health which is exempt)
        resp = client.get("/api/status", headers={"Authorization": "Basic dXNlcjp3cm9uZw=="})
        assert resp.status_code == 401

    def test_correct_password_allows_access(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        from compound_agent.dashboard import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        # base64("user:secret") = "dXNlcjpzZWNyZXQ="
        resp = client.get("/api/status", headers={"Authorization": "Basic dXNlcjpzZWNyZXQ="})
        assert resp.status_code == 200

    def test_health_exempt_from_auth(self, monkeypatch):
        monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
        from compound_agent.dashboard import create_app
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        # /health should work without auth even when password is set
        resp = client.get("/health")
        assert resp.status_code == 200
