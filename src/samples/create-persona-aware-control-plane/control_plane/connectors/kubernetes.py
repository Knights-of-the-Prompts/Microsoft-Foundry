"""Kubernetes mock connector.

Provides mock signals for pod health, deployment status, and namespace
resource utilisation.

Real-connectable via the kubernetes-client Python library using kubeconfig
or in-cluster service account.
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

_PLATFORM_ID = "kubernetes"
_CONNECTOR_ID = "kubernetes"

_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_deployment_status",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_deployment_status",
        description="Return deployment rollout status across agent namespaces.",
        input_schema={"namespace": {"type": "string", "default": "agents"}},
        output_schema={"deployments": "array"},
        required_permissions=["get deployments"],
        signal_types_returned=["deployment_status"],
        source_mode=ConnectorMode.MOCK,
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_pod_health",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_pod_health",
        description="Return pod health and restart counts for agent workloads.",
        input_schema={"namespace": {"type": "string", "default": "agents"}},
        output_schema={"pods": "array"},
        required_permissions=["get pods"],
        signal_types_returned=["resource_health", "deployment_status"],
        source_mode=ConnectorMode.MOCK,
    ),
]


class KubernetesMockConnector(PlatformConnector):
    """Kubernetes connector — mock implementation."""

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Kubernetes",
            description="Pod health, deployment status, and namespace resource signals.",
            mode=ConnectorMode.MOCK,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.NONE,
            base_url="",
            required_scopes=[],
            supported_signal_types=["deployment_status", "resource_health", "resource_utilization"],
            supported_tools=[t.name for t in _TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        return []

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "latency_ms": None,
            "message": "Mock connector — no real Kubernetes API calls made.",
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

        if "deployment_status" in signal_requirements:
            signals.append({
                "signal_type": "deployment_status",
                "platform_id": _PLATFORM_ID,
                "title": "All agent deployments running — 0 rollout failures",
                "value": {
                    "severity": "low",
                    "total_deployments": 8,
                    "available": 8,
                    "unavailable": 0,
                    "namespace": "agents",
                },
                "source_metadata": meta,
            })

        if "resource_health" in signal_requirements:
            signals.append({
                "signal_type": "resource_health",
                "platform_id": _PLATFORM_ID,
                "title": "1 pod restarted 4 times in last hour (OOMKilled)",
                "value": {
                    "severity": "medium",
                    "pods_running": 24,
                    "pods_restarted": 1,
                    "restart_reason": "OOMKilled",
                    "affected_pod": "sales-followup-agent-6d8c9b-xkzpt",
                },
                "source_metadata": meta,
            })

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "get_deployment_status":
            return {
                "deployments": [
                    {"name": "sales-followup-agent", "replicas": 2, "available": 2},
                    {"name": "support-resolution-agent", "replicas": 3, "available": 3},
                ],
                "source_mode": "mock",
            }
        if tool_name == "get_pod_health":
            return {
                "pods": [
                    {"name": "sales-followup-agent-6d8c9b-xkzpt", "restarts": 4, "status": "Running"},
                ],
                "source_mode": "mock",
            }
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}
