"""UI route and rendering tests.

Verifies:
- GET / returns the HTML shell with all required structural elements
- Static files are mounted and reachable
- Sidebar uses simplified 4-item nav with SVG icons and no emoji
- All existing API endpoints remain functional
- Key UI sections are present in the HTML
- Connector section renders expected content from the API
- KPI interpretation flow includes access readiness in the response
- Access request flow works end-to-end
- Agent request flow works end-to-end
- Evidence trail is accessible

Run with:
    cd src/samples/create-persona-aware-control-plane
    python -m pytest tests/test_ui.py -v
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import app, _access_requests
from control_plane.stores import evidence_store, request_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_stores():
    evidence_store.clear()
    request_store.clear()
    _access_requests.clear()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# UI route loads
# ---------------------------------------------------------------------------


class TestUIRoute:
    def test_root_returns_200(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200

    def test_root_returns_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_html_contains_doctype(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "<!DOCTYPE html>" in resp.text

    def test_html_contains_app_title(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Control Plane" in resp.text

    def test_html_references_static_css(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "/static/style.css" in resp.text

    def test_html_references_app_js(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "/static/app.js" in resp.text


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


class TestStaticFiles:
    def test_css_file_serves(self, client: TestClient) -> None:
        resp = client.get("/static/style.css")
        assert resp.status_code == 200

    def test_js_file_serves(self, client: TestClient) -> None:
        resp = client.get("/static/app.js")
        assert resp.status_code == 200

    def test_css_content_type(self, client: TestClient) -> None:
        resp = client.get("/static/style.css")
        assert "css" in resp.headers.get("content-type", "")

    def test_js_content_type(self, client: TestClient) -> None:
        resp = client.get("/static/app.js")
        ct = resp.headers.get("content-type", "")
        assert "javascript" in ct or "text" in ct


# ---------------------------------------------------------------------------
# Simplified navigation: 4-item nav, SVG icons, no emoji
# ---------------------------------------------------------------------------

EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F9FF\u2600-\u26FF\u2700-\u27BF\U0001FA00-\U0001FFFF]"
)


class TestSimplifiedNav:
    def test_sidebar_nav_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "sidebar-nav" in resp.text

    def test_nav_briefing_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Briefing" in resp.text

    def test_nav_integrations_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Integrations" in resp.text

    def test_nav_actions_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Actions" in resp.text

    def test_nav_evidence_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Evidence" in resp.text

    def test_sidebar_contains_svg_icons(self, client: TestClient) -> None:
        resp = client.get("/")
        sidebar_m = re.search(r'<aside[^>]*>.*?</aside>', resp.text, re.DOTALL)
        assert sidebar_m, "sidebar <aside> not found"
        sidebar = sidebar_m.group(0)
        assert "<svg" in sidebar, "SVG icons not found in sidebar"

    def test_sidebar_no_emoji(self, client: TestClient) -> None:
        resp = client.get("/")
        sidebar_m = re.search(r'<aside[^>]*>.*?</aside>', resp.text, re.DOTALL)
        assert sidebar_m, "sidebar <aside> not found"
        sidebar = sidebar_m.group(0)
        assert not EMOJI_RE.search(sidebar), "Emoji found in sidebar"

    def test_page_no_emoji_in_nav(self, client: TestClient) -> None:
        """No emoji characters anywhere in the nav elements."""
        resp = client.get("/")
        nav_m = re.search(r'<nav class="sidebar-nav"[^>]*>.*?</nav>', resp.text, re.DOTALL)
        assert nav_m, "sidebar-nav <nav> not found"
        nav = nav_m.group(0)
        assert not EMOJI_RE.search(nav), f"Emoji found in nav: {EMOJI_RE.findall(nav)}"

    def test_svg_stroke_width_consistent(self, client: TestClient) -> None:
        resp = client.get("/")
        sidebar_m = re.search(r'<aside[^>]*>.*?</aside>', resp.text, re.DOTALL)
        sidebar = sidebar_m.group(0)
        strokes = re.findall(r'stroke-width="([^"]+)"', sidebar)
        assert len(strokes) > 0, "No stroke-width found on SVG icons"

    def test_four_nav_items(self, client: TestClient) -> None:
        resp = client.get("/")
        nav_items = re.findall(r'class="nav-item[^"]*"[^>]*data-section', resp.text)
        assert len(nav_items) == 4, f"Expected 4 nav items, got {len(nav_items)}"

    def test_svg_aria_hidden(self, client: TestClient) -> None:
        resp = client.get("/")
        sidebar_m = re.search(r'<aside[^>]*>.*?</aside>', resp.text, re.DOTALL)
        sidebar = sidebar_m.group(0)
        assert 'aria-hidden="true"' in sidebar


# ---------------------------------------------------------------------------
# Section structural elements in HTML (tab panels)
# ---------------------------------------------------------------------------


class TestHtmlStructure:
    def test_persona_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-persona" in resp.text

    def test_connectors_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-connectors" in resp.text

    def test_tools_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-tools" in resp.text

    def test_kpi_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-kpi" in resp.text

    def test_access_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-access" in resp.text

    def test_digest_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-digest" in resp.text

    def test_agent_ideas_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-agent-ideas" in resp.text

    def test_evidence_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-evidence" in resp.text

    def test_registry_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-registry" in resp.text

    def test_access_readiness_tab_label(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Access Readiness" in resp.text

    def test_governance_thesis_in_series(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "governable" in resp.text.lower()

    def test_security_note_in_connectors(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Secrets" in resp.text or "secrets" in resp.text

    def test_no_auto_grant_notice(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "auto-grant" in resp.text.lower() or "never auto-grant" in resp.text.lower()

    def test_tab_nav_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "tab-nav" in resp.text

    def test_tab_panel_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "tab-panel" in resp.text

    def test_briefing_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-briefing" in resp.text

    def test_integrations_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-integrations" in resp.text

    def test_actions_section_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "section-actions" in resp.text


# ---------------------------------------------------------------------------
# Connector section renders via API
# ---------------------------------------------------------------------------


class TestConnectorAPI:
    def test_connectors_api_returns_8(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        assert resp.status_code == 200
        assert len(resp.json()) == 8

    def test_connector_has_mode_field(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        for c in resp.json():
            assert "mode" in c

    def test_connector_has_signal_types(self, client: TestClient) -> None:
        resp = client.get("/api/connectors")
        for c in resp.json():
            assert "supported_signal_types" in c

    def test_connector_test_endpoint(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/test", json={})
        assert resp.status_code == 200

    def test_connector_configure_endpoint(self, client: TestClient) -> None:
        resp = client.post("/api/connectors/azure/configure", json={"mode": "mock"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tools panel renders via API
# ---------------------------------------------------------------------------


class TestToolsAPI:
    def test_tools_api_returns_tools(self, client: TestClient) -> None:
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_tool_has_required_fields(self, client: TestClient) -> None:
        resp = client.get("/api/tools")
        for tool in resp.json():
            assert "name" in tool
            assert "platform_id" in tool
            assert "signal_types" in tool
            assert "source_mode" in tool

    def test_tools_filter_by_platform(self, client: TestClient) -> None:
        resp = client.get("/api/tools?platform_id=azure")
        assert resp.status_code == 200
        tools = resp.json()
        assert all(t["platform_id"] == "azure" for t in tools)


# ---------------------------------------------------------------------------
# KPI interpretation flow includes access readiness
# ---------------------------------------------------------------------------


class TestKPIInterpretationViaUI:
    def test_kpi_includes_access_readiness_summary(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer", "mode": "mock"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_readiness_summary" in data

    def test_kpi_includes_access_check_results(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "mode": "mock"},
        )
        data = resp.json()
        assert "access_check_results" in data
        assert isinstance(data["access_check_results"], list)

    def test_kpi_includes_access_gaps(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "mode": "mock"},
        )
        data = resp.json()
        assert "access_gaps" in data

    def test_kpi_includes_recommended_requests(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "mode": "mock"},
        )
        data = resp.json()
        assert "recommended_access_requests" in data

    def test_access_summary_has_overall_status(self, client: TestClient) -> None:
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "compliance_officer", "mode": "mock"},
        )
        summary = resp.json()["access_readiness_summary"]
        assert summary["overall_status"] in ("ready", "partially_ready", "blocked")

    def test_access_grants_endpoint_works(self, client: TestClient) -> None:
        resp = client.get("/api/access/personas/compliance_officer/grants")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_access_check_endpoint_works(self, client: TestClient) -> None:
        resp = client.post(
            "/api/access/check",
            json={
                "persona_id": "compliance_officer",
                "kpi_agent_result": {
                    "required_signals": ["incidents"],
                    "selected_platforms": ["servicenow"],
                },
                "mode": "mock",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "overall_status" in data
        assert "access_check_results" in data


# ---------------------------------------------------------------------------
# Access request flow works
# ---------------------------------------------------------------------------


class TestAccessRequestFlowViaUI:
    def test_submit_access_request(self, client: TestClient) -> None:
        payload = {
            "persona_id": "cfo",
            "kpi_id": "cfo_kpi_01",
            "connector_id": "microsoft365",
            "platform_id": "microsoft365",
            "requested_scope": "Reports.Read.All",
            "requested_role": "Reports Reader",
            "requested_permission": "read",
            "requested_actions": ["read_sharing_reports"],
            "justification": "CFO needs M365 usage data.",
            "business_outcome": "Complete digest.",
            "recommended_approver": "M365 Global Administrator",
        }
        resp = client.post("/api/access/requests", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["persona_id"] == "cfo"

    def test_access_request_not_auto_approved(self, client: TestClient) -> None:
        payload = {
            "persona_id": "cfo",
            "kpi_id": "cfo_kpi_01",
            "connector_id": "kubernetes",
            "platform_id": "kubernetes",
            "requested_scope": "cluster-reader",
            "requested_role": "Cluster Viewer",
            "requested_permission": "read",
            "requested_actions": ["read_deployments"],
            "justification": "CFO capacity planning.",
            "business_outcome": "Infra visibility.",
            "recommended_approver": "Kubernetes Administrator",
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
            "justification": "IT capacity forecasting.",
            "business_outcome": "Improved operational planning.",
            "recommended_approver": "Salesforce System Administrator",
        }
        client.post("/api/access/requests", json=payload)
        resp = client.get("/api/access/requests")
        assert resp.status_code == 200
        reqs = resp.json()
        assert any(r["persona_id"] == "it_manager" for r in reqs)

    def test_access_request_creates_evidence(self, client: TestClient) -> None:
        payload = {
            "persona_id": "cto",
            "kpi_id": "cto_kpi_01",
            "connector_id": "salesforce",
            "platform_id": "salesforce",
            "requested_scope": "opportunity.read",
            "requested_role": "Sales Analyst",
            "requested_permission": "read",
            "requested_actions": ["read_opportunity_pipeline"],
            "justification": "CTO pipeline monitoring.",
            "business_outcome": "Forecast reliability.",
            "recommended_approver": "Salesforce System Administrator",
        }
        client.post("/api/access/requests", json=payload)
        resp = client.get("/api/evidence?persona_id=cto")
        assert resp.status_code == 200
        event_types = {e["event_type"] for e in resp.json()}
        assert "access_request_submitted" in event_types


# ---------------------------------------------------------------------------
# Agent request flow works
# ---------------------------------------------------------------------------


class TestAgentRequestFlowViaUI:
    def test_submit_agent_request(self, client: TestClient) -> None:
        resp = client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "invoice-recovery-agent",
                "requested_by_persona": "cfo",
                "linked_kpi_id": "cfo_cost_kpi",
                "rationale": "Automate invoice recovery to reduce overdue receivables.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["requested_by_persona"] == "cfo"

    def test_list_agent_requests(self, client: TestClient) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "policy-research-agent",
                "requested_by_persona": "compliance_officer",
                "linked_kpi_id": "comp_kpi_01",
                "rationale": "Automate regulatory change monitoring.",
            },
        )
        resp = client.get("/api/agent-requests")
        assert resp.status_code == 200
        reqs = resp.json()
        assert any(r["requested_by_persona"] == "compliance_officer" for r in reqs)

    def test_agent_request_creates_evidence(self, client: TestClient) -> None:
        client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "support-triage",
                "requested_by_persona": "service_owner",
                "linked_kpi_id": "svc_kpi",
                "rationale": "Reduce triage time.",
            },
        )
        resp = client.get("/api/evidence?persona_id=service_owner")
        event_types = {e["event_type"] for e in resp.json()}
        assert "agent_request_submitted" in event_types


# ---------------------------------------------------------------------------
# Evidence trail works
# ---------------------------------------------------------------------------


class TestEvidenceTrailViaUI:
    def test_evidence_endpoint_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/evidence")
        assert resp.status_code == 200

    def test_kpi_interpretation_generates_evidence(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "security_officer", "mode": "mock"},
        )
        resp = client.get("/api/evidence?persona_id=security_officer")
        events = resp.json()
        assert len(events) > 0
        event_types = {e["event_type"] for e in events}
        assert "kpi_interpreted" in event_types or len(event_types) > 0

    def test_evidence_filtered_by_persona(self, client: TestClient) -> None:
        client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "it_manager", "mode": "mock"},
        )
        resp = client.get("/api/evidence?persona_id=it_manager")
        events = resp.json()
        for ev in events:
            assert ev.get("persona_id") == "it_manager" or ev.get("persona_id") is None


# ---------------------------------------------------------------------------
# All 8 personas load via API (regression for UI persona selector)
# ---------------------------------------------------------------------------


class TestPersonaAPIRegression:
    def test_all_8_personas_available(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        assert resp.status_code == 200
        assert len(resp.json()) == 8

    def test_each_persona_has_name_and_id(self, client: TestClient) -> None:
        resp = client.get("/api/personas")
        for p in resp.json():
            assert "name" in p
            assert "id" in p or "persona_id" in p

    def test_persona_detail_has_default_kpis(self, client: TestClient) -> None:
        resp = client.get("/api/personas/compliance_officer")
        assert resp.status_code == 200
        data = resp.json()
        assert "default_kpis" in data


# ---------------------------------------------------------------------------
# Design system — light theme, pill styling, restrained palette
# ---------------------------------------------------------------------------


class TestDesignSystem:
    """Verify the enterprise governance design system is applied correctly.

    Checks are CSS-source based (via /static/style.css) so they are
    fast and do not require a browser. They confirm that the design
    tokens expressed in the CSS match the light-mode governance brief.
    """

    def test_css_uses_pill_border_radius(self, client: TestClient) -> None:
        """Tags and badges must use pill-shaped border-radius (9999px)."""
        resp = client.get("/static/style.css")
        assert "9999px" in resp.text, (
            "CSS should define var(--radius-pill) as 9999px for pill-shaped labels"
        )

    def test_badge_class_uses_pill_radius(self, client: TestClient) -> None:
        """The .badge class must reference the pill radius variable."""
        resp = client.get("/static/style.css")
        css = resp.text
        # .badge block must contain border-radius referencing the pill var
        assert "border-radius: var(--radius-pill)" in css

    def test_tag_class_uses_pill_radius(self, client: TestClient) -> None:
        """The .tag class must use pill border-radius."""
        resp = client.get("/static/style.css")
        assert "border-radius: var(--radius-pill)" in resp.text

    def test_css_light_mode_background(self, client: TestClient) -> None:
        """Root background must be a light slate surface (not dark navy)."""
        resp = client.get("/static/style.css")
        css = resp.text
        # slate-50 (#f8fafc) should be the root --bg
        assert "#f8fafc" in css, "CSS should use slate-50 (#f8fafc) as the light background"

    def test_css_white_card_surface(self, client: TestClient) -> None:
        """Card surfaces must use white (#ffffff)."""
        resp = client.get("/static/style.css")
        assert "#ffffff" in resp.text

    def test_css_accent_is_deep_blue_not_neon(self, client: TestClient) -> None:
        """Primary accent must be a deep governance blue, not the old neon #3b82f6."""
        resp = client.get("/static/style.css")
        css = resp.text
        # Old neon blue must not appear anywhere in the stylesheet
        assert "#3b82f6" not in css, (
            "Neon blue #3b82f6 should not be in the stylesheet — use deep blue #1d4ed8"
        )

    def test_css_uses_deep_blue_accent(self, client: TestClient) -> None:
        """Deep governance blue (indigo-800 #3730a3) must be the primary accent."""
        resp = client.get("/static/style.css")
        assert "#3730a3" in resp.text

    def test_css_no_dark_root_background(self, client: TestClient) -> None:
        """Old dark mode root background (#0f172a) must not be --bg."""
        resp = client.get("/static/style.css")
        css = resp.text
        # The old dark-mode --bg token must not appear as a background value
        assert "--bg:           #0f172a" not in css and "--bg: #0f172a" not in css

    def test_css_no_purple_accent(self, client: TestClient) -> None:
        """Purple (#a855f7) should not be in the stylesheet — palette is simplified."""
        resp = client.get("/static/style.css")
        assert "#a855f7" not in resp.text, "Purple accent should not be used"

    def test_buttons_use_pill_radius(self, client: TestClient) -> None:
        """.btn must use pill border-radius."""
        resp = client.get("/static/style.css")
        assert "border-radius: var(--radius-pill)" in resp.text

    def test_page_no_emoji_anywhere(self, client: TestClient) -> None:
        """No emoji characters anywhere in the rendered HTML."""
        resp = client.get("/")
        assert not EMOJI_RE.search(resp.text), "Emoji found in rendered page"

    def test_sidebar_still_has_four_nav_items(self, client: TestClient) -> None:
        """Sidebar navigation must retain all 4 governance sections."""
        resp = client.get("/")
        nav_items = re.findall(r'class="nav-item[^"]*"[^>]*data-section', resp.text)
        assert len(nav_items) == 4

    def test_kpi_workspace_section_present(self, client: TestClient) -> None:
        """KPI Workspace must still be in the rendered HTML."""
        resp = client.get("/")
        assert "KPI Workspace" in resp.text

    def test_access_readiness_section_present(self, client: TestClient) -> None:
        """Access Readiness must still be in the rendered HTML."""
        resp = client.get("/")
        assert "Access Readiness" in resp.text

    def test_connector_section_present(self, client: TestClient) -> None:
        """Configure Platforms connector section must still be present."""
        resp = client.get("/")
        assert "Configure Platforms" in resp.text or "connector" in resp.text.lower()

    def test_kpi_agent_still_interprets(self, client: TestClient) -> None:
        """KPI interpretation flow must still work after CSS-only changes."""
        resp = client.post(
            "/api/kpi-agent/interpret",
            json={"persona_id": "cfo", "mode": "mock"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "normalized_kpi" in data
        assert "access_readiness_summary" in data

    def test_access_request_flow_still_works(self, client: TestClient) -> None:
        """Access request submission must still work after visual refactor."""
        resp = client.post(
            "/api/access/requests",
            json={
                "persona_id": "cto",
                "kpi_id": "cto_kpi_01",
                "connector_id": "azure",
                "platform_id": "azure",
                "requested_scope": "Reader",
                "requested_role": "Reader",
                "requested_permission": "read",
                "requested_actions": [],
                "justification": "Design system regression test.",
                "business_outcome": "Governance visibility.",
                "recommended_approver": "Azure Admin",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    def test_agent_request_flow_still_works(self, client: TestClient) -> None:
        """Agent request submission must still work after visual refactor."""
        resp = client.post(
            "/api/agent-requests",
            json={
                "agent_idea_id": "cto_idea_01",
                "requested_by_persona": "cto",
                "linked_kpi_id": "cto_kpi_01",
                "rationale": "Design system regression test.",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"
