"""A365 mock connector — alias for Microsoft Agent 365.

``a365`` is the short platform ID used in persona relevant_platforms lists
and in platform_definitions.yaml.  This connector delegates all behaviour to
``Agent365MockConnector`` and simply re-brands the IDs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from control_plane.connectors.agent365 import Agent365MockConnector
from control_plane.connectors.base import (
    ConnectorDefinition,
    ConnectorMode,
    ConnectorStatus,
    ControlPlaneTool,
    AuthType,
)

_PLATFORM_ID = "a365"
_CONNECTOR_ID = "a365"


def _remap_tool(tool: ControlPlaneTool) -> ControlPlaneTool:
    """Return a copy of *tool* with platform/connector IDs rewritten to a365."""
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
        source_mode=ConnectorMode.MOCK,
    )


class A365MockConnector(Agent365MockConnector):
    """A365 connector — mock implementation (alias of Agent 365).

    Uses platform_id ``a365`` so persona signal-routing and KPI
    dependency queries can resolve against either ``agent365`` or ``a365``.
    """

    def get_definition(self) -> ConnectorDefinition:
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="A365 (Agent 365)",
            description="Agent registry, activity, and ownership signals (A365 alias for Agent 365).",
            mode=self._mode,
            status=ConnectorStatus.CONNECTED,
            auth_type=AuthType.ENTRA_CLIENT_CREDENTIALS,
            base_url="https://graph.microsoft.com/beta",
            required_scopes=["https://graph.microsoft.com/.default"],
            supported_signal_types=["agent_registrations", "agent_activity", "ownership_data"],
            supported_tools=[t.name for t in self.get_available_tools()],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_available_tools(self) -> List[ControlPlaneTool]:
        return [_remap_tool(t) for t in super().get_available_tools()]

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        signals = super().get_signals(signal_requirements, context)
        # Rewrite platform_id in every signal
        for s in signals:
            s["platform_id"] = _PLATFORM_ID
        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return super().execute_tool(tool_name, payload)
