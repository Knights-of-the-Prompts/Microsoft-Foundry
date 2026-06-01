"""Azure mock connector.

Provides mock signals for resource health, cost data, security events,
and compliance status.

Real-connectable via Azure SDK (azure-mgmt-* + azure-identity).
Uses DefaultAzureCredential — supports az login, managed identity, and
workload identity without code changes.

To switch to live mode set CONTROL_PLANE_MODE=live and provide
AZURE_SUBSCRIPTION_ID and AZURE_TENANT_ID (or rely on az login).
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

_PLATFORM_ID = "azure"
_CONNECTOR_ID = "azure"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.list_resource_health",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="list_resource_health",
        description="List Azure resource health events for the subscription.",
        input_schema={"resource_group": {"type": "string", "required": False}},
        output_schema={"resources": "array"},
        required_permissions=["Microsoft.ResourceHealth/availabilityStatuses/read"],
        signal_types_returned=["resource_health"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_cost_summary",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_cost_summary",
        description="Return cost summary for the billing period, optionally filtered by tag.",
        input_schema={
            "period": {"type": "string", "default": "BillingMonth"},
            "tag_filter": {"type": "object", "required": False},
        },
        output_schema={"total_cost": "number", "currency": "string", "by_service": "object"},
        required_permissions=["Microsoft.CostManagement/query/action"],
        signal_types_returned=["cost_data"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_security_events",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_security_events",
        description=(
            "Return recent security events from Microsoft Defender / Azure Security Center."
        ),
        input_schema={"severity": {"type": "string", "default": "High"}},
        output_schema={"events": "array"},
        required_permissions=["Microsoft.Security/alerts/read"],
        signal_types_returned=["security_events"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_anomalous_signins",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_anomalous_signins",
        description="Return anomalous sign-in events for service principals.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"sign_ins": "array"},
        required_permissions=["SecurityEvents.Read.All"],
        signal_types_returned=["security_events", "user_activity"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class AzureMockConnector(PlatformConnector):
    """Azure connector — mock implementation.

    Returns deterministic demo data.  A live implementation would use:
    - azure-mgmt-resourcehealth for resource health
    - azure-mgmt-costmanagement for cost queries
    - azure-monitor-query for log analytics / sign-in events
    All with DefaultAzureCredential (no code changes for managed identity).
    """

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft Azure",
            description=(
                "Resource health, cost, security events, and compliance via Azure SDK."
            ),
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.AZURE_DEFAULT_CREDENTIAL,
            base_url="https://management.azure.com",
            required_scopes=["https://management.azure.com/.default"],
            supported_signal_types=[
                "resource_health",
                "cost_data",
                "security_events",
                "compliance_status",
                "user_activity",
            ],
            supported_tools=[t.name for t in _TOOLS],
            health_check_endpoint="/subscriptions",
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.subscription_id:
                errors.append("AZURE_SUBSCRIPTION_ID is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real Azure API calls made.",
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
            data_quality_notes="Mock data — configure live Azure connector for real signals.",
        )

        if "security_events" in signal_requirements:
            signals.append({
                "signal_type": "security_events",
                "platform_id": _PLATFORM_ID,
                "title": "3 anomalous sign-in events detected for service principals",
                "value": {
                    "severity": "high",
                    "anomalous_signins": 3,
                    "unauthorized_access_attempts": 2,
                    "affected_principals": [
                        "sp-foundry-agent@contoso.com",
                        "sp-reporting-agent@contoso.com",
                    ],
                },
                "source_metadata": meta,
            })

        if "cost_data" in signal_requirements:
            signals.append({
                "signal_type": "cost_data",
                "platform_id": _PLATFORM_ID,
                "title": "Agent infrastructure cost — $1,240 MTD",
                "value": {
                    "total_cost": 1240.00,
                    "currency": "USD",
                    "period": "BillingMonth",
                    "by_service": {
                        "Azure OpenAI": 820.00,
                        "Azure Kubernetes Service": 310.00,
                        "Storage": 110.00,
                    },
                },
                "source_metadata": meta,
            })

        if "resource_health" in signal_requirements:
            signals.append({
                "signal_type": "resource_health",
                "platform_id": _PLATFORM_ID,
                "title": "All agent compute resources healthy",
                "value": {
                    "severity": "low",
                    "healthy": 12,
                    "degraded": 0,
                    "unavailable": 0,
                    "unknown": 1,
                },
                "source_metadata": meta,
            })

        if "compliance_status" in signal_requirements:
            signals.append({
                "signal_type": "compliance_status",
                "platform_id": _PLATFORM_ID,
                "title": "2 policy compliance failures in subscription",
                "value": {
                    "severity": "medium",
                    "non_compliant_resources": 2,
                    "policy_names": ["Require TLS 1.2", "Audit diagnostic settings"],
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "list_resource_health":
            return {
                "resources": [
                    {"id": "/subscriptions/xxx/resourceGroups/rg-agents", "status": "Available"},
                    {"id": "/subscriptions/xxx/resourceGroups/rg-foundry", "status": "Available"},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_cost_summary":
            return {
                "total_cost": 1240.00,
                "currency": "USD",
                "period": payload.get("period", "BillingMonth"),
                "by_service": {"Azure OpenAI": 820.00, "AKS": 310.00, "Storage": 110.00},
                "source_mode": "mock",
            }
        if tool_name == "get_security_events":
            return {
                "events": [
                    {"id": "alert-001", "severity": "High", "title": "Anomalous sign-in detected"},
                    {"id": "alert-002", "severity": "High", "title": "Unauthorized resource access attempt"},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_anomalous_signins":
            return {
                "sign_ins": [
                    {"principal": "sp-foundry-agent", "location": "Unknown", "risk": "high"},
                ],
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
