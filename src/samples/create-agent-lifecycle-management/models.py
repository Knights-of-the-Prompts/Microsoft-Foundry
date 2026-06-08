"""
models.py

Data models for the Agent Lifecycle Management sample.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentProfile:
    agent_id: str
    display_name: str
    owner_email: str
    sponsor_email: str
    business_stream: str
    expected_outcome: str
    cost_center: str
    environment: str
    azure_resource_group: str
    required_resource_tags: list[str]


@dataclass
class AzureResourceEvidence:
    resource_id: str
    name: str
    type: str
    location: str
    tags: dict[str, str]
    missing_required_tags: list[str]


@dataclass
class AzureAdvisorFinding:
    recommendation_id: str
    category: str
    impact: str
    impacted_resource_id: str
    short_description: str


@dataclass
class EvidenceBundle:
    agent_id: str
    resources: list[AzureResourceEvidence] = field(default_factory=list)
    advisor_findings: list[AzureAdvisorFinding] = field(default_factory=list)
    collection_warnings: list[str] = field(default_factory=list)


@dataclass
class GateResult:
    gate_name: str
    status: str  # pass, warning, fail
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class LifecycleDecisionPackage:
    agent_id: str
    display_name: str
    owner_email: str
    sponsor_email: str
    current_state: str
    recommended_action: str
    recommended_state: str
    gate_results: list[GateResult] = field(default_factory=list)
    required_actions: list[str] = field(default_factory=list)
    explanation: str = ""
