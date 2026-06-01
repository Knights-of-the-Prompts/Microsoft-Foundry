"""Microsoft Foundry mock connector.

Provides mock signals for agent invocations, model usage, and project health.

Real-connectable via azure-ai-projects using DefaultAzureCredential.
Provide FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_SUBSCRIPTION_ID for live mode.
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

_PLATFORM_ID = "foundry"
_CONNECTOR_ID = "foundry"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_agent_invocations",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_agent_invocations",
        description="Return agent invocation counts and error rates from Microsoft Foundry.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"agents": "array"},
        required_permissions=["AIProject.Read"],
        signal_types_returned=["agent_invocations"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_model_usage",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_model_usage",
        description="Return token usage and cost by model deployment in the Foundry project.",
        input_schema={"period_days": {"type": "integer", "default": 7}},
        output_schema={"models": "array", "total_tokens": "integer"},
        required_permissions=["AIProject.Read"],
        signal_types_returned=["model_usage"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_project_health",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_project_health",
        description="Return health status of the Foundry project and its dependencies.",
        input_schema={},
        output_schema={"status": "string", "issues": "array"},
        required_permissions=["AIProject.Read"],
        signal_types_returned=["project_health"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class FoundryMockConnector(PlatformConnector):
    """Microsoft Foundry connector — mock implementation.

    A live implementation would use azure-ai-projects + DefaultAzureCredential
    to query project diagnostics, model usage, and agent versions.
    """

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft Foundry",
            description="Agent invocations, model usage, and project health via azure-ai-projects.",
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.AZURE_DEFAULT_CREDENTIAL,
            base_url="",  # Set from FOUNDRY_PROJECT_ENDPOINT in live mode
            required_scopes=["https://management.azure.com/.default"],
            supported_signal_types=["agent_invocations", "model_usage", "project_health"],
            supported_tools=[t.name for t in _TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.base_url:
                errors.append("FOUNDRY_PROJECT_ENDPOINT is required for live mode.")
            if not config.subscription_id:
                errors.append("FOUNDRY_SUBSCRIPTION_ID is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real Foundry API calls made.",
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
            data_quality_notes="Mock data — configure FOUNDRY_PROJECT_ENDPOINT for live.",
        )

        if "agent_invocations" in signal_requirements:
            signals.append({
                "signal_type": "agent_invocations",
                "platform_id": _PLATFORM_ID,
                "title": "3 agents — 4,820 invocations last 7 days, 0.3% error rate",
                "value": {
                    "severity": "low",
                    "total_invocations": 4820,
                    "error_rate_pct": 0.3,
                    "agents": [
                        {"agent_id": "sales-followup-agent", "invocations": 2100},
                        {"agent_id": "support-resolution-agent", "invocations": 1980},
                        {"agent_id": "reporting-agent", "invocations": 740},
                    ],
                    "period_days": 7,
                },
                "source_metadata": meta,
            })

        if "model_usage" in signal_requirements:
            signals.append({
                "signal_type": "model_usage",
                "platform_id": _PLATFORM_ID,
                "title": "1.2M tokens used across gpt-4o and gpt-4o-mini (7 days)",
                "value": {
                    "total_tokens": 1_200_000,
                    "models": [
                        {"model": "gpt-4o", "tokens": 900_000, "estimated_cost_usd": 27.00},
                        {"model": "gpt-4o-mini", "tokens": 300_000, "estimated_cost_usd": 0.45},
                    ],
                },
                "source_metadata": meta,
            })

        if "project_health" in signal_requirements:
            signals.append({
                "signal_type": "project_health",
                "platform_id": _PLATFORM_ID,
                "title": "Foundry project healthy — no configuration issues",
                "value": {"status": "healthy", "issues": [], "agent_count": 3},
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "get_agent_invocations":
            return {
                "agents": [
                    {"agent_id": "sales-followup-agent", "invocations": 2100, "errors": 6},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_model_usage":
            return {
                "total_tokens": 1_200_000,
                "models": [{"model": "gpt-4o", "tokens": 900_000}],
                "source_mode": "mock",
            }
        if tool_name == "get_project_health":
            return {"status": "healthy", "issues": [], "source_mode": "mock"}
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
