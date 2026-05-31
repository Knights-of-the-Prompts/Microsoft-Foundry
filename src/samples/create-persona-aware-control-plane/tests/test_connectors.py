"""Interface compliance tests for all platform connectors.

These tests verify that every connector correctly implements the
PlatformConnector interface contract.  They run entirely in mock mode —
no credentials or external API calls are required.

Run with:
    python -m pytest tests/ -v
"""
from __future__ import annotations

import pytest

from control_plane.connectors import ALL_CONNECTORS
from control_plane.connectors.base import (
    ConnectorConfig,
    ConnectorDefinition,
    ConnectorMode,
    ConnectorStatus,
    ControlPlaneTool,
    PlatformConnector,
)
from control_plane.connectors.registry import ToolRegistry
from control_plane.kpi_agent.agent import KPIAgent
from control_plane.models.personas import PERSONA_CATALOGUE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    for cls in ALL_CONNECTORS:
        reg.register(cls())
    return reg


@pytest.fixture(params=ALL_CONNECTORS)
def connector(request) -> PlatformConnector:
    return request.param()


# ---------------------------------------------------------------------------
# ConnectorDefinition contract
# ---------------------------------------------------------------------------


class TestConnectorDefinition:
    def test_returns_connector_definition(self, connector: PlatformConnector) -> None:
        defn = connector.get_definition()
        assert isinstance(defn, ConnectorDefinition)

    def test_platform_id_not_empty(self, connector: PlatformConnector) -> None:
        assert connector.get_definition().platform_id

    def test_mode_is_mock_in_phase1(self, connector: PlatformConnector) -> None:
        assert connector.get_definition().mode == ConnectorMode.MOCK

    def test_status_not_error(self, connector: PlatformConnector) -> None:
        assert connector.get_definition().status != ConnectorStatus.ERROR

    def test_supported_signal_types_non_empty(self, connector: PlatformConnector) -> None:
        assert connector.get_definition().supported_signal_types


# ---------------------------------------------------------------------------
# Health check contract
# ---------------------------------------------------------------------------


class TestHealth:
    def test_get_health_does_not_raise(self, connector: PlatformConnector) -> None:
        health = connector.get_health()
        assert isinstance(health, dict)

    def test_health_has_status_key(self, connector: PlatformConnector) -> None:
        health = connector.get_health()
        assert "status" in health

    def test_health_has_checked_at(self, connector: PlatformConnector) -> None:
        health = connector.get_health()
        assert "checked_at" in health


# ---------------------------------------------------------------------------
# Tools contract
# ---------------------------------------------------------------------------


class TestTools:
    def test_returns_list_of_tools(self, connector: PlatformConnector) -> None:
        tools = connector.get_available_tools()
        assert isinstance(tools, list)

    def test_tools_are_control_plane_tool_instances(
        self, connector: PlatformConnector
    ) -> None:
        for tool in connector.get_available_tools():
            assert isinstance(tool, ControlPlaneTool)

    def test_tool_ids_unique(self, connector: PlatformConnector) -> None:
        tool_ids = [t.id for t in connector.get_available_tools()]
        assert len(tool_ids) == len(set(tool_ids)), "Duplicate tool IDs detected."

    def test_tool_platform_id_matches_connector(
        self, connector: PlatformConnector
    ) -> None:
        platform_id = connector.get_definition().platform_id
        for tool in connector.get_available_tools():
            assert tool.platform_id == platform_id

    def test_supported_tools_listed_in_definition(
        self, connector: PlatformConnector
    ) -> None:
        defn = connector.get_definition()
        tool_names = {t.name for t in connector.get_available_tools()}
        for name in defn.supported_tools:
            assert name in tool_names, (
                f"Tool '{name}' listed in supported_tools but not returned by get_available_tools()"
            )


# ---------------------------------------------------------------------------
# Signal contract
# ---------------------------------------------------------------------------


class TestSignals:
    def test_get_signals_returns_list(self, connector: PlatformConnector) -> None:
        defn = connector.get_definition()
        signals = connector.get_signals(defn.supported_signal_types, {})
        assert isinstance(signals, list)

    def test_every_signal_has_source_metadata(
        self, connector: PlatformConnector
    ) -> None:
        defn = connector.get_definition()
        signals = connector.get_signals(defn.supported_signal_types, {})
        for sig in signals:
            assert "source_metadata" in sig, (
                f"Signal missing 'source_metadata' key in {defn.platform_id}"
            )

    def test_source_metadata_has_required_fields(
        self, connector: PlatformConnector
    ) -> None:
        defn = connector.get_definition()
        signals = connector.get_signals(defn.supported_signal_types, {})
        required = {"source_mode", "connector_id", "platform_id", "retrieved_at", "confidence"}
        for sig in signals:
            missing = required - sig["source_metadata"].keys()
            assert not missing, (
                f"source_metadata missing fields {missing} in {defn.platform_id}"
            )

    def test_empty_requirements_returns_no_signals(
        self, connector: PlatformConnector
    ) -> None:
        signals = connector.get_signals([], {})
        assert signals == []


