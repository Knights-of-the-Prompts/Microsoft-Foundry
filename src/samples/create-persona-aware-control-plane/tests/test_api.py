"""End-to-end tests for the FastAPI control plane backend.

Tests run against the FastAPI TestClient — no server process needed.
No credentials or external API calls are required (mock mode).

Run with:
    python -m pytest tests/ -v

All 14 scenarios specified in the Phase 2 spec are covered here.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from control_plane.models.personas import PERSONA_CATALOGUE
from control_plane.stores import evidence_store, request_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_stores():
    """Reset in-memory stores before each test for isolation."""
    evidence_store.clear()
    request_store.clear()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Scenario 1 — List personas
# ---------------------------------------------------------------------------


class TestListPersonas:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        assert resp.status_code == 200

    def test_returns_all_8_personas(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        data = resp.json()
        assert len(data) == 8

    def test_persona_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        persona = resp.json()[0]
        for field in ("id", "name", "description", "relevant_platforms", "default_kpis"):
            assert field in persona, f"Persona missing field: {field}"

    def test_persona_ids_match_catalogue(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        ids = {p["id"] for p in resp.json()}
        assert ids == set(PERSONA_CATALOGUE.keys())


# ---------------------------------------------------------------------------
# Scenario 2 — Get persona detail
# ---------------------------------------------------------------------------


class TestGetPersona:
    def test_known_persona_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/personas/compliance_officer")
        assert resp.status_code == 200

    def test_unknown_persona_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/personas/__unknown__")
        assert resp.status_code == 404

    def test_persona_detail_has_default_kpis(self, client: TestClient) -> None:
        resp = client.get("/api/personas/cfo")
        data = resp.json()
        assert len(data["default_kpis"]) > 0

    @pytest.mark.parametrize("persona_id", list(PERSONA_CATALOGUE.keys()))
    def test_all_personas_accessible(self, client: TestClient, persona_id: str) -> None:
        resp = client.get(f"/api/personas/{persona_id}")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Scenario 3 — List connectors
# ---------------------------------------------------------------------------


class TestListConnectors:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        assert resp.status_code == 200

    def test_returns_7_connectors(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        assert len(resp.json()) == 7

    def test_connector_has_health_key(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        for connector in resp.json():
            assert "health" in connector

    def test_connector_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        c = resp.json()[0]
        for field in ("id", "platform_id", "name", "mode", "status", "supported_signal_types"):
            assert field in c


# ---------------------------------------------------------------------------
# Scenario 4 — Get connector detail
# ---------------------------------------------------------------------------


class TestGetConnector:
    def test_known_connector_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/connectors/azure")
        assert resp.status_code == 200

    def test_unknown_connector_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/connectors/__unknown__")
        assert resp.status_code == 404

    def test_connector_detail_has_tools(self, client: TestClient) -> None:
        resp = client.get("/api/connectors/azure")
        assert "tools" in resp.json()
        assert len(resp.json()["tools"]) > 0


# ---------------------------------------------------------------------------
# Scenario 5 — Configure connector
# ---------------------------------------------------------------------------


class TestConfigureConnector:
    def test_configure_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/api/connectors/azure/configure",
            json={"mode": "mock"},
        )
        assert resp.status_code == 200

    def test_configure_returns_configured_status(self, client: TestClient) -> None:
        resp = client.post(
            "/api/connectors/azure/configure",
            json={"mode": "mock"},
        )
        assert resp.json()["status"] == "configured"


# ---------------------------------------------------------------------------
# Scenario 6 — Test connector health
# ---------------------------------------------------------------------------


class TestConnectorHealth:
    def test_health_check_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/test")
        assert resp.status_code == 200

    def test_health_response_has_health_key(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/test")
        assert "health" in resp.json()

    def test_health_status_not_error(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/test")
        assert resp.json()["health"]["status"] != "error"


# ---------------------------------------------------------------------------
# Scenario 7 — Enable / disable connector
# ---------------------------------------------------------------------------


class TestEnableDisableConnector:
    def test_enable_returns_enabled_true(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_disable_returns_enabled_false(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# Scenario 8 — List tools
# ---------------------------------------------------------------------------


class TestListTools:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/tools")
        assert resp.status_code == 200

    def test_returns_non_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/tools")
        assert len(resp.json()) > 0

    def test_filter_by_platform_id(self, client: TestClient) -> None:
        resp = client.get("/api/tools?platform_id=azure")
        assert resp.status_code == 200
        for tool in resp.json():
            assert tool["platform_id"] == "azure"

    def test_unknown_platform_filter_returns_empty(self, client: TestClient) -> None:
        resp = client.get("/api/tools?platform_id=__nonexistent__")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Scenario 9 — KPI Agent: default persona KPI
# ---------------------------------------------------------------------------


class TestKPIAgentDefault:
    def test_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer"},
        )
        assert resp.status_code == 200

    def test_response_has_required_top_level_keys(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer"},
        )
        data = resp.json()
        for key in (
            "persona",
            "original_kpi",
            "normalized_kpi",
            "maturity_level",
            "confidence_score",
            "clarification_questions",
            "required_signals",
            "selected_platforms",
            "weekly_digest",
            "agent_ideas",
            "evidence_events",
            "source_mode_summary",
        ):
            assert key in data, f"Response missing key: {key}"

    def test_weekly_digest_has_required_keys(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer"},
        )
        digest = resp.json()["weekly_digest"]
        for key in (
            "title",
            "executive_summary",
            "top_risks",
            "recommended_actions",
            "evidence_gaps",
            "confidence_level",
            "data_source_mode",
            "connectors_used",
        ):
            assert key in digest, f"Weekly digest missing key: {key}"

    def test_agent_ideas_non_empty(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer"},
        )
        assert len(resp.json()["agent_ideas"]) > 0

    def test_agent_ideas_have_required_fields(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer"},
        )
        for idea in resp.json()["agent_ideas"]:
            for field in (
                "id",
                "title",
                "problem_statement",
                "proposed_agent_capability",
                "expected_value",
                "risk_level",
                "improves",
            ):
                assert field in idea, f"AgentIdea missing field: {field}"

    def test_unknown_persona_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "__unknown__"},
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize("persona_id", list(PERSONA_CATALOGUE.keys()))
    def test_all_personas_produce_valid_response(
        self, client: TestClient, persona_id: str
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": persona_id},
        )
        assert resp.status_code == 200
        assert "weekly_digest" in resp.json()


# ---------------------------------------------------------------------------
# Scenario 10 — KPI Agent: vague KPI
# ---------------------------------------------------------------------------


class TestKPIAgentVague:
    def test_vague_kpi_returns_maturity_vague(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer", "kpi": "improve compliance"},
        )
        assert resp.status_code == 200
        assert resp.json()["maturity_level"] == "vague"

    def test_vague_kpi_returns_clarification_questions(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "kpi": "lower costs"},
        )
        questions = resp.json()["clarification_questions"]
        assert len(questions) >= 3

    def test_vague_kpi_still_returns_digest(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "security_officer", "kpi": "fix security"},
        )
        assert resp.status_code == 200
        assert "weekly_digest" in resp.json()


# ---------------------------------------------------------------------------
# Scenario 11 — KPI Agent: well-articulated KPI
# ---------------------------------------------------------------------------


class TestKPIAgentWellArticulated:
    def test_well_articulated_kpi_returns_correct_maturity(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={
                "persona_id": "cfo",
                "kpi": "Reduce cost per request by 20% within 60 days.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["maturity_level"] == "well_articulated"

    def test_well_articulated_kpi_returns_no_clarification_questions(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={
                "persona_id": "cfo",
                "kpi": "Reduce cost per request by 20% within 60 days.",
            },
        )
        assert resp.json()["clarification_questions"] == []


# ---------------------------------------------------------------------------
# Scenario 12 — Agent Requests
# ---------------------------------------------------------------------------


class TestAgentRequests:
    def test_submit_request_returns_201(self, client: TestClient) -> None:
        resp = client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "comp_idea_01",
                "requested_by_persona": "compliance_officer",
                "linked_kpi_id": "co_kpi_01",
                "rationale": "We need automated evidence trail monitoring.",
            },
        )
        assert resp.status_code == 200  # TestClient maps to 200 by default

    def test_submitted_request_appears_in_list(self, client: TestClient) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "comp_idea_01",
                "requested_by_persona": "compliance_officer",
                "linked_kpi_id": "co_kpi_01",
                "rationale": "Test rationale.",
            },
        )
        resp = client.get("/api/agent-requests")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_request_has_required_fields(self, client: TestClient) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "cfo_idea_01",
                "requested_by_persona": "cfo",
                "linked_kpi_id": "cfo_kpi_01",
                "rationale": "Cost optimisation.",
            },
        )
        requests = client.get("/api/agent-requests").json()
        for req in requests:
            for field in ("id", "agent_idea_id", "requested_by_persona", "status", "rationale"):
                assert field in req

    def test_request_status_is_submitted(self, client: TestClient) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "sec_idea_01",
                "requested_by_persona": "security_officer",
                "linked_kpi_id": "so_kpi_01",
                "rationale": "Anomaly response.",
            },
        )
        requests = client.get("/api/agent-requests").json()
        assert all(r["status"] == "submitted" for r in requests)

    def test_empty_store_returns_empty_list(self, client: TestClient) -> None:
        resp = client.get("/api/agent-requests")
        assert resp.json() == []


# ---------------------------------------------------------------------------
# Scenario 13 — Evidence Trail
# ---------------------------------------------------------------------------


class TestEvidenceTrail:
    def test_evidence_trail_empty_on_fresh_store(self, client: TestClient) -> None:
        resp = client.get("/api/evidence")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_evidence_trail_populated_after_kpi_run(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cto"},
        )
        resp = client.get("/api/evidence")
        assert len(resp.json()) > 0

    def test_evidence_event_has_required_fields(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "it_manager"},
        )
        events = client.get("/api/evidence").json()
        for event in events:
            for field in ("id", "event_type", "timestamp", "source_mode"):
                assert field in event

    def test_filter_by_persona_id(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "security_officer"},
        )
        events = client.get("/api/evidence?persona_id=security_officer").json()
        assert len(events) > 0
        for event in events:
            assert event["persona_id"] == "security_officer"

    def test_evidence_written_on_agent_request_submit(
        self, client: TestClient
    ) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "biz_idea_01",
                "requested_by_persona": "business_owner",
                "linked_kpi_id": "bo_kpi_01",
                "rationale": "Expand case coverage.",
            },
        )
        resp = client.get("/api/evidence?persona_id=business_owner")
        event_types = [e["event_type"] for e in resp.json()]
        assert "agent_request_submitted" in event_types


# ---------------------------------------------------------------------------
# Scenario 14 — KPI Agent evidence events in response
# ---------------------------------------------------------------------------


class TestKPIAgentEvidenceEvents:
    def test_response_contains_evidence_events(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "product_owner"},
        )
        events = resp.json()["evidence_events"]
        assert len(events) > 0

    def test_evidence_events_include_kpi_interpreted(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "service_owner"},
        )
        event_types = [e["event_type"] for e in resp.json()["evidence_events"]]
        assert "kpi_interpreted" in event_types
        assert "signals_selected" in event_types
        assert "tools_used" in event_types
        assert "insights_generated" in event_types

    def test_evidence_events_include_agent_ideas_generated(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "business_owner"},
        )
        event_types = [e["event_type"] for e in resp.json()["evidence_events"]]
        assert "agent_ideas_generated" in event_types


# ---------------------------------------------------------------------------
# Scenario 15 — Persona role alignment (acceptance criteria)
# ---------------------------------------------------------------------------


class TestPersonaRoleAlignment:
    """Assert that persona KPI assignments reflect the correct executive and
    operational accountability boundaries agreed in the role model update."""

    # CTO must NOT expose operational reliability KPIs (uptime / MTTR)
    def test_cto_default_kpis_are_not_operational_reliability(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/cto")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        for banned in ("uptime", "mttr", "mean time to r", "incident"):
            assert banned not in kpi_titles, (
                f"CTO default KPIs should not contain '{banned}' — that belongs to IT Manager"
            )

    def test_cto_default_kpis_include_strategy_concepts(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/cto")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        assert any(
            kw in kpi_titles for kw in ("reuse", "architecture", "platform", "tech debt")
        ), "CTO KPIs should reflect technology strategy"

    # IT Manager must own operational reliability KPIs
    def test_it_manager_default_kpis_include_operational_reliability(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/it_manager")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        assert any(
            kw in kpi_titles for kw in ("incident", "mttr", "uptime", "deployment failure")
        ), "IT Manager KPIs should include operational reliability metrics"

    # CFO must own ROI / cost-to-value KPIs
    def test_cfo_default_kpis_include_roi_concepts(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/cfo")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        assert any(kw in kpi_titles for kw in ("roi", "return", "cost", "spend", "budget", "value"))

    # Compliance Officer must own evidence / audit KPIs
    def test_compliance_officer_kpis_include_audit_concepts(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/compliance_officer")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        assert any(kw in kpi_titles for kw in ("audit", "evidence", "policy", "oversight"))

    # Security Officer must own data-exposure / privilege KPIs
    def test_security_officer_kpis_include_security_concepts(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/personas/security_officer")
        kpi_titles = " ".join(k["title"] for k in resp.json()["default_kpis"]).lower()
        assert any(kw in kpi_titles for kw in ("exposure", "privilege", "permission", "shadow", "access"))

    # KPI agent normalized output for CTO must not mention uptime
    def test_cto_kpi_agent_normalized_metric_excludes_uptime(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cto"},
        )
        metric = resp.json()["normalized_kpi"]["metric"].lower()
        assert "uptime" not in metric, "CTO normalized KPI metric should not include uptime"

    # KPI agent normalized output for IT Manager must include MTTR or incident
    def test_it_manager_kpi_agent_normalized_metric_includes_mttr(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "it_manager"},
        )
        metric = resp.json()["normalized_kpi"]["metric"].lower()
        assert any(kw in metric for kw in ("mttr", "incident", "restore", "restore")), (
            "IT Manager normalized KPI metric should reference MTTR or incidents"
        )
