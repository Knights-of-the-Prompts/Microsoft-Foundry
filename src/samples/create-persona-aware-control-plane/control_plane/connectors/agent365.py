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
            mode=ConnectorMode.MOCK,
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
            signals.append({
                "signal_type": "agent_registrations",
                "platform_id": _PLATFORM_ID,
                "title": "5 agents registered — 1 missing owner assignment",
                "value": {
                    "severity": "medium",
                    "total_agents": 5,
                    "agents_without_owner": 1,
                    "agents": [
                        {"agent_id": "sales-followup-agent", "owner": "alice@contoso.com"},
                        {"agent_id": "support-resolution-agent", "owner": "bob@contoso.com"},
                        {"agent_id": "reporting-agent", "owner": None},
                    ],
                },
                "source_metadata": meta,
            })

        if "ownership_data" in signal_requirements:
            signals.append({
                "signal_type": "ownership_data",
                "platform_id": _PLATFORM_ID,
                "title": "Ownership coverage: 80% (4 of 5 agents have assigned owners)",
                "value": {
                    "severity": "medium",
                    "coverage_pct": 80.0,
                    "unowned_agents": [{"agent_id": "reporting-agent"}],
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "list_agent_registrations":
            return {
                "agents": [
                    {"agent_id": "sales-followup-agent", "status": "active"},
                    {"agent_id": "support-resolution-agent", "status": "active"},
                    {"agent_id": "reporting-agent", "status": "active"},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_agent_activity":
            return {
                "activity": [
                    {"agent_id": "sales-followup-agent", "interactions": 2100},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_ownership_coverage":
            return {
                "coverage_pct": 80.0,
                "unowned_agents": [{"agent_id": "reporting-agent"}],
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
