"""Access readiness domain models for the Persona-Aware Control Plane.

These models represent the access-checking layer that sits between the
KPI Agent and the connector infrastructure.  The Access Readiness Agent
uses these models to determine whether the selected persona has the right
permissions, scopes, and roles to retrieve the signals required by their KPI.

Design principles:
- No access is auto-granted.  The agent recommends; humans approve.
- All checks are KPI-driven: a connected connector may still be insufficient.
- Mock grants enable full demo without real IAM dependencies.
- Evidence events are written for every check, gap and request.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class AccessCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AccessGrantSource(str, Enum):
    MOCK = "mock"
    LIVE = "live"
    HYBRID = "hybrid"


class AccessCheckStatus(str, Enum):
    ALLOWED = "allowed"
    PARTIALLY_ALLOWED = "partially_allowed"
    MISSING_ACCESS = "missing_access"
    UNKNOWN = "unknown"
    CONNECTOR_NOT_CONFIGURED = "connector_not_configured"


class AccessGapType(str, Enum):
    MISSING_SCOPE = "missing_scope"
    MISSING_ROLE = "missing_role"
    MISSING_PERMISSION = "missing_permission"
    MISSING_ACTION = "missing_action"
    CONNECTOR_NOT_CONFIGURED = "connector_not_configured"
    INSUFFICIENT_DATA_ACCESS = "insufficient_data_access"


class OverallAccessStatus(str, Enum):
    READY = "ready"
    PARTIALLY_READY = "partially_ready"
    BLOCKED = "blocked"


class AccessRequestStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class SensitiveDataLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    RESTRICTED = "restricted"


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass
class AccessRequirement:
    """What a KPI requires from a specific connector/tool to produce insights."""

    id: str
    kpi_id: str
    persona_id: str
    connector_id: str
    platform_id: str
    tool_name: str
    required_signal_type: str
    required_action: str
    required_scope: str
    required_role: str
    required_permission: str
    reason: str
    criticality: AccessCriticality

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kpi_id": self.kpi_id,
            "persona_id": self.persona_id,
            "connector_id": self.connector_id,
            "platform_id": self.platform_id,
            "tool_name": self.tool_name,
            "required_signal_type": self.required_signal_type,
            "required_action": self.required_action,
            "required_scope": self.required_scope,
            "required_role": self.required_role,
            "required_permission": self.required_permission,
            "reason": self.reason,
            "criticality": self.criticality.value,
        }


@dataclass
class CurrentAccessGrant:
    """What access the persona currently has on a connector."""

    id: str
    persona_id: str
    connector_id: str
    platform_id: str
    granted_scope: str
    granted_role: str
    granted_permission: str
    granted_actions: List[str]
    source: AccessGrantSource
    evidence_ref: Optional[str] = None
    expires_at: Optional[str] = None
    last_verified_at: Optional[str] = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "persona_id": self.persona_id,
            "connector_id": self.connector_id,
            "platform_id": self.platform_id,
            "granted_scope": self.granted_scope,
            "granted_role": self.granted_role,
            "granted_permission": self.granted_permission,
            "granted_actions": self.granted_actions,
            "source": self.source.value,
            "evidence_ref": self.evidence_ref,
            "expires_at": self.expires_at,
            "last_verified_at": self.last_verified_at,
        }


@dataclass
class AccessCheckResult:
    """Result of checking one connector/tool against a persona's current grants."""

    id: str
    persona_id: str
    kpi_id: str
    connector_id: str
    platform_id: str
    tool_name: str
    status: AccessCheckStatus
    required_access: Dict[str, Any]
    current_access: Dict[str, Any]
    missing_scopes: List[str]
    missing_roles: List[str]
    missing_permissions: List[str]
    missing_actions: List[str]
    explanation: str
    recommended_request: str
    confidence_score: float
    source_mode: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "persona_id": self.persona_id,
            "kpi_id": self.kpi_id,
            "connector_id": self.connector_id,
            "platform_id": self.platform_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "required_access": self.required_access,
            "current_access": self.current_access,
            "missing_scopes": self.missing_scopes,
            "missing_roles": self.missing_roles,
            "missing_permissions": self.missing_permissions,
            "missing_actions": self.missing_actions,
            "explanation": self.explanation,
            "recommended_request": self.recommended_request,
            "confidence_score": self.confidence_score,
            "source_mode": self.source_mode,
        }


@dataclass
class AccessGap:
    """A specific access gap identified by the Access Readiness Agent."""

    id: str
    persona_id: str
    kpi_id: str
    connector_id: str
    platform_id: str
    gap_type: AccessGapType
    description: str
    business_impact: str
    risk_if_granted: str
    risk_if_not_granted: str
    recommended_approver: str
    recommended_duration: str
    least_privilege_recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "persona_id": self.persona_id,
            "kpi_id": self.kpi_id,
            "connector_id": self.connector_id,
            "platform_id": self.platform_id,
            "gap_type": self.gap_type.value,
            "description": self.description,
            "business_impact": self.business_impact,
            "risk_if_granted": self.risk_if_granted,
            "risk_if_not_granted": self.risk_if_not_granted,
            "recommended_approver": self.recommended_approver,
            "recommended_duration": self.recommended_duration,
            "least_privilege_recommendation": self.least_privilege_recommendation,
        }


@dataclass
class AccessRequest:
    """A persona's request for additional access to support a KPI."""

    id: str
    persona_id: str
    kpi_id: str
    connector_id: str
    platform_id: str
    requested_scope: str
    requested_role: str
    requested_permission: str
    requested_actions: List[str]
    justification: str
    business_outcome: str
    status: AccessRequestStatus
    recommended_approver: str
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "persona_id": self.persona_id,
            "kpi_id": self.kpi_id,
            "connector_id": self.connector_id,
            "platform_id": self.platform_id,
            "requested_scope": self.requested_scope,
            "requested_role": self.requested_role,
            "requested_permission": self.requested_permission,
            "requested_actions": self.requested_actions,
            "justification": self.justification,
            "business_outcome": self.business_outcome,
            "status": self.status.value,
            "recommended_approver": self.recommended_approver,
            "created_at": self.created_at,
        }
