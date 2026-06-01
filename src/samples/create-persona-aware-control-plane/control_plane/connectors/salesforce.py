"""Salesforce mock connector.

Provides mock signals for opportunity pipeline, case resolution, revenue
impact, and customer health.

Real-connectable via Salesforce REST API using OAuth connected app.
Provide SALESFORCE_BASE_URL, SALESFORCE_CLIENT_ID, and a resolved secret
for SALESFORCE_CLIENT_SECRET_REF in live mode.
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

_PLATFORM_ID = "salesforce"
_CONNECTOR_ID = "salesforce"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_opportunity_pipeline",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_opportunity_pipeline",
        description="Return opportunity pipeline metrics influenced by agents.",
        input_schema={"period_days": {"type": "integer", "default": 30}},
        output_schema={"total_pipeline": "number", "agent_influenced_pct": "number"},
        required_permissions=["Opportunity.Read"],
        signal_types_returned=["opportunity_pipeline", "revenue_impact"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_case_resolution",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_case_resolution",
        description="Return case resolution time and agent-assisted resolution rate.",
        input_schema={"period_days": {"type": "integer", "default": 30}},
        output_schema={"avg_resolution_hours": "number", "agent_assisted_pct": "number"},
        required_permissions=["Case.Read"],
        signal_types_returned=["case_resolution"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class SalesforceMockConnector(PlatformConnector):
    """Salesforce connector — mock implementation."""

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Salesforce",
            description="Opportunity pipeline, case resolution, and revenue impact signals.",
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.OAUTH,
            base_url="",  # Set from SALESFORCE_BASE_URL in live mode
            required_scopes=["api"],
            supported_signal_types=["opportunity_pipeline", "revenue_impact", "case_resolution"],
            supported_tools=[t.name for t in _TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not config.base_url:
                errors.append("SALESFORCE_BASE_URL is required for live mode.")
            if not config.client_id:
                errors.append("SALESFORCE_CLIENT_ID is required for live mode.")
            if not config.secret_ref:
                errors.append("SALESFORCE_CLIENT_SECRET_REF is required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real Salesforce API calls made.",
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

        if "opportunity_pipeline" in signal_requirements or "revenue_impact" in signal_requirements:
            signals.append({
                "signal_type": "opportunity_pipeline",
                "platform_id": _PLATFORM_ID,
                "title": "Agent-influenced pipeline: $4.2M (14% of total) — 30 days",
                "value": {
                    "severity": "low",
                    "total_pipeline_usd": 30_000_000,
                    "agent_influenced_usd": 4_200_000,
                    "agent_influenced_pct": 14.0,
                    "period_days": 30,
                },
                "source_metadata": meta,
            })

        if "case_resolution" in signal_requirements:
            signals.append({
                "signal_type": "case_resolution",
                "platform_id": _PLATFORM_ID,
                "title": "Average case resolution: 3.2h (18% faster with agent assist)",
                "value": {
                    "severity": "low",
                    "avg_resolution_hours": 3.2,
                    "agent_assisted_pct": 42.0,
                    "improvement_pct": 18.0,
                    "period_days": 30,
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "get_opportunity_pipeline":
            return {
                "total_pipeline": 30_000_000,
                "agent_influenced_pct": 14.0,
                "source_mode": "mock",
            }
        if tool_name == "get_case_resolution":
            return {
                "avg_resolution_hours": 3.2,
                "agent_assisted_pct": 42.0,
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
