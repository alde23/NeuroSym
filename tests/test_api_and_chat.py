"""End-to-end tests for Multi-Turn Conversational Chat Agent and FastAPI Backend Endpoints."""

import pytest
from fastapi.testclient import TestClient

from neurosym.api.server import app
from neurosym.chat.agent import NeuroSymChatAgent
from neurosym.rules.models import FeasibilityVerdict


@pytest.fixture
def client():
    return TestClient(app)


def test_chat_agent_multi_turn_flow():
    """Verify state accumulation and verdict evolution across multi-turn conversation."""
    agent = NeuroSymChatAgent()
    session_id = "test-session-123"

    # Turn 1: Infeasible proposal (only 2 partners in 1 country)
    res1 = agent.process_message(
        "We want to submit a 36-month Horizon Europe Research and Innovation Action on robotics with 2 partners in Germany.",
        session_id=session_id
    )
    assert res1.session_id == session_id
    assert res1.verdict in (FeasibilityVerdict.INFEASIBLE, "INFEASIBLE")
    assert res1.proposal_context.partner_count == 2
    assert "DE" in res1.proposal_context.countries
    assert len(res1.regulatory_evidence) > 0

    # Turn 2: Fix proposal by adding Netherlands and Sweden
    res2 = agent.process_message(
        "What if we add a research partner in the Netherlands and a university in Sweden?",
        session_id=session_id
    )
    # Check that countries and partner count accumulated
    assert set(["DE", "NL", "SE"]).issubset(set(res2.proposal_context.countries))
    assert res2.proposal_context.partner_count >= 3
    assert res2.verdict in (FeasibilityVerdict.FEASIBLE, FeasibilityVerdict.CONDITIONALLY_FEASIBLE, "FEASIBLE", "CONDITIONALLY FEASIBLE")

    # Turn 3: Budget calibration follow-up
    res3 = agent.process_message(
        "What would be the expected budget range based on past CORDIS projects?",
        session_id=session_id
    )
    assert res3.domain_statistics is not None
    assert res3.domain_statistics.budget_p50 > 0


def test_chat_agent_out_of_domain():
    """Verify out-of-domain prompt returns polite refusal and preserves session integrity."""
    agent = NeuroSymChatAgent()
    res = agent.process_message("How do I make chocolate chip cookies from scratch?")
    assert res.verdict in (FeasibilityVerdict.OUT_OF_DOMAIN, "OUT_OF_DOMAIN")
    assert "horizon europe" in res.reply.lower()


def test_fastapi_health_endpoint(client):
    """Verify GET /api/health."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["duckdb_connected"] is True
    assert data["rules_count"] > 0


def test_fastapi_rules_and_schema_endpoints(client):
    """Verify GET /api/rules and GET /api/schema."""
    res_rules = client.get("/api/rules")
    assert res_rules.status_code == 200
    assert len(res_rules.json()["rules"]) >= 5

    res_schema = client.get("/api/schema")
    assert res_schema.status_code == 200
    assert "entities" in res_schema.json()
    assert "project" in res_schema.json()["entities"]


def test_fastapi_chat_endpoint(client):
    """Verify POST /api/chat with full response serialization."""
    payload = {
        "message": "We are planning a 36-month Horizon Europe RIA with 4 partners in Germany, Netherlands, and Sweden for robotics.",
        "session_id": "api-test-session"
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    
    assert data["session_id"] == "api-test-session"
    assert data["verdict"] in ("FEASIBLE", "CONDITIONALLY FEASIBLE")
    assert "reply" in data and len(data["reply"]) > 0
    assert len(data["regulatory_evidence"]) > 0
    assert data["proposal_context"]["distinct_country_count"] == 3


def test_fastapi_evaluate_endpoint(client):
    """Verify POST /api/evaluate."""
    payload = {
        "prompt": "Horizon Europe RIA with 4 partners in Germany, Netherlands, Sweden for 36 months."
    }
    response = client.post("/api/evaluate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["verdict"] in ("FEASIBLE", "CONDITIONALLY FEASIBLE")
    assert "confidence_score" in data


def test_fastapi_query_endpoint(client):
    """Verify POST /api/query."""
    payload = {
        "prompt": "Find robotics projects with budget over 2 million EUR"
    }
    response = client.post("/api/query", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "generated_sql" in data
    assert data["total_matches"] >= 0


def test_fastapi_sessions_and_stream(client):
    """Verify GET /api/sessions and POST /api/chat/stream SSE endpoint."""
    # 1. Start stream chat
    payload = {
        "message": "We have 4 partners in Germany, Netherlands, and Sweden for 36 months.",
        "session_id": "stream-session-1"
    }
    stream_res = client.post("/api/chat/stream", json=payload)
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]
    stream_content = stream_res.text
    assert "data:" in stream_content
    assert "complete" in stream_content

    # 2. Check session list
    sessions_res = client.get("/api/sessions")
    assert sessions_res.status_code == 200
    sessions_data = sessions_res.json()["sessions"]
    assert any(s["session_id"] == "stream-session-1" for s in sessions_data)


def test_web_frontend_static_serving(client):
    """Verify web frontend HTML, CSS, theme.css, and app.js are served at root /."""
    res_index = client.get("/")
    assert res_index.status_code == 200
    assert "NeuroSym AI" in res_index.text
    assert "data-theme=" in res_index.text

    res_theme = client.get("/theme.css")
    assert res_theme.status_code == 200
    assert "--font-sans" in res_theme.text
    assert "horizon-dark" in res_theme.text

    res_app = client.get("/app.js")
    assert res_app.status_code == 200
    assert "NeuroSymApp" in res_app.text
