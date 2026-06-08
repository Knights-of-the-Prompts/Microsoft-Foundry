"""
evaluate_lifecycle.py

Evaluates lifecycle gates against the agent profile, Azure evidence
and lifecycle policy. Returns a LifecycleDecisionPackage.
"""

from __future__ import annotations

from dataclasses import fields as dataclass_fields
from typing import Any

from models import (
    AgentProfile,
    EvidenceBundle,
    GateResult,
    LifecycleDecisionPackage,
)

# Maps recommended actions to canonical lifecycle state names.
ACTION_TO_STATE: dict[str, str] = {
    "Operate": "operating",
    "Remediate": "remediating",
    "Restrict": "restricted",
    "Review": "under_review",
    "Retire": "retired",
}


def _evaluate_metadata_gate(profile: AgentProfile, policy: dict) -> GateResult:
    """Check that all required profile fields are present and non-empty."""
    required: list[str] = policy.get("metadata_gate", {}).get("required_fields", [])
    profile_dict = {f.name: getattr(profile, f.name) for f in dataclass_fields(profile)}
    missing = [f for f in required if not profile_dict.get(f)]

    if missing:
        return GateResult(
            gate_name="metadata_gate",
            status="fail",
            message=f"Required profile fields are missing or empty: {', '.join(missing)}",
            evidence={"missing_fields": missing},
        )
    return GateResult(
        gate_name="metadata_gate",
        status="pass",
        message="All required profile fields are present.",
        evidence={},
    )


def _evaluate_resource_gate(
    profile: AgentProfile, evidence: EvidenceBundle, policy: dict
) -> GateResult:
    """Check that at least one resource exists and required tags are present."""
    gate_cfg = policy.get("azure_resource_gate", {})
    require_one = gate_cfg.get("require_at_least_one_resource", True)

    if require_one and not evidence.resources:
        return GateResult(
            gate_name="azure_resource_gate",
            status="fail",
            message=(
                "No Azure resources were found that are associated with this agent. "
                "Tag at least one resource with agent_id, agentName, or "
                "accountable_agents_demo='true'."
            ),
            evidence={"resource_count": 0},
        )

    resources_with_missing: list[dict[str, Any]] = [
        {"name": r.name, "missing_tags": r.missing_required_tags}
        for r in evidence.resources
        if r.missing_required_tags
    ]

    if resources_with_missing:
        total_missing = sum(len(r["missing_tags"]) for r in resources_with_missing)
        return GateResult(
            gate_name="azure_resource_gate",
            status="fail",
            message=(
                f"{len(resources_with_missing)} resource(s) are missing required tags "
                f"({total_missing} tag occurrence(s) total)."
            ),
            evidence={"resources_with_missing_tags": resources_with_missing},
        )

    return GateResult(
        gate_name="azure_resource_gate",
        status="pass",
        message=f"All {len(evidence.resources)} resource(s) have required tags.",
        evidence={"resource_count": len(evidence.resources)},
    )


def _evaluate_risk_gate(evidence: EvidenceBundle, policy: dict) -> GateResult:
    """Check Azure Advisor findings for high or medium risk."""
    gate_cfg = policy.get("risk_gate", {})
    fail_on_high = gate_cfg.get("fail_on_high_advisor_findings", True)
    warn_on_medium = gate_cfg.get("warn_on_medium_advisor_findings", True)

    high_findings = [
        f for f in evidence.advisor_findings
        if f.impact.lower() == "high"
    ]
    medium_findings = [
        f for f in evidence.advisor_findings
        if f.impact.lower() == "medium"
    ]

    if fail_on_high and high_findings:
        return GateResult(
            gate_name="risk_gate",
            status="fail",
            message=(
                f"{len(high_findings)} high-impact Azure Advisor finding(s) require review."
            ),
            evidence={
                "high_findings": [
                    {"id": f.recommendation_id, "description": f.short_description}
                    for f in high_findings
                ]
            },
        )

    if warn_on_medium and medium_findings:
        return GateResult(
            gate_name="risk_gate",
            status="warning",
            message=(
                f"{len(medium_findings)} medium-impact Azure Advisor finding(s) noted."
            ),
            evidence={
                "medium_findings": [
                    {"id": f.recommendation_id, "description": f.short_description}
                    for f in medium_findings
                ]
            },
        )

    return GateResult(
        gate_name="risk_gate",
        status="pass",
        message="No high or medium risk Advisor findings.",
        evidence={"total_advisor_findings": len(evidence.advisor_findings)},
    )


