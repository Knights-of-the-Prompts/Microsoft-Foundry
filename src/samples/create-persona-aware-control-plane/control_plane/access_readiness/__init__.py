"""Access Readiness Agent — persona-aware access checking for the Control Plane.

Responsibilities:
1. Accept a persona and a KPI Agent result.
2. Inspect required signals, platforms and tools.
3. Determine what access (scopes, roles, permissions, actions) is required.
4. Compare required access with the persona's mock grants.
5. Return access check results per connector/tool.
6. Flag access gaps with business impact and least-privilege recommendations.
7. Generate access request recommendations (no auto-granting).
8. Write evidence events for every check outcome.

Design rules:
- Access Readiness Agent NEVER grants access.
- KPI Agent stays pure: it interprets KPIs.  This agent handles IAM.
- All mock grants are deterministic — demo works without real IAM dependencies.
- Live mode upgrade: replace _get_grants() with a real identity/IAM call.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from control_plane.connectors.registry import ToolRegistry
from control_plane.models.access import (
    AccessCheckResult,
    AccessCheckStatus,
    AccessGap,
    AccessGapType,
    AccessGrantSource,
    AccessRequest,
    AccessRequestStatus,
    CurrentAccessGrant,
    OverallAccessStatus,
    SensitiveDataLevel,
)
from control_plane.stores import evidence_store


# ---------------------------------------------------------------------------
# Mock access grants — what each persona can currently do per platform.
# This is the only source of IAM truth in mock mode.
# In live mode, replace with a call to Microsoft Entra / PIM / RBAC API.
# ---------------------------------------------------------------------------

# Structure: persona_id → platform_id → grant
_MOCK_GRANTS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "compliance_officer": {
        "agent365": {
            "scope": "AgentRegistry.Read",
            "role": "Agent Registry Viewer",
            "permission": "read",
            "actions": ["list_agents", "read_agent_metadata", "read_ownership"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": {
            "scope": "Project.Read",
            "role": "AI Project Reader",
            "permission": "read",
            "actions": ["read_invocations", "read_evaluation_summaries"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "servicenow": {
            "scope": "incident.read task.read",
            "role": "ITSM Viewer",
            "permission": "read",
            "actions": ["read_incidents", "read_remediation_tasks", "read_sla"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "azure": {
            "scope": "SecurityEvents.Read.All",
            "role": "Security Reader",
            "permission": "read",
            "actions": ["read_security_events", "read_anomalous_signins"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "microsoft365": {
            # Cannot read sensitive user-level content
            "scope": "Reports.Read.All",
            "role": "Reports Reader",
            "permission": "read",
            "actions": ["read_sharing_reports", "read_teams_usage"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "kubernetes": None,  # not in scope for compliance KPIs
        "salesforce": None,
    },
    "cfo": {
        "azure": {
            "scope": "Cost Management Reader",
            "role": "Cost Management Reader",
            "permission": "read",
            "actions": ["read_cost_summary", "read_resource_tags"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": {
            "scope": "Project.Read Usage.Read",
            "role": "Foundry Cost Reader",
            "permission": "read",
            "actions": ["read_model_usage", "read_agent_invocations"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "salesforce": {
            "scope": "opportunity.read case.read",
            "role": "Sales Analyst",
            "permission": "read",
            "actions": ["read_opportunity_pipeline", "read_case_resolution"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "microsoft365": None,  # no default M365 grant for CFO
        "kubernetes": None,
        "agent365": None,
        "servicenow": None,
    },
    "cto": {
        "azure": {
            "scope": "ResourceHealth.Read Subscription.Read",
            "role": "Reader",
            "permission": "read",
            "actions": ["read_resource_health", "read_subscriptions"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "kubernetes": {
            "scope": "cluster-reader",
            "role": "Cluster Viewer",
            "permission": "read",
            "actions": ["read_deployments", "read_pods"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": {
            "scope": "Project.Read",
            "role": "AI Platform Architect",
            "permission": "read",
            "actions": ["read_project_health", "read_agent_registrations"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "agent365": {
            "scope": "AgentRegistry.Read",
            "role": "Agent Platform Viewer",
            "permission": "read",
            "actions": ["list_agents", "read_agent_metadata"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "microsoft365": None,
        "salesforce": None,
        "servicenow": None,
    },
    "it_manager": {
        "azure": {
            "scope": "ResourceHealth.Read SecurityEvents.Read.All",
            "role": "Monitoring Reader",
            "permission": "read",
            "actions": ["read_resource_health", "read_security_events"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "kubernetes": {
            "scope": "cluster-reader",
            "role": "Cluster Viewer",
            "permission": "read",
            "actions": ["read_deployments", "read_pods"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "servicenow": {
            "scope": "incident.read incident.write sla.read",
            "role": "ITIL Manager",
            "permission": "read_write",
            "actions": [
                "read_incidents", "create_incidents",
                "update_incidents", "read_sla", "read_change_requests",
            ],
            "can_read_sensitive": False,
            "can_modify": True,
        },
        "agent365": {
            "scope": "AgentRegistry.Read",
            "role": "IT Operations Viewer",
            "permission": "read",
            "actions": ["list_agents", "read_ownership"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": {
            "scope": "Project.Read",
            "role": "Platform Operations Reader",
            "permission": "read",
            "actions": ["read_project_health"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "microsoft365": None,
        "salesforce": None,
    },
    "security_officer": {
        "azure": {
            "scope": "SecurityEvents.Read.All AuditLog.Read.All",
            "role": "Security Reader",
            "permission": "read",
            "actions": [
                "read_security_events", "read_anomalous_signins",
                "read_audit_logs",
            ],
            "can_read_sensitive": True,
            "can_modify": False,
        },
        "microsoft365": {
            "scope": "AuditLog.Read.All Reports.Read.All",
            "role": "Security Reader",
            "permission": "read",
            "actions": ["read_sharing_reports", "read_user_activity", "read_dlp_events"],
            "can_read_sensitive": True,
            "can_modify": False,
        },
        "servicenow": {
            "scope": "incident.read security.read",
            "role": "Security Operations Viewer",
            "permission": "read",
            "actions": ["read_incidents", "read_security_incidents"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "agent365": {
            "scope": "AgentRegistry.Read",
            "role": "Security Compliance Reviewer",
            "permission": "read",
            "actions": ["list_agents", "read_agent_metadata", "read_ownership"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "kubernetes": None,
        "foundry": None,
        "salesforce": None,
    },
    "business_owner": {
        "salesforce": {
            "scope": "opportunity.read case.read",
            "role": "Business Analyst",
            "permission": "read",
            "actions": ["read_opportunity_pipeline", "read_case_resolution"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": {
            "scope": "Project.Read",
            "role": "Business Stakeholder",
            "permission": "read",
            "actions": ["read_agent_invocations"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "azure": {
            "scope": "ResourceHealth.Read",
            "role": "Reader",
            "permission": "read",
            "actions": ["read_resource_health"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "microsoft365": None,
        "kubernetes": None,
        "agent365": None,
        "servicenow": None,
    },
    "product_owner": {
        "foundry": {
            "scope": "Project.Read",
            "role": "Product Stakeholder",
            "permission": "read",
            "actions": ["read_project_health", "read_agent_invocations"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "agent365": {
            "scope": "AgentRegistry.Read",
            "role": "Product Owner",
            "permission": "read",
            "actions": ["list_agents", "read_agent_activity"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "servicenow": {
            "scope": "change_request.read",
            "role": "Change Advisory Board Member",
            "permission": "read",
            "actions": ["read_change_requests"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "azure": None,
        "kubernetes": None,
        "microsoft365": None,
        "salesforce": None,
    },
    "service_owner": {
        "servicenow": {
            "scope": "incident.read sla.read",
            "role": "Service Owner",
            "permission": "read",
            "actions": ["read_incidents", "read_sla", "read_escalations"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "azure": {
            "scope": "ResourceHealth.Read",
            "role": "Reader",
            "permission": "read",
            "actions": ["read_resource_health"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "kubernetes": {
            "scope": "cluster-reader",
            "role": "Cluster Viewer",
            "permission": "read",
            "actions": ["read_deployments", "read_pods"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "salesforce": {
            "scope": "case.read",
            "role": "Support Analyst",
            "permission": "read",
            "actions": ["read_case_resolution"],
            "can_read_sensitive": False,
            "can_modify": False,
        },
        "foundry": None,
        "microsoft365": None,
        "agent365": None,
    },
}

# What a given signal type requires from which platform
_SIGNAL_REQUIREMENTS: Dict[str, Dict[str, Any]] = {
    "security_events": {
        "platform_id": "azure",
        "tool": "get_security_events",
        "scope": "SecurityEvents.Read.All",
        "role": "Security Reader",
        "permission": "read",
        "actions": ["read_security_events"],
        "sensitive_data_level": "high",
    },
    "user_activity": {
        "platform_id": "microsoft365",
        "tool": "get_user_activity",
        "scope": "Reports.Read.All",
        "role": "Reports Reader",
        "permission": "read",
        "actions": ["read_user_activity"],
        "sensitive_data_level": "medium",
    },
    "compliance_status": {
        "platform_id": "microsoft365",
        "tool": "get_user_activity",
        "scope": "Reports.Read.All",
        "role": "Compliance Administrator",
        "permission": "read",
        "actions": ["read_compliance_reports"],
        "sensitive_data_level": "medium",
    },
    "agent_registrations": {
        "platform_id": "agent365",
        "tool": "list_agent_registrations",
        "scope": "AgentRegistry.Read",
        "role": "Agent Registry Viewer",
        "permission": "read",
        "actions": ["list_agents"],
        "sensitive_data_level": "low",
    },
    "agent_invocations": {
        "platform_id": "foundry",
        "tool": "get_agent_invocations",
        "scope": "Project.Read",
        "role": "AI Project Reader",
        "permission": "read",
        "actions": ["read_invocations"],
        "sensitive_data_level": "low",
    },
    "cost_data": {
        "platform_id": "azure",
        "tool": "get_cost_summary",
        "scope": "Cost Management Reader",
        "role": "Cost Management Reader",
        "permission": "read",
        "actions": ["read_cost_summary"],
        "sensitive_data_level": "low",
    },
    "model_usage": {
        "platform_id": "foundry",
        "tool": "get_model_usage",
        "scope": "Usage.Read",
        "role": "Foundry Usage Reader",
        "permission": "read",
        "actions": ["read_model_usage"],
        "sensitive_data_level": "low",
    },
    "revenue_impact": {
        "platform_id": "salesforce",
        "tool": "get_opportunity_pipeline",
        "scope": "opportunity.read",
        "role": "Sales Analyst",
        "permission": "read",
        "actions": ["read_opportunity_pipeline"],
        "sensitive_data_level": "medium",
    },
    "opportunity_pipeline": {
        "platform_id": "salesforce",
        "tool": "get_opportunity_pipeline",
        "scope": "opportunity.read",
        "role": "Sales Analyst",
        "permission": "read",
        "actions": ["read_opportunity_pipeline"],
        "sensitive_data_level": "medium",
    },
    "resource_health": {
        "platform_id": "azure",
        "tool": "list_resource_health",
        "scope": "ResourceHealth.Read",
        "role": "Reader",
        "permission": "read",
        "actions": ["read_resource_health"],
        "sensitive_data_level": "none",
    },
    "deployment_status": {
        "platform_id": "kubernetes",
        "tool": "get_deployment_status",
        "scope": "cluster-reader",
        "role": "Cluster Viewer",
        "permission": "read",
        "actions": ["read_deployments"],
        "sensitive_data_level": "none",
    },
    "project_health": {
        "platform_id": "foundry",
        "tool": "get_project_health",
        "scope": "Project.Read",
        "role": "AI Project Reader",
        "permission": "read",
        "actions": ["read_project_health"],
        "sensitive_data_level": "none",
    },
    "incidents": {
        "platform_id": "servicenow",
        "tool": "get_open_incidents",
        "scope": "incident.read",
        "role": "ITSM Viewer",
        "permission": "read",
        "actions": ["read_incidents"],
        "sensitive_data_level": "low",
    },
    "sla_compliance": {
        "platform_id": "servicenow",
        "tool": "get_sla_compliance",
        "scope": "sla.read",
        "role": "ITSM Viewer",
        "permission": "read",
        "actions": ["read_sla"],
        "sensitive_data_level": "none",
    },
    "change_requests": {
        "platform_id": "servicenow",
        "tool": "get_change_requests",
        "scope": "change_request.read",
        "role": "Change Advisory Board Member",
        "permission": "read",
        "actions": ["read_change_requests"],
        "sensitive_data_level": "none",
    },
    "case_resolution": {
        "platform_id": "salesforce",
        "tool": "get_case_resolution",
        "scope": "case.read",
        "role": "Support Analyst",
        "permission": "read",
        "actions": ["read_case_resolution"],
        "sensitive_data_level": "low",
    },
    "agent_activity": {
        "platform_id": "agent365",
        "tool": "get_agent_activity",
        "scope": "AgentRegistry.Read",
        "role": "Agent Registry Viewer",
        "permission": "read",
        "actions": ["read_agent_activity"],
        "sensitive_data_level": "low",
    },
    "ownership_data": {
        "platform_id": "agent365",
        "tool": "get_ownership_coverage",
        "scope": "AgentRegistry.Read",
        "role": "Agent Registry Viewer",
        "permission": "read",
        "actions": ["read_ownership"],
        "sensitive_data_level": "none",
    },
}

_RECOMMENDED_APPROVERS: Dict[str, str] = {
    "azure": "Azure RBAC Administrator / Subscription Owner",
    "microsoft365": "M365 Global Administrator or Privileged Role Administrator",
    "kubernetes": "Kubernetes Cluster Administrator",
    "foundry": "AI Platform Owner or Foundry Project Administrator",
    "agent365": "Agent 365 Administrator",
    "servicenow": "ServiceNow System Administrator or ITIL Manager",
    "salesforce": "Salesforce System Administrator",
}


def _persona_kpi_id(persona_id: str) -> str:
    """Return a stable KPI ID for evidence events."""
    return f"{persona_id}_kpi_01"


class AccessReadinessAgent:
    """Checks whether the selected persona has the access required by their KPI.

    Usage::

        agent = AccessReadinessAgent(registry)
        result = agent.check(
            persona_id="compliance_officer",
            kpi_agent_result={
                "required_signals": [...],
                "selected_platforms": [...],
                "available_tools_used": [...],
            },
        )
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_grants(self, persona_id: str) -> List[Dict[str, Any]]:
        """Return all mock access grants for a persona."""
        persona_grants = _MOCK_GRANTS.get(persona_id, {})
        result = []
        for platform_id, grant in persona_grants.items():
            if grant is None:
                continue
            result.append(CurrentAccessGrant(
                id=str(uuid.uuid4()),
                persona_id=persona_id,
                connector_id=platform_id,
                platform_id=platform_id,
                granted_scope=grant["scope"],
                granted_role=grant["role"],
                granted_permission=grant["permission"],
                granted_actions=grant["actions"],
                source=AccessGrantSource.MOCK,
                last_verified_at=datetime.now(timezone.utc).isoformat(),
            ).to_dict())
        return result

    def check(
        self,
        persona_id: str,
        kpi_agent_result: Dict[str, Any],
        mode: str = "mock",
    ) -> Dict[str, Any]:
        """Run access readiness check for a persona + KPI Agent result.

        Returns a structured response with:
        - overall_status: ready | partially_ready | blocked
        - access_check_results: per-signal check outcome
        - access_gaps: specific gaps with business impact
        - recommended_access_requests: least-privilege request templates
        - evidence_events: audit trail
        """
        required_signals: List[str] = kpi_agent_result.get("required_signals", [])
        kpi_id = kpi_agent_result.get(
            "normalized_kpi", {}
        ).get("metric") or _persona_kpi_id(persona_id)
        persona_grants = _MOCK_GRANTS.get(persona_id, {})
        evidence_events: List[Dict[str, Any]] = []
        check_results: List[Dict[str, Any]] = []
        access_gaps: List[Dict[str, Any]] = []
        recommended_requests: List[Dict[str, Any]] = []

        # --- Write "access check started" event ---
        evidence_store.add_event(
            "access_checked",
            {
                "persona_id": persona_id,
                "kpi_id": kpi_id,
                "signals_to_check": required_signals,
            },
            persona_id=persona_id,
            kpi_id=kpi_id,
            source_mode=mode,
        )
        evidence_events.append(self._evt("access_checked", persona_id, kpi_id, {
            "signals_to_check": required_signals,
        }))

        # --- Check each required signal ---
        processed: set = set()
        for signal_type in required_signals:
            req = _SIGNAL_REQUIREMENTS.get(signal_type)
            if req is None:
                continue
            platform_id = req["platform_id"]
            key = (signal_type, platform_id)
            if key in processed:
                continue
            processed.add(key)

            grant = persona_grants.get(platform_id)
            result = self._check_one(
                persona_id=persona_id,
                kpi_id=kpi_id,
                signal_type=signal_type,
                req=req,
                grant=grant,
                mode=mode,
            )
            check_results.append(result.to_dict())

            # --- Write evidence event per outcome ---
            if result.status == AccessCheckStatus.MISSING_ACCESS:
                evidence_store.add_event(
                    "access_gap_detected",
                    {
                        "persona_id": persona_id,
                        "connector_id": platform_id,
                        "signal_type": signal_type,
                        "missing_scopes": result.missing_scopes,
                        "missing_roles": result.missing_roles,
                    },
                    persona_id=persona_id,
                    kpi_id=kpi_id,
                    source_mode=mode,
                )
                evidence_events.append(self._evt(
                    "access_gap_detected", persona_id, kpi_id,
                    {"signal_type": signal_type, "platform": platform_id},
                ))
                gap = self._build_gap(
                    persona_id, kpi_id, platform_id, signal_type, req, result
                )
                access_gaps.append(gap.to_dict())

                rec = self._build_request(
                    persona_id, kpi_id, platform_id, signal_type, req
                )
                recommended_requests.append(rec.to_dict())
                evidence_store.add_event(
                    "access_request_recommended",
                    {
                        "persona_id": persona_id,
                        "connector_id": platform_id,
                        "requested_scope": req["scope"],
                    },
                    persona_id=persona_id,
                    kpi_id=kpi_id,
                    source_mode=mode,
                )
                evidence_events.append(self._evt(
                    "access_request_recommended", persona_id, kpi_id,
                    {"platform": platform_id, "scope": req["scope"]},
                ))

            elif result.status == AccessCheckStatus.CONNECTOR_NOT_CONFIGURED:
                evidence_store.add_event(
                    "connector_access_insufficient",
                    {
                        "persona_id": persona_id,
                        "connector_id": platform_id,
                        "reason": "connector not configured",
                    },
                    persona_id=persona_id,
                    kpi_id=kpi_id,
                    source_mode=mode,
                )
                evidence_events.append(self._evt(
                    "connector_access_insufficient", persona_id, kpi_id,
                    {"platform": platform_id},
                ))

        # --- Overall status ---
        if not check_results:
            overall = OverallAccessStatus.BLOCKED.value
        elif not access_gaps:
            overall = OverallAccessStatus.READY.value
        elif len(access_gaps) < len(check_results):
            overall = OverallAccessStatus.PARTIALLY_READY.value
        else:
            overall = OverallAccessStatus.BLOCKED.value

        return {
            "persona_id": persona_id,
            "kpi_id": kpi_id,
            "overall_status": overall,
            "access_check_results": check_results,
            "access_gaps": access_gaps,
            "recommended_access_requests": recommended_requests,
            "evidence_events": evidence_events,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "source_mode": mode,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_one(
        self,
        persona_id: str,
        kpi_id: str,
        signal_type: str,
        req: Dict[str, Any],
        grant: Optional[Dict[str, Any]],
        mode: str,
    ) -> AccessCheckResult:
        platform_id = req["platform_id"]
        tool_name = req["tool"]
        required_scope = req["scope"]
        required_role = req["role"]
        required_permission = req["permission"]
        required_actions: List[str] = req["actions"]

        if grant is None:
            return AccessCheckResult(
                id=str(uuid.uuid4()),
                persona_id=persona_id,
                kpi_id=kpi_id,
                connector_id=platform_id,
                platform_id=platform_id,
                tool_name=tool_name,
                status=AccessCheckStatus.MISSING_ACCESS,
                required_access={
                    "scope": required_scope,
                    "role": required_role,
                    "permission": required_permission,
                    "actions": required_actions,
                },
                current_access={},
                missing_scopes=[required_scope],
                missing_roles=[required_role],
                missing_permissions=[required_permission],
                missing_actions=required_actions,
                explanation=(
                    f"Persona '{persona_id}' has no access grant for "
                    f"platform '{platform_id}'. "
                    f"Signal '{signal_type}' requires {required_role}."
                ),
                recommended_request=(
                    f"Request {required_role} on {platform_id} to enable "
                    f"'{signal_type}' signal for this KPI."
                ),
                confidence_score=1.0,
                source_mode=mode,
            )

        # Check each dimension
        granted_scopes = set(grant["scope"].split())
        required_scopes_set = set(required_scope.split())
        missing_scopes = list(required_scopes_set - granted_scopes)

        granted_role_val = grant["role"]
        missing_roles: List[str] = (
            [] if granted_role_val == required_role
            or required_role in granted_role_val
            or granted_role_val in required_role
            else [required_role]
        )

        granted_actions = set(grant["actions"])
        missing_actions = [a for a in required_actions if a not in granted_actions]

        has_all = not missing_scopes and not missing_roles and not missing_actions

        if has_all:
            status = AccessCheckStatus.ALLOWED
            explanation = (
                f"Persona '{persona_id}' has sufficient access to "
                f"'{signal_type}' via {platform_id}."
            )
            recommended_request = ""
        elif not missing_scopes and missing_actions:
            status = AccessCheckStatus.PARTIALLY_ALLOWED
            explanation = (
                f"Persona '{persona_id}' can read '{signal_type}' from {platform_id} "
                f"but is missing actions: {', '.join(missing_actions)}."
            )
            recommended_request = (
                f"Request additional actions {missing_actions} on {platform_id}."
            )
        else:
            status = AccessCheckStatus.MISSING_ACCESS
            explanation = (
                f"Persona '{persona_id}' lacks the '{required_role}' role "
                f"on {platform_id} needed to retrieve '{signal_type}'."
            )
            recommended_request = (
                f"Request {required_role} on {platform_id} with scope "
                f"'{required_scope}' to enable this KPI insight."
            )

        return AccessCheckResult(
            id=str(uuid.uuid4()),
            persona_id=persona_id,
            kpi_id=kpi_id,
            connector_id=platform_id,
            platform_id=platform_id,
            tool_name=tool_name,
            status=status,
            required_access={
                "scope": required_scope,
                "role": required_role,
                "permission": required_permission,
                "actions": required_actions,
            },
            current_access={
                "scope": grant["scope"],
                "role": grant["role"],
                "permission": grant["permission"],
                "actions": grant["actions"],
            },
            missing_scopes=missing_scopes,
            missing_roles=missing_roles,
            missing_permissions=[],
            missing_actions=missing_actions,
            explanation=explanation,
            recommended_request=recommended_request,
            confidence_score=0.85,
            source_mode=mode,
        )

    @staticmethod
    def _build_gap(
        persona_id: str,
        kpi_id: str,
        platform_id: str,
        signal_type: str,
        req: Dict[str, Any],
        result: "AccessCheckResult",
    ) -> AccessGap:
        sensitive = req.get("sensitive_data_level", "low")
        risk_if_granted = (
            "Low risk — read-only access to non-sensitive operational data."
            if sensitive in ("none", "low")
            else f"Medium risk — grants access to {sensitive}-sensitivity data. "
            "Apply time-bound access and require periodic re-certification."
        )
        return AccessGap(
            id=str(uuid.uuid4()),
            persona_id=persona_id,
            kpi_id=kpi_id,
            connector_id=platform_id,
            platform_id=platform_id,
            gap_type=AccessGapType.MISSING_ROLE,
            description=(
                f"Persona '{persona_id}' cannot retrieve '{signal_type}' from "
                f"'{platform_id}' — missing role: {req['role']}."
            ),
            business_impact=(
                f"KPI insight for '{kpi_id}' will be incomplete without "
                f"'{signal_type}'. Confidence score will be reduced."
            ),
            risk_if_granted=risk_if_granted,
            risk_if_not_granted=(
                f"KPI digest will show an evidence gap for '{signal_type}'. "
                "Control-plane recommendations may be unreliable."
            ),
            recommended_approver=_RECOMMENDED_APPROVERS.get(
                platform_id, "Platform Administrator"
            ),
            recommended_duration="30 days, renewable with re-justification.",
            least_privilege_recommendation=(
                f"Grant read-only '{req['role']}' on '{platform_id}' scoped to "
                f"the minimum resource group / project required for this KPI. "
                "Do not grant write or admin permissions."
            ),
        )

    @staticmethod
    def _build_request(
        persona_id: str,
        kpi_id: str,
        platform_id: str,
        signal_type: str,
        req: Dict[str, Any],
    ) -> AccessRequest:
        return AccessRequest(
            id=str(uuid.uuid4()),
            persona_id=persona_id,
            kpi_id=kpi_id,
            connector_id=platform_id,
            platform_id=platform_id,
            requested_scope=req["scope"],
            requested_role=req["role"],
            requested_permission=req["permission"],
            requested_actions=req["actions"],
            justification=(
                f"KPI '{kpi_id}' requires '{signal_type}' from '{platform_id}'. "
                f"Current access does not include role '{req['role']}'."
            ),
            business_outcome=(
                f"Enables complete control-plane digest for persona '{persona_id}'. "
                "Improves confidence score and reduces evidence gaps."
            ),
            status=AccessRequestStatus.DRAFT,
            recommended_approver=_RECOMMENDED_APPROVERS.get(
                platform_id, "Platform Administrator"
            ),
        )

    @staticmethod
    def _evt(
        event_type: str,
        persona_id: str,
        kpi_id: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "event_type": event_type,
            "persona_id": persona_id,
            "kpi_id": kpi_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
