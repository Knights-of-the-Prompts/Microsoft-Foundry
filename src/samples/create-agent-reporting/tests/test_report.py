"""
Unit tests for report/report.py

Tests cover:
  - evaluate_risks() threshold logic
  - generate_recommended_actions() risk actions, profile completeness, Advisor items
  - load_agent_profile() happy path and missing file
  - fetch_governance() no GUID, 403 fallback, 200 Graph override

No Azure credentials required — API calls are fully mocked.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Ensure env vars are set before importing report (report reads them at import time)
os.environ.setdefault("AZURE_SUBSCRIPTION_ID", "test-sub")
os.environ.setdefault("AZURE_RESOURCE_GROUP_NAME", "test-rg")
os.environ.setdefault("AI_SERVICES_NAME", "test-ai")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "report"))

from report import (
    evaluate_risks,
    fetch_governance,
    generate_recommended_actions,
    load_agent_profile,
)


# ── evaluate_risks ────────────────────────────────────────────────────────────

class TestEvaluateRisks:

    def _clean_usage(self, **overrides) -> dict:
        base = {"total": 50, "success": 50, "errors": 0, "error_rate": 0.0, "tokens": 5000}
        base.update(overrides)
        return base

    def _clean_cost(self, **overrides) -> dict:
        base = {"amount": 2.0, "currency": "USD"}
        base.update(overrides)
        return base

    def test_high_error_rate_triggers_risk(self):
        usage = self._clean_usage(total=100, errors=10, error_rate=0.10)
        risks = evaluate_risks(usage, self._clean_cost())
        assert any("error rate" in r.lower() for r in risks)

    def test_cost_over_threshold_triggers_risk(self):
        risks = evaluate_risks(self._clean_usage(), self._clean_cost(amount=50.0))
        assert any("cost alert" in r.lower() for r in risks)

    def test_idle_agent_triggers_risk(self):
        usage = self._clean_usage(total=0, success=0, errors=0, error_rate=0.0, tokens=0)
        risks = evaluate_risks(usage, self._clean_cost(amount=0.0))
        assert any("idle" in r.lower() for r in risks)

    def test_no_risks_when_all_clean(self):
        assert evaluate_risks(self._clean_usage(), self._clean_cost()) == []

    def test_usage_error_returns_empty(self):
        assert evaluate_risks({"error": "connection failed"}, self._clean_cost()) == []

    def test_cost_error_returns_empty(self):
        assert evaluate_risks(self._clean_usage(), {"error": "api error"}) == []

    def test_multiple_risks_returned(self):
        usage = self._clean_usage(total=100, errors=20, error_rate=0.20)
        cost  = {"amount": 50.0, "currency": "USD"}
        risks = evaluate_risks(usage, cost)
        assert len(risks) >= 2


# ── generate_recommended_actions ─────────────────────────────────────────────

class TestGenerateRecommendedActions:

    def _full_profile(self) -> dict:
        return {
            "business_stream": "IT Operations",
            "efficiency_value_description": "~15 min saved per ticket",
            "outcome_value_description": "30% reduction in manual handling",
            "outcome_description": "Reduces ticket resolution time",
        }

    def test_error_rate_risk_produces_owner_action(self):
        risks = ["High error rate: 10.0% exceeds threshold 5.0%"]
        actions = generate_recommended_actions(
            risks, [], self._full_profile(), {"owner": "owner@contoso.com"}
        )
        assert any("error rate" in a.lower() for a in actions)
        assert any("owner@contoso.com" in a for a in actions)

    def test_cost_alert_risk_produces_finops_action(self):
        risks = ["Cost alert: 50.00 USD exceeds threshold 10.00 USD"]
        actions = generate_recommended_actions(
            risks, [], self._full_profile(), {"sponsor": "sponsor@contoso.com"}
        )
        assert any("finops" in a.lower() or "cost" in a.lower() for a in actions)

    def test_idle_risk_produces_sponsor_action(self):
        risks = ["Idle agent: no requests in the last 7 days (threshold: 3d)"]
        actions = generate_recommended_actions(
            risks, [], self._full_profile(), {"sponsor": "sponsor@contoso.com"}
        )
        assert any("idle" in a.lower() or "still needed" in a.lower() for a in actions)

    def test_missing_business_stream_produces_action(self):
        profile = {k: v for k, v in self._full_profile().items() if k != "business_stream"}
        actions = generate_recommended_actions([], [], profile, {})
        assert any("business_stream" in a for a in actions)

    def test_missing_value_descriptions_produces_action(self):
        profile = {"business_stream": "IT", "outcome_description": "x"}
        actions = generate_recommended_actions([], [], profile, {})
        assert any("value" in a.lower() for a in actions)

    def test_missing_outcome_description_produces_action(self):
        profile = {
            "business_stream": "IT",
            "efficiency_value_description": "x",
            "outcome_value_description": "y",
        }
        actions = generate_recommended_actions([], [], profile, {})
        assert any("outcome_description" in a for a in actions)

    def test_complete_profile_no_risks_no_advisor_returns_empty(self):
        actions = generate_recommended_actions([], [], self._full_profile(), {})
        assert actions == []

    def test_advisor_item_produces_action(self):
        advisor = ["Enable soft delete for Key Vault"]
        actions = generate_recommended_actions([], advisor, self._full_profile(), {})
        assert any("soft delete" in a.lower() for a in actions)

    def test_advisor_error_item_is_skipped(self):
        advisor = ["Error fetching Advisor data: connection refused"]
        actions = generate_recommended_actions([], advisor, self._full_profile(), {})
        assert not any("connection refused" in a for a in actions)


# ── load_agent_profile ────────────────────────────────────────────────────────

class TestLoadAgentProfile:

    def test_loads_valid_yaml(self, tmp_path: Path):
        profile_file = tmp_path / "agent_profile.yaml"
        profile_file.write_text(
            "agent_name: TestAgent\nbusiness_stream: IT Operations\nowner_email: owner@contoso.com\n",
            encoding="utf-8",
        )
        result = load_agent_profile(profile_file)
        assert result["agent_name"] == "TestAgent"
        assert result["business_stream"] == "IT Operations"
        assert result["owner_email"] == "owner@contoso.com"

    def test_missing_file_returns_empty_dict(self, tmp_path: Path):
        result = load_agent_profile(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_empty_yaml_returns_empty_dict(self, tmp_path: Path):
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        assert load_agent_profile(f) == {}


# ── fetch_governance ──────────────────────────────────────────────────────────

class TestFetchGovernance:

    def _cred(self):
        cred = MagicMock()
        cred.get_token.return_value = MagicMock(token="fake-token")
        return cred

    def test_no_guid_returns_profile_values(self):
        profile = {"owner_email": "owner@contoso.com", "sponsor_email": "sponsor@contoso.com"}
        result = fetch_governance("", self._cred(), profile)
        assert result["owner"] == "owner@contoso.com"
        assert result["sponsor"] == "sponsor@contoso.com"

    def test_no_guid_no_profile_returns_dashes(self):
        result = fetch_governance("", self._cred(), {})
        assert "—" in result.get("owner", "—")

    def test_403_uses_profile_fallback(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        profile = {"owner_email": "owner@contoso.com", "sponsor_email": "sponsor@contoso.com"}
        with patch("report.httpx.get", return_value=mock_resp):
            result = fetch_governance("some-guid", self._cred(), profile)
        assert result["owner"] == "owner@contoso.com"
        assert result["sponsor"] == "sponsor@contoso.com"

    def test_200_graph_overrides_profile(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ownerDisplayName": "Alice Graph",
            "sponsorDisplayName": "Bob Graph",
        }
        profile = {"owner_email": "owner@contoso.com"}
        with patch("report.httpx.get", return_value=mock_resp):
            result = fetch_governance("some-guid", self._cred(), profile)
        assert result["owner"] == "Alice Graph"
        assert result["sponsor"] == "Bob Graph"

    def test_network_error_uses_profile_fallback(self):
        profile = {"owner_email": "owner@contoso.com"}
        with patch("report.httpx.get", side_effect=Exception("network error")):
            result = fetch_governance("some-guid", self._cred(), profile)
        assert result["owner"] == "owner@contoso.com"
