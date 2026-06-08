"""
tests/test_lifecycle_rules.py

Focused unit tests for the lifecycle decision logic.
Tests use in-memory data only. No Azure calls are made.
"""

import sys
import os

# Ensure the sample root is on sys.path so imports work without installation.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import (
    AgentProfile,
    AzureAdvisorFinding,
    AzureResourceEvidence,
    EvidenceBundle,
)
from evaluate_lifecycle import evaluate_lifecycle

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

BASE_POLICY = {
    "current_state": "operating",
    "metadata_gate": {
        "required_fields": [
            "owner_email",
            "sponsor_email",
            "business_stream",
            "expected_outcome",
            "cost_center",
        ]
    },
    "azure_resource_gate": {
        "require_at_least_one_resource": True,
        "required_tags": ["agent_id", "owner", "cost_center"],
    },
    "risk_gate": {
        "fail_on_high_advisor_findings": True,
        "warn_on_medium_advisor_findings": True,
    },
}


def _make_profile(**overrides) -> AgentProfile:
    defaults = dict(
        agent_id="test-agent",
        display_name="Test Agent",
        owner_email="owner@test.com",
        sponsor_email="sponsor@test.com",
        business_stream="sales",
        expected_outcome="Increase conversion",
        cost_center="CC-001",
        environment="development",
        azure_resource_group="rg-test",
        required_resource_tags=["agent_id", "owner", "cost_center"],
    )
    defaults.update(overrides)
    return AgentProfile(**defaults)


def _make_resource(name: str = "res1", missing_tags: list[str] | None = None) -> AzureResourceEvidence:
    return AzureResourceEvidence(
        resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Test/test/res1",
        name=name,
        type="Microsoft.Test/test",
        location="eastus",
        tags={"agent_id": "test-agent", "owner": "owner@test.com", "cost_center": "CC-001"},
        missing_required_tags=missing_tags or [],
    )


def _make_advisor_finding(impact: str = "High") -> AzureAdvisorFinding:
    return AzureAdvisorFinding(
        recommendation_id="rec-001",
        category="Security",
        impact=impact,
        impacted_resource_id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Test/test/res1",
        short_description="Test recommendation",
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_missing_owner_recommends_remediate():
    """Missing owner_email in profile should recommend Remediate."""
    profile = _make_profile(owner_email="")
    evidence = EvidenceBundle(agent_id="test-agent", resources=[_make_resource()])
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Remediate"
    assert package.recommended_state == "remediating"


def test_missing_sponsor_recommends_remediate():
    """Missing sponsor_email in profile should recommend Remediate."""
    profile = _make_profile(sponsor_email="")
    evidence = EvidenceBundle(agent_id="test-agent", resources=[_make_resource()])
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Remediate"
    assert package.recommended_state == "remediating"


def test_no_azure_resources_recommends_review():
    """No associated Azure resources should recommend Review / under_review."""
    profile = _make_profile()
    evidence = EvidenceBundle(agent_id="test-agent")  # empty resources
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Review"
    assert package.recommended_state == "under_review"


def test_missing_resource_tags_recommends_remediate():
    """Resources with missing required tags should recommend Remediate."""
    profile = _make_profile()
    resource = _make_resource(missing_tags=["cost_center", "owner"])
    evidence = EvidenceBundle(agent_id="test-agent", resources=[resource])
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Remediate"
    assert package.recommended_state == "remediating"


def test_high_risk_advisor_finding_recommends_restrict():
    """A high-impact Advisor finding should recommend Restrict."""
    profile = _make_profile()
    resource = _make_resource()
    finding = _make_advisor_finding(impact="High")
    evidence = EvidenceBundle(
        agent_id="test-agent",
        resources=[resource],
        advisor_findings=[finding],
    )
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Restrict"
    assert package.recommended_state == "restricted"


def test_all_gates_pass_recommends_operate():
    """When all gates pass, the recommendation should be Operate."""
    profile = _make_profile()
    resource = _make_resource()
    evidence = EvidenceBundle(agent_id="test-agent", resources=[resource])
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Operate"
    assert package.recommended_state == "operating"


def test_medium_advisor_finding_still_operates():
    """A medium-impact Advisor finding (warning only) should not block operation."""
    profile = _make_profile()
    resource = _make_resource()
    finding = _make_advisor_finding(impact="Medium")
    evidence = EvidenceBundle(
        agent_id="test-agent",
        resources=[resource],
        advisor_findings=[finding],
    )
    package = evaluate_lifecycle(profile, evidence, BASE_POLICY)

    assert package.recommended_action == "Operate"
    assert package.recommended_state == "operating"
    # The warning should still be visible in the explanation
    gate_map = {g.gate_name: g for g in package.gate_results}
    assert gate_map["risk_gate"].status == "warning"
