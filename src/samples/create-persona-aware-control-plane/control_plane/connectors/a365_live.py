"""A365 live connector — alias for the live Microsoft Agent 365 connector.

Inherits ``Agent365LiveConnector`` and remaps all IDs from ``agent365`` to
``a365`` so the control plane can route A365-specific persona signals
independently of the base Agent 365 connector.

Activation:
  CONTROL_PLANE_A365_LIVE=true   (falls back to CONTROL_PLANE_AGENT365_LIVE)
  AGENT365_TENANT_ID / AGENT365_CLIENT_ID / AGENT365_CLIENT_SECRET  — same creds
"""
from __future__ import annotations

import copy
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from control_plane.connectors.agent365_live import Agent365LiveConnector
from control_plane.connectors.a365 import A365MockConnector
from control_plane.connectors.base import (
    ConnectorDefinition,
    ConnectorMode,
    ConnectorStatus,
    ControlPlaneTool,
    AuthType,
    PlatformConnector,
)

_PLATFORM_ID = "a365"
_CONNECTOR_ID = "a365"
_GRAPH_BASE = "https://graph.microsoft.com"


def _live_enabled() -> bool:
    # Honour A365-specific flag first, then fall back to agent365 flag
    env = (
        os.environ.get("CONTROL_PLANE_A365_LIVE", "")
        or os.environ.get("CONTROL_PLANE_AGENT365_LIVE", "")
    )
    return env.lower() in ("true", "1", "yes")


def _remap_tool(tool: ControlPlaneTool) -> ControlPlaneTool:
    return ControlPlaneTool(
        id=tool.id.replace("agent365.", f"{_PLATFORM_ID}."),
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        output_schema=tool.output_schema,
        required_permissions=tool.required_permissions,
        signal_types_returned=tool.signal_types_returned,
        source_mode=tool.source_mode,
        required_roles=getattr(tool, "required_roles", []),
        sensitive_data_level=getattr(tool, "sensitive_data_level", "low"),
    )


class A365LiveConnector(Agent365LiveConnector):
    """Live A365 connector — remaps agent365 → a365 for all IDs."""

    def get_definition(self) -> ConnectorDefinition:
        base = super().get_definition()
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="A365 (Agent 365 Live)",
            description=base.description,
            mode=base.mode,
            status=base.status,
            auth_type=base.auth_type,
            base_url=base.base_url,
            required_scopes=base.required_scopes,
            supported_signal_types=base.supported_signal_types,
            supported_tools=base.supported_tools,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_available_tools(self) -> List[ControlPlaneTool]:
        return [_remap_tool(t) for t in super().get_available_tools()]

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        signals = super().get_signals(signal_requirements, context)
        for s in signals:
            s["platform_id"] = _PLATFORM_ID
            if "source_metadata" in s and isinstance(s["source_metadata"], dict):
                s["source_metadata"] = copy.copy(s["source_metadata"])
                s["source_metadata"]["connector_id"] = _CONNECTOR_ID
                s["source_metadata"]["platform_id"] = _PLATFORM_ID
        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return super().execute_tool(tool_name, payload)


def get_a365_connector() -> PlatformConnector:
    """Return live A365 connector when enabled, else mock."""
    if _live_enabled():
        return A365LiveConnector()
    return A365MockConnector()
