"""Domain models for KPI refinement workflow.

Workflow:
  Draft KPI
  → KpiChallengeAgent  → KpiChallengeSession
  → FormalizedKpi
  → ControlCompositionAgent → ControlPackage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class KpiMaturityLevel(str, Enum):
    VAGUE = "vague"
    USABLE = "usable"
    WELL_ARTICULATED = "well_articulated"
    CONTROL_READY = "control_ready"


class ChallengeSessionStatus(str, Enum):
    DRAFT = "draft"
    CHALLENGED = "challenged"
    FORMALIZED = "formalized"
    CONTROL_READY = "control_ready"


# ---------------------------------------------------------------------------
# KPI Challenge Session
# ---------------------------------------------------------------------------


@dataclass
class KpiChallengeSession:
    """State for one interactive KPI refinement session."""

    id: str
    persona_id: str
    draft_kpi: str
    maturity_level: KpiMaturityLevel
    challenge_questions: List[str]
    suggested_formalized_kpi: Dict[str, Any]
    missing_fields: List[str]
    confidence_score: float
    status: ChallengeSessionStatus = ChallengeSessionStatus.CHALLENGED
    user_answers: Dict[str, str] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.id,
            "persona_id": self.persona_id,
            "draft_kpi": self.draft_kpi,
            "maturity_level": self.maturity_level.value,
            "challenge_questions": self.challenge_questions,
            "suggested_formalized_kpi": self.suggested_formalized_kpi,
            "missing_fields": self.missing_fields,
            "confidence_score": self.confidence_score,
            "status": self.status.value,
            "user_answers": self.user_answers,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Formalized KPI
# ---------------------------------------------------------------------------


@dataclass
class FormalizedKpi:
    """A fully articulated, governance-grade KPI."""

    id: str
    persona_id: str
    title: str
    outcome_statement: str
    metric: str
    target: str
    timeframe: str
    scope: str
    included_entities: List[str]
    excluded_entities: List[str]
    tradeoffs: List[str]
    evidence_standard: str
    risk_tolerance: str
    success_criteria: List[str]
    confidence_score: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "persona_id": self.persona_id,
            "title": self.title,
            "outcome_statement": self.outcome_statement,
            "metric": self.metric,
            "target": self.target,
            "timeframe": self.timeframe,
            "scope": self.scope,
            "included_entities": self.included_entities,
            "excluded_entities": self.excluded_entities,
            "tradeoffs": self.tradeoffs,
            "evidence_standard": self.evidence_standard,
            "risk_tolerance": self.risk_tolerance,
            "success_criteria": self.success_criteria,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Control Package
# ---------------------------------------------------------------------------


@dataclass
class ControlPackage:
    """The composed output after a KPI is formalized.

    Answers:
      A. "What will I get?"  — control_plane_outputs / what_you_get
      B. "What do I need?"   — required_* / what_you_need
    """

    id: str
    formalized_kpi_id: str
    persona_id: str
    what_you_get: List[str]
    what_you_need: List[str]
    required_signals: List[str]
    required_connectors: List[str]
    required_tools: List[str]
    required_access: List[Dict[str, str]]
    required_evidence: List[str]
    access_readiness_summary: Dict[str, Any]
    connector_readiness_summary: Dict[str, Any]
    recommended_actions: List[Dict[str, Any]]
    agent_ideas: List[Dict[str, Any]]
    evidence_events: List[str]
    limitations: List[str]
    confidence_score: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "formalized_kpi_id": self.formalized_kpi_id,
            "persona_id": self.persona_id,
            "what_you_get": self.what_you_get,
            "what_you_need": self.what_you_need,
            "required_signals": self.required_signals,
            "required_connectors": self.required_connectors,
            "required_tools": self.required_tools,
            "required_access": self.required_access,
            "required_evidence": self.required_evidence,
            "access_readiness_summary": self.access_readiness_summary,
            "connector_readiness_summary": self.connector_readiness_summary,
            "recommended_actions": self.recommended_actions,
            "agent_ideas": self.agent_ideas,
            "evidence_events": self.evidence_events,
            "limitations": self.limitations,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at,
        }
