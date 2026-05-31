"""Tests for the KPI refinement workflow.

Covers:
1. KPI challenge endpoint — basic response shape.
2. Persona-specific challenge questions for CFO.
3. KPI formalization endpoint.
4. Control package endpoint.
5. Control package contains what_you_get.
6. Control package contains what_you_need.
7. Access readiness is included only in control package (after formalization).
8. UI route contains KPI stepper elements.
9. UI does not expose full control package before KPI formalization step.
10. Existing tests are not broken (implicit — the fixture clears stores).

Run with:
    cd src/samples/create-persona-aware-control-plane
    python -m pytest tests/test_kpi_refinement.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import app
from control_plane.stores import evidence_store, request_store


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_stores():
    evidence_store.clear()
    request_store.clear()
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CFO_DRAFT = "Agent ROI > 3x"
CFO_PERSONA = "cfo"


def _challenge(client, persona_id=CFO_PERSONA, draft_kpi=CFO_DRAFT):
    return client.post("/api/kpi-agent/challenge", json={
        "persona_id": persona_id,
        "draft_kpi": draft_kpi,
    })


def _formalize(client, session_id, persona_id=CFO_PERSONA, draft_kpi=CFO_DRAFT, answers=None):
    return client.post("/api/kpi-agent/formalize", json={
        "session_id": session_id,
        "persona_id": persona_id,
        "draft_kpi": draft_kpi,
        "answers": answers or {
            "business_outcome": "Demonstrate 3x ROI for funded agent initiatives",
            "timeframe": "Rolling quarter",
            "scope": "All production agent initiatives",
            "evidence_standard": "80% value confidence minimum",
        },
    })


def _control_package(client, formalized_kpi, persona_id=CFO_PERSONA):
    return client.post("/api/kpi-agent/control-package", json={
        "persona_id": persona_id,
        "formalized_kpi": formalized_kpi,
        "mode": "mock",
    })


# ---------------------------------------------------------------------------
# 1. KPI challenge endpoint — basic response shape
# ---------------------------------------------------------------------------


class TestKpiChallengeEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert resp.status_code == 200

    def test_unknown_persona_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/kpi-agent/challenge", json={
            "persona_id": "__unknown__",
            "draft_kpi": "Agent ROI > 3x",
        })
        assert resp.status_code == 404

    def test_response_has_session_id(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert "session_id" in resp.json()

    def test_response_has_maturity_level(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert "maturity_level" in resp.json()
        assert resp.json()["maturity_level"] in (
            "vague", "usable", "well_articulated", "control_ready"
        )

    def test_response_has_challenge_questions(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert "challenge_questions" in resp.json()
        assert isinstance(resp.json()["challenge_questions"], list)

    def test_response_has_missing_fields(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert "missing_fields" in resp.json()

    def test_response_has_confidence_score(self, client: TestClient) -> None:
        resp = _challenge(client)
        data = resp.json()
        assert "confidence_score" in data
        assert 0.0 <= data["confidence_score"] <= 1.0

    def test_response_has_suggested_formalized_kpi(self, client: TestClient) -> None:
        resp = _challenge(client)
        assert "suggested_formalized_kpi" in resp.json()

    def test_evidence_events_written(self, client: TestClient) -> None:
        _challenge(client)
        events = client.get("/api/evidence?persona_id=cfo").json()
        event_types = [e["event_type"] for e in events]
        assert "kpi_challenge_started" in event_types


# ---------------------------------------------------------------------------
# 2. Persona-specific challenge questions for CFO
# ---------------------------------------------------------------------------


class TestCfoChallengeQuestions:
    def test_cfo_receives_challenge_questions(self, client: TestClient) -> None:
        resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        questions = resp.json()["challenge_questions"]
        assert len(questions) > 0

    def test_cfo_questions_mention_roi(self, client: TestClient) -> None:
        resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        questions_text = " ".join(resp.json()["challenge_questions"]).lower()
        assert any(kw in questions_text for kw in ("roi", "cost", "value", "outcome", "spend"))

    def test_cfo_questions_differ_from_compliance_officer(self, client: TestClient) -> None:
        cfo_resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        comp_resp = _challenge(client, persona_id="compliance_officer", draft_kpi="Improve audit readiness")
        cfo_q = set(cfo_resp.json()["challenge_questions"])
        comp_q = set(comp_resp.json()["challenge_questions"])
        assert cfo_q != comp_q

    def test_cfo_draft_roi_maturity_not_control_ready(self, client: TestClient) -> None:
        resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        assert resp.json()["maturity_level"] != "control_ready"

    def test_cfo_suggested_kpi_mentions_roi(self, client: TestClient) -> None:
        resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        suggested = resp.json()["suggested_formalized_kpi"]
        text = str(suggested).lower()
        assert any(kw in text for kw in ("roi", "cost", "value", "investment"))


# ---------------------------------------------------------------------------
# 3. KPI formalization endpoint
# ---------------------------------------------------------------------------


class TestKpiFormalizationEndpoint:
    def test_returns_200(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        assert resp.status_code == 200

    def test_unknown_persona_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/kpi-agent/formalize", json={
            "session_id": "fake-session",
            "persona_id": "__unknown__",
            "draft_kpi": "Agent ROI > 3x",
            "answers": {},
        })
        assert resp.status_code == 404

    def test_response_has_formalized_kpi(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        assert "formalized_kpi" in resp.json()

    def test_formalized_kpi_has_required_fields(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        kpi = resp.json()["formalized_kpi"]
        for field in ("id", "persona_id", "title", "outcome_statement", "metric",
                      "target", "timeframe", "scope", "evidence_standard",
                      "risk_tolerance", "success_criteria", "confidence_score"):
            assert field in kpi, f"formalized_kpi missing field: {field}"

    def test_formalized_kpi_confidence_increases_with_answers(self, client: TestClient) -> None:
        sess = _challenge(client).json()
        bare_resp = client.post("/api/kpi-agent/formalize", json={
            "session_id": sess["session_id"],
            "persona_id": "cfo",
            "draft_kpi": "Agent ROI > 3x",
            "answers": {},
        })
        sess2 = _challenge(client).json()
        answered_resp = _formalize(client, sess2["session_id"])
        assert answered_resp.json()["confidence_score"] >= bare_resp.json()["confidence_score"]

    def test_response_has_maturity_level(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        assert "maturity_level" in resp.json()

    def test_response_has_remaining_questions(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        assert "remaining_questions" in resp.json()

    def test_formalized_kpi_evidence_written(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        _formalize(client, session_id)
        events = client.get("/api/evidence?persona_id=cfo").json()
        event_types = [e["event_type"] for e in events]
        assert "kpi_formalized" in event_types


# ---------------------------------------------------------------------------
# 4. Control package endpoint
# ---------------------------------------------------------------------------


class TestControlPackageEndpoint:
    def _get_formalized(self, client: TestClient):
        session_id = _challenge(client).json()["session_id"]
        return _formalize(client, session_id).json()["formalized_kpi"]

    def test_returns_200(self, client: TestClient) -> None:
        fkpi = self._get_formalized(client)
        resp = _control_package(client, fkpi)
        assert resp.status_code == 200

    def test_unknown_persona_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/kpi-agent/control-package", json={
            "persona_id": "__unknown__",
            "formalized_kpi": {"title": "Test"},
        })
        assert resp.status_code == 404

    def test_response_has_control_package_key(self, client: TestClient) -> None:
        fkpi = self._get_formalized(client)
        resp = _control_package(client, fkpi)
        assert "control_package" in resp.json()

    def test_control_package_has_required_keys(self, client: TestClient) -> None:
        fkpi = self._get_formalized(client)
        pkg = _control_package(client, fkpi).json()["control_package"]
        for key in (
            "id", "formalized_kpi_id", "persona_id",
            "what_you_get", "what_you_need",
            "required_signals", "required_connectors", "required_tools",
            "required_access", "required_evidence",
            "access_readiness_summary", "connector_readiness_summary",
            "recommended_actions", "agent_ideas",
            "evidence_events", "limitations", "confidence_score",
        ):
            assert key in pkg, f"control_package missing key: {key}"


# ---------------------------------------------------------------------------
# 5. Control package contains what_you_get
# ---------------------------------------------------------------------------


class TestControlPackageWhatYouGet:
    def test_what_you_get_is_non_empty_list(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        assert isinstance(pkg["what_you_get"], list)
        assert len(pkg["what_you_get"]) > 0

    def test_cfo_what_you_get_mentions_roi(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        pkg = _control_package(client, fkpi, persona_id="cfo").json()["control_package"]
        text = " ".join(pkg["what_you_get"]).lower()
        assert any(kw in text for kw in ("roi", "cost", "value", "invest"))

    def test_what_you_get_items_are_strings(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        for item in pkg["what_you_get"]:
            assert isinstance(item, str), f"what_you_get item is not a string: {item!r}"


# ---------------------------------------------------------------------------
# 6. Control package contains what_you_need
# ---------------------------------------------------------------------------


class TestControlPackageWhatYouNeed:
    def test_what_you_need_is_non_empty_list(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        assert isinstance(pkg["what_you_need"], list)
        assert len(pkg["what_you_need"]) > 0

    def test_cfo_what_you_need_mentions_azure_or_foundry(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        pkg = _control_package(client, fkpi, persona_id="cfo").json()["control_package"]
        text = " ".join(pkg["what_you_need"]).lower()
        assert any(kw in text for kw in ("azure", "foundry", "salesforce", "cost"))

    def test_what_you_need_items_are_strings(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        for item in pkg["what_you_need"]:
            assert isinstance(item, str), f"what_you_need item is not a string: {item!r}"


# ---------------------------------------------------------------------------
# 7. Access readiness is included only after formalization / control package
# ---------------------------------------------------------------------------


class TestAccessReadinessAfterFormalization:
    def test_challenge_does_not_return_access_data(self, client: TestClient) -> None:
        resp = _challenge(client)
        data = resp.json()
        # Challenge should NOT contain access_readiness_summary or access_gaps
        assert "access_readiness_summary" not in data
        assert "access_gaps" not in data
        assert "required_connectors" not in data

    def test_formalize_does_not_return_access_data(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        resp = _formalize(client, session_id)
        data = resp.json()
        assert "access_readiness_summary" not in data
        assert "access_gaps" not in data

    def test_control_package_contains_access_readiness_summary(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        summary = pkg.get("access_readiness_summary", {})
        assert isinstance(summary, dict)
        assert "overall_status" in summary

    def test_control_package_contains_connector_readiness(self, client: TestClient) -> None:
        session_id = _challenge(client).json()["session_id"]
        fkpi = _formalize(client, session_id).json()["formalized_kpi"]
        pkg = _control_package(client, fkpi).json()["control_package"]
        assert isinstance(pkg.get("connector_readiness_summary"), dict)


# ---------------------------------------------------------------------------
# 8. UI route contains the KPI stepper
# ---------------------------------------------------------------------------


class TestUiKpiStepper:
    def test_kpi_stepper_present_in_html(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-stepper" in resp.text

    def test_stepper_has_5_steps(self, client: TestClient) -> None:
        import re
        resp = client.get("/")
        steps = re.findall(r'data-step="(\d)"', resp.text)
        assert len(steps) == 5, f"Expected 5 stepper steps, found {len(steps)}"

    def test_step_1_draft_kpi_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-step-1" in resp.text
        assert "kpi-draft-input" in resp.text

    def test_step_2_challenge_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-step-2" in resp.text
        assert "kpi-formalize-btn" in resp.text

    def test_step_3_formalized_kpi_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-step-3" in resp.text
        assert "formalized-kpi-card" in resp.text

    def test_step_4_control_package_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-step-4" in resp.text
        assert "control-package-content" in resp.text

    def test_step_5_actions_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-step-5" in resp.text
        assert "kpi-actions-content" in resp.text

    def test_challenge_btn_present(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "kpi-challenge-btn" in resp.text

    def test_stepper_labels_present(self, client: TestClient) -> None:
        resp = client.get("/")
        for label in ("Draft KPI", "Challenge", "Formalized KPI", "Control Package", "Actions"):
            assert label in resp.text, f"Stepper label missing: {label}"


# ---------------------------------------------------------------------------
# 9. UI does not show full control package before KPI formalization
# ---------------------------------------------------------------------------


class TestUiControlPackageGating:
    def test_control_package_not_visible_on_load(self, client: TestClient) -> None:
        resp = client.get("/")
        # Step 4 must be hidden by default (CSS class 'hidden' or not 'active')
        import re
        # kpi-step-4 div should not have class 'active' in the initial HTML
        step4_match = re.search(
            r'id="kpi-step-4"([^>]*>)',
            resp.text,
        )
        assert step4_match, "kpi-step-4 element not found"
        attrs = step4_match.group(1)
        assert "hidden" in attrs or "active" not in attrs, (
            "kpi-step-4 should not be active on initial page load"
        )

    def test_control_package_step_does_not_render_data_without_api_call(
        self, client: TestClient
    ) -> None:
        resp = client.get("/")
        # The control-package-content div should be empty in static HTML
        import re
        match = re.search(
            r'id="control-package-content"[^>]*>(.*?)</div>',
            resp.text,
            re.DOTALL,
        )
        if match:
            content = match.group(1).strip()
            assert content == "", f"control-package-content should be empty on load, got: {content!r}"

    def test_step_1_is_active_on_load(self, client: TestClient) -> None:
        import re
        resp = client.get("/")
        step1_match = re.search(r'id="kpi-step-1"([^>]*>)', resp.text)
        assert step1_match, "kpi-step-1 not found"
        attrs = step1_match.group(1)
        assert "active" in attrs


# ---------------------------------------------------------------------------
# 10. CFO Agent ROI > 3x end-to-end scenario
# ---------------------------------------------------------------------------


class TestCfoRoiScenarioEndToEnd:
    def test_challenge_cfo_roi_kpi(self, client: TestClient) -> None:
        resp = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        assert resp.status_code == 200
        assert resp.json()["persona_id"] == "cfo"

    def test_formalize_cfo_roi_kpi(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x").json()["session_id"]
        resp = _formalize(client, session_id, persona_id="cfo", draft_kpi="Agent ROI > 3x")
        assert resp.status_code == 200
        kpi = resp.json()["formalized_kpi"]
        assert kpi["persona_id"] == "cfo"

    def test_control_package_cfo_roi(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        resp = _control_package(client, fkpi, persona_id="cfo")
        assert resp.status_code == 200
        pkg = resp.json()["control_package"]
        assert pkg["persona_id"] == "cfo"
        assert len(pkg["what_you_get"]) > 0
        assert len(pkg["what_you_need"]) > 0

    def test_cfo_control_package_has_required_access(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        pkg = _control_package(client, fkpi, persona_id="cfo").json()["control_package"]
        assert isinstance(pkg["required_access"], list)

    def test_cfo_control_package_evidence_events_written(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        _control_package(client, fkpi, persona_id="cfo")
        events = client.get("/api/evidence?persona_id=cfo").json()
        event_types = [e["event_type"] for e in events]
        assert "control_package_composed" in event_types

    def test_cfo_full_workflow_evidence_trail(self, client: TestClient) -> None:
        session_id = _challenge(client, persona_id="cfo", draft_kpi="Agent ROI > 3x").json()["session_id"]
        fkpi = _formalize(client, session_id, persona_id="cfo").json()["formalized_kpi"]
        _control_package(client, fkpi, persona_id="cfo")
        events = client.get("/api/evidence?persona_id=cfo").json()
        event_types = set(e["event_type"] for e in events)
        for expected in (
            "kpi_challenge_started",
            "kpi_questions_generated",
            "kpi_formalized",
            "required_signals_identified",
            "control_package_composed",
        ):
            assert expected in event_types, f"Missing evidence event: {expected}"
