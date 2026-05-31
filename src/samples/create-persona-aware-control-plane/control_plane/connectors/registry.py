"""Tool Registry — central capability hub for the control plane.

The ToolRegistry is the single source of truth for what tools are available
at runtime.  The KPI Agent queries the registry to discover tools, then uses
them to gather signals and build weekly digests.

Key behaviours:
- Connectors are registered by platform_id; re-registering replaces the old one.
- list_tools() returns a flat list across all registered connectors.
- execute_tool() routes a call to the owning connector.
- capability_summary() provides a human-readable overview of registered
  connectors and their current mode (mock/live/hybrid).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from control_plane.connectors.base import (
    ConnectorDefinition,
    ConnectorMode,
    ControlPlaneTool,
    PlatformConnector,
)


class ToolRegistry:
    """Central registry of platform connectors and their exposed tools.

    Usage::

        registry = ToolRegistry()
        for cls in ALL_CONNECTORS:
            registry.register(cls())

        # Discover all tools
        for tool in registry.list_tools():
            print(f"[{tool.source_mode.value}] {tool.platform_id}: {tool.name}")

        # Execute a specific tool
        result = registry.execute_tool("azure.list_resource_health", payload={})
    """

    def __init__(self) -> None:
        self._connectors: Dict[str, PlatformConnector] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, connector: PlatformConnector) -> None:
        """Register a connector.  Re-registering the same platform_id replaces
        the previous connector (enables mock → live swap at runtime).
        """
        definition = connector.get_definition()
        self._connectors[definition.platform_id] = connector

    def unregister(self, platform_id: str) -> None:
        """Remove a connector from the registry."""
        self._connectors.pop(platform_id, None)

    # ------------------------------------------------------------------
    # Connector queries
    # ------------------------------------------------------------------

    def list_connectors(self) -> List[ConnectorDefinition]:
        """Return the definition of every registered connector."""
        return [c.get_definition() for c in self._connectors.values()]

    def get_connector(self, platform_id: str) -> Optional[PlatformConnector]:
        """Return the connector for a given platform, or None."""
        return self._connectors.get(platform_id)

    # ------------------------------------------------------------------
    # Tool queries
    # ------------------------------------------------------------------

    def list_tools(self, platform_id: Optional[str] = None) -> List[ControlPlaneTool]:
        """Return all available, enabled tools.

        Pass ``platform_id`` to filter to a single connector.
        """
        if platform_id is not None:
            if platform_id not in self._connectors:
                return []
            connectors = [self._connectors[platform_id]]
        else:
            connectors = list(self._connectors.values())
        tools: List[ControlPlaneTool] = []
        for connector in connectors:
            try:
                tools.extend(t for t in connector.get_available_tools() if t.enabled)
            except Exception:
                pass
        return tools

    def get_tool(self, tool_id: str) -> Optional[ControlPlaneTool]:
        """Return a specific tool by its fully qualified id, or None."""
        for tool in self.list_tools():
            if tool.id == tool_id:
                return tool
        return None

    def tools_for_signal_types(self, signal_types: List[str]) -> List[ControlPlaneTool]:
        """Return all tools that can return any of the requested signal types."""
        return [
            tool
            for tool in self.list_tools()
            if any(st in tool.signal_types_returned for st in signal_types)
        ]

    # ------------------------------------------------------------------
    # Tool execution
    # ------------------------------------------------------------------

    def execute_tool(
        self, tool_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a tool by id, routing to the owning connector.

        Returns a result dict.  On unknown tool or connector error, returns
        a dict with an ``"error"`` key.
        """
        tool = self.get_tool(tool_id)
        if tool is None:
            return {"error": f"Tool '{tool_id}' not found in registry."}

        connector = self._connectors.get(tool.platform_id)
        if connector is None:
            return {"error": f"Connector for platform '{tool.platform_id}' not found."}

        try:
            result = connector.execute_tool(tool.name, payload)
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}

        result["_tool_id"] = tool_id
        result["_source_mode"] = tool.source_mode.value
        return result

    # ------------------------------------------------------------------
    # Signal gathering
    # ------------------------------------------------------------------

    def gather_signals(
        self,
        signal_requirements: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Gather signals matching ``signal_requirements`` from all connectors.

        Each connector contributes only the signals it supports.
        The KPI Agent calls this to collect data before generating a digest.
        """
        context = context or {}
        signals: List[Dict[str, Any]] = []
        for connector in self._connectors.values():
            definition = connector.get_definition()
            relevant = [
                sr
                for sr in signal_requirements
                if sr in definition.supported_signal_types
            ]
            if not relevant:
                continue
            try:
                batch = connector.get_signals(relevant, context)
                signals.extend(batch)
            except Exception:
                pass
        return signals

    # ------------------------------------------------------------------
    # Capability summary
    # ------------------------------------------------------------------

    def capability_summary(self) -> Dict[str, Any]:
        """Return a human-readable summary of all registered connectors and tools.

        The KPI Agent can include this in its context window when deciding
        which tools to use.
        """
        connectors_summary = []
        for definition in self.list_connectors():
            tools = self.list_tools(platform_id=definition.platform_id)
            connectors_summary.append(
                {
                    "platform_id": definition.platform_id,
                    "name": definition.name,
                    "mode": definition.mode.value,
                    "status": definition.status.value,
                    "tool_count": len(tools),
                    "signal_types": definition.supported_signal_types,
                    "tools": [
                        {
                            "id": t.id,
                            "name": t.name,
                            "source_mode": t.source_mode.value,
                            "signal_types": t.signal_types_returned,
                        }
                        for t in tools
                    ],
                }
            )

        live_count = sum(
            1 for d in self.list_connectors() if d.mode == ConnectorMode.LIVE
        )
        mock_count = sum(
            1 for d in self.list_connectors() if d.mode == ConnectorMode.MOCK
        )
        return {
            "total_connectors": len(self._connectors),
            "live_connectors": live_count,
            "mock_connectors": mock_count,
            "total_tools": len(self.list_tools()),
            "connectors": connectors_summary,
        }