def _determine_action(gate_results: list[GateResult]) -> str:
    """
    Apply decision rules in priority order and return the recommended action.

    Priority (highest first):
      1. Risk gate fail -> Restrict
      2. Metadata gate fail -> Remediate
      3. Resource gate fail with no resources -> Review
      4. Resource gate fail (tag issues) -> Remediate
      5. Warnings only (no failures) -> Operate (warnings surface in explanation)
      6. All pass -> Operate
    """
    gate_map = {g.gate_name: g for g in gate_results}

    risk = gate_map.get("risk_gate")
    if risk and risk.status == "fail":
        return "Restrict"

    metadata = gate_map.get("metadata_gate")
    if metadata and metadata.status == "fail":
        return "Remediate"

    resource = gate_map.get("azure_resource_gate")
    if resource and resource.status == "fail":
        evidence = resource.evidence or {}
        if evidence.get("resource_count") == 0:
            return "Review"
        return "Remediate"

    # Warnings alone do not block operation; they are surfaced in the explanation.
    return "Operate"


def _build_required_actions(gate_results: list[GateResult]) -> list[str]:
    """Extract human-readable required actions from failed or warned gates."""
    actions: list[str] = []
    for gate in gate_results:
        if gate.status not in ("fail", "warning"):
            continue
        evidence = gate.evidence or {}

        if gate.gate_name == "metadata_gate":
            for field in evidence.get("missing_fields", []):
                actions.append(f"Add missing profile field: {field}")

        elif gate.gate_name == "azure_resource_gate":
            for item in evidence.get("resources_with_missing_tags", []):
                for tag in item.get("missing_tags", []):
                    actions.append(f"Add missing tag '{tag}' to resource '{item['name']}'")
            if evidence.get("resource_count") == 0:
                actions.append(
                    "Associate at least one Azure resource with this agent by adding "
                    "a matching tag (agent_id, agentName, or accountable_agents_demo='true')"
                )

        elif gate.gate_name == "risk_gate":
            for finding in evidence.get("high_findings", []):
                actions.append(
                    f"Review high-risk Advisor recommendation: {finding.get('description', finding.get('id'))}"
                )
            for finding in evidence.get("medium_findings", []):
                actions.append(
                    f"Review medium-risk Advisor recommendation: {finding.get('description', finding.get('id'))}"
                )

    return actions


def evaluate_lifecycle(
    profile: AgentProfile,
    evidence: EvidenceBundle,
    policy: dict,
) -> LifecycleDecisionPackage:
    """
    Evaluate all lifecycle gates and return a LifecycleDecisionPackage.

    Gates evaluated:
      1. Metadata Gate — required profile fields
      2. Azure Resource Gate — resource existence and tag compliance
      3. Risk Gate — Azure Advisor findings

    Decision rules are applied in priority order (see _determine_action).
    """
    current_state: str = policy.get("current_state", "operating")

    gate_results = [
        _evaluate_metadata_gate(profile, policy),
        _evaluate_resource_gate(profile, evidence, policy),
        _evaluate_risk_gate(evidence, policy),
    ]

    recommended_action = _determine_action(gate_results)
    recommended_state = ACTION_TO_STATE.get(recommended_action, "under_review")
    required_actions = _build_required_actions(gate_results)

    # Build a plain-English explanation
    fail_gates = [g for g in gate_results if g.status == "fail"]
    warn_gates = [g for g in gate_results if g.status == "warning"]

    explanation_parts: list[str] = []
    for g in fail_gates:
        explanation_parts.append(g.message)
    for g in warn_gates:
        explanation_parts.append(g.message)
    if evidence.collection_warnings:
        explanation_parts.append(
            f"{len(evidence.collection_warnings)} Azure evidence collection warning(s) noted."
        )
    if not explanation_parts:
        explanation_parts.append("All lifecycle gates passed.")

    return LifecycleDecisionPackage(
        agent_id=profile.agent_id,
        display_name=profile.display_name,
        owner_email=profile.owner_email,
        sponsor_email=profile.sponsor_email,
        current_state=current_state,
        recommended_action=recommended_action,
        recommended_state=recommended_state,
        gate_results=gate_results,
        required_actions=required_actions,
        explanation=" ".join(explanation_parts),
    )
