"""Domain models for agent ideas, agent requests and evidence events.

These models extend the control plane with the governance workflow:
  KPI Agent generates ideas → persona requests one → evidence trail records it.

All models are plain dataclasses for simplicity.  No ORM or database is used;
the in-memory stores in ``control_plane.stores`` hold instances at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Agent Idea
# ---------------------------------------------------------------------------


class ImprovesCategory(str, Enum):
    VALUE = "value"
    COST = "cost"
    REPORTING = "reporting"
    RISK = "risk"
    COMPLIANCE = "compliance"
    OPERATIONS = "operations"
    EVIDENCE = "evidence"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ImplementationComplexity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class AgentIdea:
    """A generated agent idea linked to a persona KPI.

    Created by the KPI Agent based on signal gaps, evidence gaps, or
    opportunities identified in the weekly digest.
    """

    id: str
    title: str
    persona_id: str
    related_kpi_id: str
    problem_statement: str
    proposed_agent_capability: str
    required_tools: List[str]
    required_data_sources: List[str]
    expected_value: str
    risk_level: RiskLevel
    implementation_complexity: ImplementationComplexity
    governance_notes: str
    improves: List[ImprovesCategory]
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "persona_id": self.persona_id,
            "related_kpi_id": self.related_kpi_id,
            "problem_statement": self.problem_statement,
            "proposed_agent_capability": self.proposed_agent_capability,
            "required_tools": self.required_tools,
            "required_data_sources": self.required_data_sources,
            "expected_value": self.expected_value,
            "risk_level": self.risk_level.value,
            "implementation_complexity": self.implementation_complexity.value,
            "governance_notes": self.governance_notes,
            "improves": [c.value for c in self.improves],
            "generated_at": self.generated_at,
        }


# ---------------------------------------------------------------------------
# Agent Request
# ---------------------------------------------------------------------------


class AgentRequestStatus(str, Enum):
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    BUILDING = "building"
    DEPLOYED = "deployed"


@dataclass
class AgentRequest:
    """A persona's request to build an agent from an idea.

    Created when a user clicks "Request this agent" for an AgentIdea card.
    Every submission writes an evidence event.
    """

    id: str
    agent_idea_id: str
    requested_by_persona: str
    linked_kpi_id: str
    status: AgentRequestStatus
    rationale: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_idea_id": self.agent_idea_id,
            "requested_by_persona": self.requested_by_persona,
            "linked_kpi_id": self.linked_kpi_id,
            "status": self.status.value,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# Evidence Event
# ---------------------------------------------------------------------------


@dataclass
class EvidenceEvent:
    """An immutable governance event in the evidence trail.

    Every significant control plane action — KPI interpretation, signal
    selection, tool use, insight generation, agent request — is recorded
    here to provide a full audit trail.
    """

    id: str
    event_type: str
    persona_id: Optional[str]
    kpi_id: Optional[str]
    payload: Dict[str, Any]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source_mode: str = "mock"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "persona_id": self.persona_id,
            "kpi_id": self.kpi_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "source_mode": self.source_mode,
        }