# ---------------------------------------------------------------------------
# Config validation contract
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_mock_config_has_no_errors(self, connector: PlatformConnector) -> None:
        defn = connector.get_definition()
        config = ConnectorConfig(
            connector_id=defn.id,
            platform_id=defn.platform_id,
            mode=ConnectorMode.MOCK,
        )
        errors = connector.validate_config(config)
        assert errors == [], f"Mock config should be valid, got: {errors}"


# ---------------------------------------------------------------------------
# Tool execution contract
# ---------------------------------------------------------------------------


class TestExecuteTool:
    def test_unknown_tool_returns_error_dict(
        self, connector: PlatformConnector
    ) -> None:
        result = connector.execute_tool("__nonexistent_tool__", {})
        assert "error" in result

    def test_known_tools_execute_without_exception(
        self, connector: PlatformConnector
    ) -> None:
        for tool in connector.get_available_tools():
            result = connector.execute_tool(tool.name, {})
            assert isinstance(result, dict), (
                f"execute_tool({tool.name}) did not return a dict"
            )
            assert "error" not in result, (
                f"execute_tool({tool.name}) returned error: {result.get('error')}"
            )


# ---------------------------------------------------------------------------
# ToolRegistry contract
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_all_connectors_registered(self, registry: ToolRegistry) -> None:
        assert len(registry.list_connectors()) == len(ALL_CONNECTORS)

    def test_list_tools_non_empty(self, registry: ToolRegistry) -> None:
        assert len(registry.list_tools()) > 0

    def test_tool_ids_globally_unique(self, registry: ToolRegistry) -> None:
        tool_ids = [t.id for t in registry.list_tools()]
        assert len(tool_ids) == len(set(tool_ids)), "Duplicate tool IDs across connectors."

    def test_capability_summary_has_expected_keys(self, registry: ToolRegistry) -> None:
        summary = registry.capability_summary()
        assert "total_connectors" in summary
        assert "total_tools" in summary
        assert "connectors" in summary

    def test_tools_for_signal_type_filters_correctly(
        self, registry: ToolRegistry
    ) -> None:
        tools = registry.tools_for_signal_types(["security_events"])
        assert len(tools) > 0
        for t in tools:
            assert "security_events" in t.signal_types_returned

    def test_gather_signals_returns_signals_with_metadata(
        self, registry: ToolRegistry
    ) -> None:
        signals = registry.gather_signals(["security_events", "cost_data"])
        assert len(signals) > 0
        for sig in signals:
            assert "source_metadata" in sig

    def test_execute_unknown_tool_returns_error(self, registry: ToolRegistry) -> None:
        result = registry.execute_tool("nonexistent.tool", {})
        assert "error" in result


# ---------------------------------------------------------------------------
# KPI Agent contract
# ---------------------------------------------------------------------------


class TestKPIAgent:
    def test_run_returns_digest_for_known_persona(
        self, registry: ToolRegistry
    ) -> None:
        agent = KPIAgent(registry)
        result = agent.run(persona_id="compliance_officer")
        assert "weekly_digest" in result
        assert "evidence_events" in result
        assert "source_mode_summary" in result

    def test_run_returns_error_for_unknown_persona(
        self, registry: ToolRegistry
    ) -> None:
        agent = KPIAgent(registry)
        result = agent.run(persona_id="__unknown__")
        assert "error" in result

    def test_evidence_events_has_kpi_interpreted_event(
        self, registry: ToolRegistry
    ) -> None:
        agent = KPIAgent(registry)
        result = agent.run(persona_id="compliance_officer")
        event_types = [e["event_type"] for e in result.get("evidence_events", [])]
        assert "kpi_interpreted" in event_types

    def test_digest_has_required_sections(self, registry: ToolRegistry) -> None:
        agent = KPIAgent(registry)
        result = agent.run(persona_id="cfo")
        digest = result["weekly_digest"]
        for key in (
            "top_risks",
            "recommended_actions",
            "evidence_gaps",
            "confidence_level",
            "executive_summary",
        ):
            assert key in digest, f"Digest missing key: {key}"

    @pytest.mark.parametrize("persona_id", list(PERSONA_CATALOGUE.keys()))
    def test_all_personas_produce_valid_digest(
        self, registry: ToolRegistry, persona_id: str
    ) -> None:
        agent = KPIAgent(registry)
        result = agent.run(persona_id=persona_id)
        assert "error" not in result, f"Persona '{persona_id}' returned error: {result}"
        assert "weekly_digest" in result
