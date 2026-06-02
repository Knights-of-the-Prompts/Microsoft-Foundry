"""Live A365 connector alias.

Wraps the Agent 365 live/mock connector behaviour and remaps connector/tool
metadata so the control plane can expose the same API under platform id
``a365``.
"""
from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List

from control_plane.connectors.a365 import A365MockConnector
from control_plane.connectors.agent365_live import Agent365LiveConnector
from control_plane.connectors.base import ConnectorDefinition, PlatformConnector

_PLATFORM_ID = "a365"
_CONNECTOR_ID = "a365"


def _live_enabled() -> bool:
    flag = os.environ.get("CONTROL_PLANE_A365_LIVE", "")
    if not flag:
        flag = os.environ.get("CONTROL_PLANE_AGENT365_LIVE", "")
    return flag.lower() in ("true", "1", "yes")


class A365LiveConnector(Agent365LiveConnector):
    """Live A365 connector.

    Inherits Graph API call implementation from Agent365LiveConnector and
    remaps metadata from ``agent365`` to ``a365``.
    """

    def get_definition(self) -> ConnectorDefinition:
        base = super().get_definition()
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="A365 (Live)",
            description=base.description,
            mode=base.mode,
            status=base.status,
            auth_type=base.auth_type,
            base_url=base.base_url,
            required_scopes=base.required_scopes,
            supported_signal_types=base.supported_signal_types,
            supported_tools=[
                t.replace("agent365", "a365") for t in base.supported_tools
            ],
            health_check_endpoint=base.health_check_endpoint,
            last_checked_at=datetime.now(timezone.utc).isoformat(),
            error_message=base.error_message,
        )

    def get_available_tools(self):
        tools = super().get_available_tools()
        remapped = []
        for tool in tools:
            t = deepcopy(tool)
            t.id = t.id.replace("agent365.", "a365.")
            t.connector_id = _CONNECTOR_ID
            t.platform_id = _PLATFORM_ID
            remapped.append(t)
        return remapped

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = super().execute_tool(tool_name, payload)
        return self._rewrite_payload_platform(result)

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        signals = super().get_signals(signal_requirements, context)
        return [self._rewrite_signal_platform(sig) for sig in signals]

    @staticmethod
    def _rewrite_signal_platform(signal: Dict[str, Any]) -> Dict[str, Any]:
        patched = deepcopy(signal)
        patched["platform_id"] = _PLATFORM_ID
        meta = patched.get("source_metadata")
        if isinstance(meta, dict):
            meta["platform_id"] = _PLATFORM_ID
            meta["connector_id"] = _CONNECTOR_ID
        return patched

    @staticmethod
    def _rewrite_payload_platform(payload: Dict[str, Any]) -> Dict[str, Any]:
        patched = deepcopy(payload)
        if isinstance(patched, dict):
            if patched.get("platform_id") == "agent365":
                patched["platform_id"] = _PLATFORM_ID
            if patched.get("connector_id") == "agent365":
                patched["connector_id"] = _CONNECTOR_ID
        return patched


def get_a365_connector() -> PlatformConnector:
    """Return a live A365 connector when enabled, else the A365 mock connector."""
    if _live_enabled():
        return A365LiveConnector()
    return A365MockConnector()
