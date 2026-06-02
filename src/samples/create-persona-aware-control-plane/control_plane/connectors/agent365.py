"""Microsoft Agent 365 mock connector.

Provides mock signals for agent registrations, activity, and ownership data.

Real-connectable via Microsoft Graph API (beta/copilot/agentRegistrations).
Requires Graph permission: AgentRegistration.Read.All.
Provide AGENT365_TENANT_ID and AGENT365_CLIENT_ID for live mode.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from control_plane.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorDefinition,
    ConnectorMode,
    ConnectorStatus,
    ControlPlaneTool,
    PlatformConnector,
)

_PLATFORM_ID = "agent365"
_CONNECTOR_ID = "agent365"

# ---------------------------------------------------------------------------
# Rich mock agent records — used by get_signals and execute_tool
# ---------------------------------------------------------------------------

_MOCK_AGENTS = [
    {
        "agent_id": "sales-followup-agent",
        "display_name": "Sales Follow-Up Agent",
        "owner": "alice@contoso.com",
        "lifecycle_stage": "Production",
        "risk_tier": "medium",
        "template_used": "foundry-sales-v2",
        "last_active": "2026-06-01T14:22:10Z",
        "interactions_7d": 2143,
        "evidence_coverage_pct": 92,
        "governance_recommendation": "Maintain current access. Schedule quarterly cost review.",
    },
    {
        "agent_id": "support-resolution-agent",
        "display_name": "Support Resolution Agent",
        "owner": "bob@contoso.com",
        "lifecycle_stage": "Production",
        "risk_tier": "high",
        "template_used": "foundry-support-v3",
        "last_active": "2026-06-02T09:05:33Z",
        "interactions_7d": 4871,
        "evidence_coverage_pct": 74,
        "governance_recommendation": "Governance review required: high-risk with partial evidence coverage.",
    },
    {
        "agent_id": "reporting-agent",
        "display_name": "Executive Reporting Agent",
        "owner": None,
        "lifecycle_stage": "Production",
        "risk_tier": "medium",
        "template_used": "foundry-reporting-v1",
        "last_active": "2026-05-29T11:44:00Z",
        "interactions_7d": 311,
        "evidence_coverage_pct": 55,
        "governance_recommendation": "Unowned agent in production — assign owner immediately.",
    },
    {
        "agent_id": "policy-research-agent",
        "display_name": "Policy Research Agent",
        "owner": "carol@contoso.com",
        "lifecycle_stage": "Staging",
        "risk_tier": "low",
        "template_used": "foundry-research-v1",
        "last_active": "2026-05-31T16:30:00Z",
        "interactions_7d": 88,
        "evidence_coverage_pct": 40,
        "governance_recommendation": "Block promotion. Evidence coverage below 50% — add audit logging.",
    },
    {
        "agent_id": "invoice-recovery-agent",
        "display_name": "Invoice Recovery Agent",
        "owner": "dave@contoso.com",
        "lifecycle_stage": "Production",
        "risk_tier": "high",
        "template_used": "foundry-finance-v2",
        "last_active": "2026-06-02T08:00:00Z",
        "interactions_7d": 673,
        "evidence_coverage_pct": 88,
        "governance_recommendation": "Maintain access. Quarterly financial audit required.",
    },
]

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.list_agent_registrations",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="list_agent_registrations",
        description="List all agents registered in the M365 Agent 365 registry.",
        input_schema={},
        output_schema={"agents": "array"},
        required_permissions=["AgentRegistration.Read.All"],
        signal_types_returned=["agent_registrations"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_agent_activity",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_agent_activity",
        description="Return recent activity metrics for registered agents.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"activity": "array"},
        required_permissions=["AgentRegistration.Read.All"],
        signal_types_returned=["agent_activity"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_ownership_coverage",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_ownership_coverage",
        description="Return agents without assigned owners or sponsors.",
        input_schema={},
        output_schema={"unowned_agents": "array", "coverage_pct": "number"},
        required_permissions=["AgentRegistration.Read.All"],
        signal_types_returned=["ownership_data", "agent_registrations"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class Agent365MockConnector(PlatformConnector):
    """Microsoft Agent 365 connector — mock implementation.

    A live implementation would use Graph API:
    GET /beta/copilot/agentRegistrations with Entra client credentials.
    """

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft Agent 365",
            description="Agent registry, activity, and ownership signals via Microsoft Graph.",
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.ENTRA_CLIENT_CREDENTIALS,
            base_url="https://graph.microsoft.com/beta",
            required_scopes=["https://graph.microsoft.com/.default"],
            supported_signal_types=["agent_registrations", "agent_activity", "ownership_data"],
            supported_tools=[t.name for t in _TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.tenant_id:
                errors.append("AGENT365_TENANT_ID is required for live mode.")
            if not config.client_id:
                errors.append("AGENT365_CLIENT_ID is required for live mode.")
            if not config.secret_ref:
                errors.append("AGENT365_CLIENT_SECRET_REF is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real Agent 365 API calls made.",
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_available_tools(self) -> List[ControlPlaneTool]:
        return _TOOLS

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        meta = self._source_metadata(
            source_mode=ConnectorMode.MOCK,
            connector_id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            confidence=0.7,
            data_quality_notes="Mock data.",
        )

        if "agent_registrations" in signal_requirements:
            unowned = [a for a in _MOCK_AGENTS if a["owner"] is None]
            signals.append({
                "signal_type": "agent_registrations",
                "platform_id": _PLATFORM_ID,
                "title": f"{len(_MOCK_AGENTS)} agents registered — {len(unowned)} missing owner assignment",
                "value": {
                    "severity": "medium",
                    "total_agents": len(_MOCK_AGENTS),
                    "agents_without_owner": len(unowned),
                    "agents": _MOCK_AGENTS,
                },
                "source_metadata": meta,
            })

        if "ownership_data" in signal_requirements:
            unowned = [{"agent_id": a["agent_id"]} for a in _MOCK_AGENTS if a["owner"] is None]
            owned_count = len(_MOCK_AGENTS) - len(unowned)
            coverage_pct = round(owned_count / len(_MOCK_AGENTS) * 100, 1)
            signals.append({
                "signal_type": "ownership_data",
                "platform_id": _PLATFORM_ID,
                "title": f"Ownership coverage: {coverage_pct:.0f}% ({owned_count} of {len(_MOCK_AGENTS)} agents have assigned owners)",
                "value": {
                    "severity": "medium",
                    "coverage_pct": coverage_pct,
                    "unowned_agents": unowned,
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "list_agent_registrations":
            return {
                "agents": _MOCK_AGENTS,
                "total": len(_MOCK_AGENTS),
                "source_mode": "mock",
            }
        if tool_name == "get_agent_activity":
            return {
                "activity": [
                    {"agent_id": a["agent_id"], "interactions_7d": a["interactions_7d"]}
                    for a in _MOCK_AGENTS
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_ownership_coverage":
            unowned = [{"agent_id": a["agent_id"]} for a in _MOCK_AGENTS if a["owner"] is None]
            owned_count = len(_MOCK_AGENTS) - len(unowned)
            return {
                "coverage_pct": round(owned_count / len(_MOCK_AGENTS) * 100, 1),
                "owned_count": owned_count,
                "total_agents": len(_MOCK_AGENTS),
                "unowned_agents": unowned,
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
