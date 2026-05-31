"""Microsoft 365 mock connector.

Provides mock signals for user activity, collaboration data, Teams usage,
email volume, and external file sharing.

Real-connectable via Microsoft Graph API using Entra client credentials.
To switch to live mode set CONTROL_PLANE_MODE=live (or hybrid) and provide
M365_TENANT_ID, M365_CLIENT_ID, and a resolved secret for M365_CLIENT_SECRET_REF.
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

_PLATFORM_ID = "microsoft365"
_CONNECTOR_ID = "microsoft365"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_user_activity",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_user_activity",
        description="Return recent user activity metrics from Microsoft 365.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"active_users": "integer", "inactive_users": "integer"},
        required_permissions=["Reports.Read.All"],
        signal_types_returned=["user_activity"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_external_shares",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_external_shares",
        description=(
            "List files shared externally without a sensitivity label in SharePoint/OneDrive."
        ),
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"files": "array"},
        required_permissions=["Sites.Read.All", "Reports.Read.All"],
        signal_types_returned=["user_activity", "compliance_status"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_teams_usage",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_teams_usage",
        description="Return Teams meeting and messaging usage metrics.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"total_meetings": "integer", "total_messages": "integer"},
        required_permissions=["Reports.Read.All"],
        signal_types_returned=["collaboration_data"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class Microsoft365MockConnector(PlatformConnector):
    """Microsoft 365 connector — mock implementation.

    Returns deterministic demo data.  Implements the same PlatformConnector
    interface as the future live Graph API connector so it can be swapped at
    runtime without changes to the ToolRegistry or KPI Agent.
    """

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft 365",
            description="User activity, collaboration, compliance signals via Microsoft Graph.",
            mode=ConnectorMode.MOCK,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.ENTRA_CLIENT_CREDENTIALS,
            base_url="https://graph.microsoft.com/v1.0",
            required_scopes=["https://graph.microsoft.com/.default"],
            supported_signal_types=["user_activity", "collaboration_data", "compliance_status"],
            supported_tools=[t.name for t in _TOOLS],
            health_check_endpoint="/v1.0/$metadata",
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.tenant_id:
                errors.append("M365_TENANT_ID is required for live mode.")
            if not config.client_id:
                errors.append("M365_CLIENT_ID is required for live mode.")
            if not config.secret_ref:
                errors.append("M365_CLIENT_SECRET_REF is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real API calls made.",
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
            data_quality_notes="Mock data — configure live M365 connector for real signals.",
        )

        if "user_activity" in signal_requirements:
            signals.append({
                "signal_type": "user_activity",
                "platform_id": _PLATFORM_ID,
                "title": "15 files shared externally without classification labels",
                "value": {
                    "severity": "medium",
                    "external_shares_without_label": 15,
                    "period_days": 7,
                    "top_sharers": ["alice@contoso.com", "bob@contoso.com"],
                },
                "source_metadata": meta,
            })

        if "compliance_status" in signal_requirements:
            signals.append({
                "signal_type": "compliance_status",
                "platform_id": _PLATFORM_ID,
                "title": "DLP policy violations — 3 incidents last 7 days",
                "value": {
                    "severity": "medium",
                    "dlp_violations": 3,
                    "unclassified_documents": 42,
                    "period_days": 7,
                },
                "source_metadata": meta,
            })

        if "collaboration_data" in signal_requirements:
            signals.append({
                "signal_type": "collaboration_data",
                "platform_id": _PLATFORM_ID,
                "title": "Teams usage — 487 meetings, 12,340 messages (7 days)",
                "value": {
                    "total_meetings": 487,
                    "total_messages": 12340,
                    "active_users": 234,
                    "period_days": 7,
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "get_user_activity":
            return {
                "active_users": 234,
                "inactive_users": 12,
                "external_shares_without_label": 15,
                "period_days": payload.get("period_days", 7),
                "source_mode": "mock",
            }
        if tool_name == "get_external_shares":
            return {
                "files": [
                    {"name": "Q4-Financials.xlsx", "owner": "alice@contoso.com", "shared_with": "external"},
                    {"name": "Product-Roadmap.pptx", "owner": "bob@contoso.com", "shared_with": "external"},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_teams_usage":
            return {
                "total_meetings": 487,
                "total_messages": 12340,
                "period_days": payload.get("period_days", 7),
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
