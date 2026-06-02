"""A365 connector alias.

Provides the same mock data and behaviour as the Agent 365 connector,
but exposes the platform under the short name ``a365`` so users can
reference the connector/API consistently with that naming.
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

_PLATFORM_ID = "a365"
_CONNECTOR_ID = "a365"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.list_agent_registrations",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="list_agent_registrations",
        description="List all agents registered in the A365 registry.",
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


class A365MockConnector(PlatformConnector):
    """A365 connector — mock implementation."""

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="A365",
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
                errors.append("A365_TENANT_ID is required for live mode.")
            if not config.client_id:
                errors.append("A365_CLIENT_ID is required for live mode.")
            if not config.secret_ref:
                errors.append("A365_CLIENT_SECRET_REF is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real A365 API calls made.",
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
