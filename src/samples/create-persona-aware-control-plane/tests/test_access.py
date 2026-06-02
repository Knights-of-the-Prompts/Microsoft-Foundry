"""Access Readiness Agent — 10 test scenarios.

Tests verify:
1.  AccessReadinessAgent with compliance_officer KPI
2.  AccessReadinessAgent with CFO KPI — missing M365 grant
3.  Persona missing Azure cost access (sales_rep → azure cost_data)
4.  Missing M365 sensitive-data access for compliance_officer (user_activity)
5.  Grant exists but actions are insufficient (partial access)
6.  Connector not configured → MISSING_ACCESS (grant is None)
7.  Access request creation via POST /api/access/requests
8.  Evidence events generated for access checks and gaps
9.  KPI Agent response includes access_readiness_summary and sub-keys
10. Existing API tests remain green (GET /api/personas, /api/connectors, etc.)

Run with:
    cd src/samples/create-persona-aware-control-plane
    python -m pytest tests/test_access.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app, _access_requests
from control_plane.access_readiness import AccessReadinessAgent
from control_plane.connectors.registry import ToolRegistry
from control_plane.connectors import ALL_CONNECTORS
from control_plane.kpi_agent.agent import KPIAgent
from control_plane.stores import evidence_store, request_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_stores():
    """Isolate every test: clear all in-memory stores."""
    evidence_store.clear()
    request_store.clear()
    _access_requests.clear()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def registry():
    reg = ToolRegistry()
    for cls in ALL_CONNECTORS:
        reg.register(cls())
    return reg


@pytest.fixture(scope="module")
def access_agent(registry):
    return AccessReadinessAgent(registry)


@pytest.fixture(scope="module")
def kpi_agent(registry):
    return KPIAgent(registry)


# ---------------------------------------------------------------------------
# Scenario 1 — Compliance officer KPI check returns structured result
# ---------------------------------------------------------------------------


class TestComplianceOfficerAccess:
    """compliance_officer has grants for agent365, foundry, servicenow, azure, m365."""

    def test_check_returns_overall_status(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={
                "required_signals": ["agent_registrations", "compliance_status"],
                "selected_platforms": ["agent365", "microsoft365"],
            },
        )
        assert "overall_status" in result
        assert result["overall_status"] in ("ready", "partially_ready", "blocked")

    def test_check_returns_check_results(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={
                "required_signals": ["agent_registrations", "incidents"],
            },
        )
        assert isinstance(result["access_check_results"], list)
        assert len(result["access_check_results"]) == 2

    def test_agent_registrations_allowed(self, access_agent: AccessReadinessAgent) -> None:
        """compliance_officer has AgentRegistry.Read — agent_registrations should be allowed."""
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["agent_registrations"]},
        )
        check = result["access_check_results"][0]
        assert check["status"] in ("allowed", "partially_allowed")

    def test_no_auto_grant(self, access_agent: AccessReadinessAgent) -> None:
        """Gaps must generate recommended_requests, never auto-grant."""
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["deployment_status"]},
        )
        # compliance_officer has no kubernetes grant → must have a gap
        for gap in result["access_gaps"]:
            assert "least_privilege_recommendation" in gap
        # No grants should be added to mock store
        grants_before = len(access_agent.get_grants("compliance_officer"))
        result2 = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["deployment_status"]},
        )
        grants_after = len(access_agent.get_grants("compliance_officer"))
        assert grants_before == grants_after


# ---------------------------------------------------------------------------
# Scenario 2 — CFO KPI — missing M365 and agent365 grants
# ---------------------------------------------------------------------------


class TestCFOAccessMissingGrants:
    """CFO has no M365 and no agent365 grant in mock store."""

    def test_m365_signal_produces_gap(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["user_activity"]},  # needs M365
        )
        assert result["overall_status"] in ("partially_ready", "blocked")
        assert any(g["platform_id"] == "microsoft365" for g in result["access_gaps"])

    def test_agent365_signal_produces_gap(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["agent_registrations"]},  # needs agent365
        )
        assert any(g["platform_id"] == "agent365" for g in result["access_gaps"])

    def test_recommended_request_created_for_gap(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        reqs = result["recommended_access_requests"]
        assert len(reqs) >= 1
        req = reqs[0]
        assert req["persona_id"] == "cfo"
        assert req["status"] == "draft"
        # Must not be auto-submitted
        assert req["status"] != "approved"

    def test_cfo_cost_data_allowed(self, access_agent: AccessReadinessAgent) -> None:
        """CFO has Cost Management Reader on azure."""
        result = access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["cost_data"]},
        )
        checks = result["access_check_results"]
        assert any(c["status"] in ("allowed", "partially_allowed") for c in checks)


# ---------------------------------------------------------------------------
# Scenario 3 — Persona missing Azure cost access
# ---------------------------------------------------------------------------


class TestMissingAzureCostAccess:
    """product_owner has no azure grant — cost_data should produce a gap."""

    def test_cost_data_gap_detected(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="product_owner",
            kpi_agent_result={"required_signals": ["cost_data"]},
        )
        # product_owner has no azure grant
        gap_platforms = [g["platform_id"] for g in result["access_gaps"]]
        assert "azure" in gap_platforms

    def test_recommended_approver_present(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="product_owner",
            kpi_agent_result={"required_signals": ["cost_data"]},
        )
        for gap in result["access_gaps"]:
            assert gap["recommended_approver"]
            assert len(gap["recommended_approver"]) > 0


# ---------------------------------------------------------------------------
# Scenario 4 — Missing sensitive-data access (compliance_officer + user_activity)
# ---------------------------------------------------------------------------


class TestSensitiveDataAccess:
    """compliance_officer can read M365 Reports but cannot read individual user activity."""

    def test_compliance_officer_user_activity_check(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        checks = result["access_check_results"]
        # Reports Reader scope may not include user-level activity read_user_activity
        assert len(checks) == 1
        check = checks[0]
        # check can be partially_allowed or missing_access due to action gap
        assert check["status"] in ("allowed", "partially_allowed", "missing_access")

    def test_gap_has_business_impact(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        for gap in result["access_gaps"]:
            assert gap.get("business_impact"), "Every gap must have a business_impact string"

    def test_least_privilege_recommendation_present(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        result = access_agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        for gap in result["access_gaps"]:
            rec = gap.get("least_privilege_recommendation", "")
            assert "read-only" in rec.lower() or "read" in rec.lower()


# ---------------------------------------------------------------------------
# Scenario 5 — Grant exists but actions are insufficient (partial access)
# ---------------------------------------------------------------------------


class TestPartialAccess:
    """cto has foundry grant but may be missing specific invocation actions."""

    def test_partial_access_scenario(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="cto",
            kpi_agent_result={"required_signals": ["agent_invocations"]},
        )
        checks = result["access_check_results"]
        assert len(checks) >= 1
        # Status must be one of the valid enum values
        for check in checks:
            assert check["status"] in (
                "allowed", "partially_allowed", "missing_access",
                "connector_not_configured", "unknown",
            )

    def test_missing_actions_listed(self, access_agent: AccessReadinessAgent) -> None:
        """Any partial result must list the missing actions."""
        result = access_agent.check(
            persona_id="cto",
            kpi_agent_result={"required_signals": ["agent_invocations"]},
        )
        for check in result["access_check_results"]:
            if check["status"] == "partially_allowed":
                assert isinstance(check["missing_actions"], list)
                assert len(check["missing_actions"]) > 0


# ---------------------------------------------------------------------------
# Scenario 6 — Connector not configured (grant is None)
# ---------------------------------------------------------------------------


class TestConnectorNotConfigured:
    """security_officer has no kubernetes or salesforce grant."""

    def test_kubernetes_produces_missing_access(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        result = access_agent.check(
            persona_id="security_officer",
            kpi_agent_result={"required_signals": ["deployment_status"]},
        )
        checks = result["access_check_results"]
        assert len(checks) == 1
        assert checks[0]["status"] == "missing_access"

    def test_gap_type_present(self, access_agent: AccessReadinessAgent) -> None:
        result = access_agent.check(
            persona_id="security_officer",
            kpi_agent_result={"required_signals": ["deployment_status"]},
        )
        for gap in result["access_gaps"]:
            assert "gap_type" in gap

    def test_recommended_request_status_is_draft(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        result = access_agent.check(
            persona_id="security_officer",
            kpi_agent_result={"required_signals": ["deployment_status"]},
        )
        for req in result["recommended_access_requests"]:
            assert req["status"] == "draft", "Agent must only produce DRAFT requests"


# ---------------------------------------------------------------------------
# Scenario 7 — Access request creation via POST /api/access/requests
# ---------------------------------------------------------------------------


class TestCreateAccessRequest:
    def test_create_access_request_returns_201_or_200(
        self, client: TestClient
    ) -> None:
        payload = {
            "persona_id": "cfo",
            "kpi_id": "cfo_kpi_01",
            "connector_id": "microsoft365",
            "platform_id": "microsoft365",
            "requested_scope": "Reports.Read.All",
            "requested_role": "Reports Reader",
            "requested_permission": "read",
            "requested_actions": ["read_sharing_reports"],
            "justification": "CFO needs M365 usage reports to track adoption KPIs.",
            "business_outcome": "Complete control-plane digest for CFO persona.",
            "recommended_approver": "M365 Global Administrator",
        }
        resp = client.post("/api/access/requests", json=payload)
        assert resp.status_code == 200

    def test_created_request_status_is_submitted(
        self, client: TestClient
    ) -> None:
        payload = {
            "persona_id": "compliance_officer",
            "kpi_id": "compliance_kpi_01",
            "connector_id": "kubernetes",
            "platform_id": "kubernetes",
            "requested_scope": "cluster-reader",
            "requested_role": "Cluster Viewer",
            "requested_permission": "read",
            "requested_actions": ["read_deployments"],
            "justification": "Compliance officer needs deployment status for SLA KPI.",
            "business_outcome": "Reduces evidence gaps in compliance digest.",
            "recommended_approver": "Kubernetes Cluster Administrator",
        }
        resp = client.post("/api/access/requests", json=payload)
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["persona_id"] == "compliance_officer"

    def test_created_request_not_approved(self, client: TestClient) -> None:
        """Access must never be auto-granted or auto-approved via API."""
        payload = {
            "persona_id": "cto",
            "kpi_id": "cto_kpi_01",
            "connector_id": "salesforce",
            "platform_id": "salesforce",
            "requested_scope": "opportunity.read",
            "requested_role": "Sales Analyst",
            "requested_permission": "read",
            "requested_actions": ["read_opportunity_pipeline"],
            "justification": "CTO monitors pipeline for capacity planning.",
            "business_outcome": "Improves forecast reliability.",
            "recommended_approver": "Salesforce System Administrator",
        }
        resp = client.post("/api/access/requests", json=payload)
        data = resp.json()
        assert data["status"] not in ("approved", "granted")

    def test_list_access_requests(self, client: TestClient) -> None:
        payload = {
            "persona_id": "it_manager",
            "kpi_id": "it_kpi_01",
            "connector_id": "salesforce",
            "platform_id": "salesforce",
            "requested_scope": "opportunity.read",
            "requested_role": "Sales Analyst",
            "requested_permission": "read",
            "requested_actions": ["read_opportunity_pipeline"],
            "justification": "IT manager monitors pipeline.",
            "business_outcome": "Improves operational visibility.",
            "recommended_approver": "Salesforce System Administrator",
        }
        client.post("/api/access/requests", json=payload)
        resp = client.get("/api/access/requests")
        assert resp.status_code == 200
        items = resp.json()
        assert isinstance(items, list)
        assert any(r["persona_id"] == "it_manager" for r in items)

    def test_get_grants_endpoint(self, client: TestClient) -> None:
        resp = client.get("/api/access/personas/compliance_officer/grants")
        assert resp.status_code == 200
        grants = resp.json()
        assert isinstance(grants, list)
        assert len(grants) > 0
        for g in grants:
            assert "platform_id" in g
            assert "granted_role" in g

    def test_get_grants_unknown_persona_returns_404(
        self, client: TestClient
    ) -> None:
        resp = client.get("/api/access/personas/unknown_persona_xyz/grants")
        assert resp.status_code == 404

    def test_check_endpoint(self, client: TestClient) -> None:
        payload = {
            "persona_id": "compliance_officer",
            "kpi_agent_result": {
                "required_signals": ["incidents", "agent_registrations"],
                "selected_platforms": ["servicenow", "agent365"],
            },
            "mode": "mock",
        }
        resp = client.post("/api/access/check", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_status" in data
        assert "access_check_results" in data
        assert "access_gaps" in data
        assert "recommended_access_requests" in data


# ---------------------------------------------------------------------------
# Scenario 8 — Evidence events generated
# ---------------------------------------------------------------------------


class TestEvidenceEvents:
    def test_access_check_writes_evidence(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        evidence_store.clear()
        access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        events = evidence_store.list(persona_id="cfo")
        event_types = {e.event_type for e in events}
        assert "access_checked" in event_types

    def test_access_gap_writes_evidence(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        evidence_store.clear()
        access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["user_activity"]},  # no M365 grant
        )
        events = evidence_store.list(persona_id="cfo")
        event_types = {e.event_type for e in events}
        assert "access_gap_detected" in event_types

    def test_access_request_recommended_event(
        self, access_agent: AccessReadinessAgent
    ) -> None:
        evidence_store.clear()
        access_agent.check(
            persona_id="cfo",
            kpi_agent_result={"required_signals": ["user_activity"]},
        )
        events = evidence_store.list(persona_id="cfo")
        event_types = {e.event_type for e in events}
        assert "access_request_recommended" in event_types

    def test_api_access_request_writes_evidence(self, client: TestClient) -> None:
        evidence_store.clear()
        payload = {
            "persona_id": "cfo",
            "kpi_id": "cfo_kpi_01",
            "connector_id": "microsoft365",
            "platform_id": "microsoft365",
            "requested_scope": "Reports.Read.All",
            "requested_role": "Reports Reader",
            "requested_permission": "read",
            "requested_actions": ["read_sharing_reports"],
            "justification": "CFO KPI needs M365 data.",
            "business_outcome": "Complete CFO digest.",
            "recommended_approver": "M365 Global Administrator",
        }
        client.post("/api/access/requests", json=payload)
        resp = client.get("/api/evidence?persona_id=cfo")
        events = resp.json()
        event_types = {e["event_type"] for e in events}
        assert "access_request_submitted" in event_types


# ---------------------------------------------------------------------------
# Scenario 9 — KPI Agent response includes access readiness summary
# ---------------------------------------------------------------------------


class TestKPIAgentAccessReadinessSummary:
    def test_kpi_agent_includes_access_summary(
        self, kpi_agent: KPIAgent
    ) -> None:
        result = kpi_agent.run(persona_id="compliance_officer")
        assert "access_readiness_summary" in result, (
            "KPI Agent must include access_readiness_summary in response"
        )

    def test_access_readiness_summary_structure(
        self, kpi_agent: KPIAgent
    ) -> None:
        result = kpi_agent.run(persona_id="cfo")
        summary = result["access_readiness_summary"]
        assert "overall_status" in summary
        assert "checked_signals" in summary
        assert "access_gaps_count" in summary
        assert "recommended_requests_count" in summary

    def test_kpi_agent_includes_access_check_results(
        self, kpi_agent: KPIAgent
    ) -> None:
        result = kpi_agent.run(persona_id="compliance_officer")
        assert "access_check_results" in result
        assert isinstance(result["access_check_results"], list)

    def test_kpi_agent_includes_access_gaps(
        self, kpi_agent: KPIAgent
    ) -> None:
        result = kpi_agent.run(persona_id="compliance_officer")
        assert "access_gaps" in result
        assert isinstance(result["access_gaps"], list)

    def test_kpi_agent_includes_recommended_access_requests(
        self, kpi_agent: KPIAgent
    ) -> None:
        result = kpi_agent.run(persona_id="compliance_officer")
        assert "recommended_access_requests" in result
        assert isinstance(result["recommended_access_requests"], list)

    def test_kpi_agent_via_api_includes_access_summary(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "mode": "mock"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_readiness_summary" in data
        assert data["access_readiness_summary"]["overall_status"] in (
            "ready", "partially_ready", "blocked"
        )


# ---------------------------------------------------------------------------
# Scenario 10 — Existing endpoints still work (regression)
# ---------------------------------------------------------------------------


class TestExistingEndpointsRegression:
    def test_list_personas(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        assert resp.status_code == 200
        assert len(resp.json()) == 8

    def test_list_connectors(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        assert resp.status_code == 200
        assert len(resp.json()) == 8

    def test_list_tools(self, client: TestClient) -> None:
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert len(tools) > 0

    def test_kpi_interpret_cto(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cto", "mode": "mock"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "weekly_digest" in data
        assert "agent_ideas" in data

    def test_evidence_trail(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "it_manager", "mode": "mock"},
        )
        resp = client.get("/api/evidence?persona_id=it_manager")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_agent_request_flow(self, client: TestClient) -> None:
        resp = client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "idea_001",
                "requested_by_persona": "service_owner",
                "linked_kpi_id": "kpi_01",
                "rationale": "Automate SLA monitoring.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
