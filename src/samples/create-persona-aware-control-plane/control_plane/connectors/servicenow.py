"""ServiceNow mock connector.

Provides mock signals for incidents, change requests, SLA compliance,
and problem records.

Real-connectable via ServiceNow REST Table API using API key or OAuth.
Provide SERVICENOW_BASE_URL and SERVICENOW_API_KEY_REF for live mode.
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

_PLATFORM_ID = "servicenow"
_CONNECTOR_ID = "servicenow"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_open_incidents",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_open_incidents",
        description="Return open incidents from ServiceNow, optionally filtered by priority.",
        input_schema={"priority": {"type": "string", "default": "all"}},
        output_schema={"incidents": "array"},
        required_permissions=["itil"],
        signal_types_returned=["incidents"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_sla_compliance",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_sla_compliance",
        description="Return SLA compliance metrics for the period.",
        input_schema={"period_days": {"type": "integer", "default": 30}},
        output_schema={"compliance_pct": "number", "breached": "integer"},
        required_permissions=["itil"],
        signal_types_returned=["sla_compliance"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_change_requests",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_change_requests",
        description="Return pending and recent change requests related to agent infrastructure.",
        input_schema={"state": {"type": "string", "default": "all"}},
        output_schema={"changes": "array"},
        required_permissions=["itil"],
        signal_types_returned=["change_requests"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class ServiceNowMockConnector(PlatformConnector):
    """ServiceNow connector — mock implementation."""

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="ServiceNow",
            description="Incidents, change requests, SLA compliance via ServiceNow REST API.",
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.API_KEY,
            base_url="",  # Set from SERVICENOW_BASE_URL in live mode
            required_scopes=[],
            supported_signal_types=["incidents", "change_requests", "sla_compliance"],
            supported_tools=[t.name for t in _TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.base_url:
                errors.append("SERVICENOW_BASE_URL is required for live mode.")
            if not config.secret_ref:
                errors.append("SERVICENOW_API_KEY_REF is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real ServiceNow API calls made.",
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

        if "incidents" in signal_requirements:
            signals.append({
                "signal_type": "incidents",
                "platform_id": _PLATFORM_ID,
                "title": "2 open P2 security incidents (>24h unresolved)",
                "value": {
                    "severity": "high",
                    "open_p1": 0,
                    "open_p2": 2,
                    "open_p3": 7,
                    "oldest_open_hours": 38,
                },
                "source_metadata": meta,
            })

        if "sla_compliance" in signal_requirements:
            signals.append({
                "signal_type": "sla_compliance",
                "platform_id": _PLATFORM_ID,
                "title": "SLA compliance 93% — below 95% target",
                "value": {
                    "severity": "medium",
                    "compliance_pct": 93.0,
                    "breached": 4,
                    "period_days": 30,
                },
                "source_metadata": meta,
            })

        if "change_requests" in signal_requirements:
            signals.append({
                "signal_type": "change_requests",
                "platform_id": _PLATFORM_ID,
                "title": "3 pending change requests for agent infrastructure",
                "value": {
                    "severity": "low",
                    "pending": 3,
                    "approved": 1,
                    "failed_last_30d": 1,
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "get_open_incidents":
            return {
                "incidents": [
                    {"number": "INC0012345", "priority": "2", "short_description": "Agent auth failure"},
                    {"number": "INC0012346", "priority": "2", "short_description": "Data access anomaly"},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_sla_compliance":
            return {"compliance_pct": 93.0, "breached": 4, "source_mode": "mock"}
        if tool_name == "get_change_requests":
            return {
                "changes": [
                    {"number": "CHG0009001", "state": "assess", "short_description": "Agent runtime upgrade"},
                ],
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
