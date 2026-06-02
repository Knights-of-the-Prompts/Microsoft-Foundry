"""Live Microsoft Agent 365 connector — real Graph API calls.

Uses azure-identity DefaultAzureCredential (same credential chain as the
Azure live connector) to acquire a Graph token, then calls the Microsoft
Graph API endpoints for Copilot agent registration and usage.

Required Graph permissions (application):
  AgentRegistration.Read.All   — list registered Copilot agents
  Reports.Read.All             — usage / activity reports

Required environment variable to activate live mode:
  CONTROL_PLANE_AGENT365_LIVE=true

Optional (override the identity used):
  AGENT365_TENANT_ID     — AAD tenant (defaults to DefaultAzureCredential tenant)
  AGENT365_CLIENT_ID     — service principal client ID
  AGENT365_CLIENT_SECRET — service principal secret (use Key Vault in production)

Design:
  - Never raises: errors are captured in SignalExecution and returned as
    source_mode="error" so the UI shows them in the provenance drawer.
  - Falls back to the mock connector when live mode is not enabled.
  - Raw preview is a safe, trimmed subset of the API response (no PII).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from control_plane.connectors.base import (
    AuthType,
    ConnectorConfig,
    ConnectorDefinition,
    ConnectorMode,
    ConnectorStatus,
    ControlPlaneTool,
    PlatformConnector,
)
from control_plane.connectors.agent365 import Agent365MockConnector
from control_plane.models.provenance import SignalExecution

_PLATFORM_ID = "agent365"
_CONNECTOR_ID = "agent365"
_GRAPH_BASE = "https://graph.microsoft.com"


# ---------------------------------------------------------------------------
# Live tools
# ---------------------------------------------------------------------------

_LIVE_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.list_copilot_agents",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="list_copilot_agents",
        description=(
            "List Copilot agents registered in this tenant via Microsoft Graph. "
            "Returns agent display name, status, owner, and creation date."
        ),
        input_schema={},
        output_schema={"agents": "array", "total": "integer"},
        required_permissions=["AgentRegistration.Read.All"],
        signal_types_returned=["agent_registrations"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Global Reader"],
        sensitive_data_level="low",
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_copilot_usage_summary",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_copilot_usage_summary",
        description=(
            "Retrieve aggregate M365 Copilot usage metrics — active users, "
            "interaction counts, and enabled workloads — via Microsoft Graph reports."
        ),
        input_schema={"period": {"type": "string", "default": "D7"}},
        output_schema={"active_users": "integer", "total_interactions": "integer"},
        required_permissions=["Reports.Read.All"],
        signal_types_returned=["agent_activity", "user_activity"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Reports Reader", "Global Reader"],
        sensitive_data_level="low",
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_agent_ownership_gaps",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_agent_ownership_gaps",
        description=(
            "Identify registered Copilot agents that have no assigned owner or "
            "published contact in the tenant directory."
        ),
        input_schema={},
        output_schema={"unowned_agents": "array", "coverage_pct": "number"},
        required_permissions=["AgentRegistration.Read.All"],
        signal_types_returned=["ownership_data", "agent_registrations"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Global Reader"],
        sensitive_data_level="low",
    ),
]


# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------

def _live_enabled() -> bool:
    return os.environ.get("CONTROL_PLANE_AGENT365_LIVE", "").lower() in ("true", "1", "yes")


def _tenant_id() -> Optional[str]:
    return os.environ.get("AGENT365_TENANT_ID") or os.environ.get("AZURE_TENANT_ID") or None


def _client_id() -> Optional[str]:
    return os.environ.get("AGENT365_CLIENT_ID") or None


def _client_secret() -> Optional[str]:
    return os.environ.get("AGENT365_CLIENT_SECRET") or None


# ---------------------------------------------------------------------------
# Graph HTTP helper
# ---------------------------------------------------------------------------

def _graph_get(path: str, token: str) -> Dict[str, Any]:
    """Make a GET request to Microsoft Graph. Returns parsed JSON dict."""
    import urllib.request
    import json as _json

    url = f"{_GRAPH_BASE}{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # nosec — HTTPS only
        return _json.loads(resp.read().decode())


def _acquire_graph_token() -> tuple[str, str]:
    """Acquire a Microsoft Graph token via azure-identity.

    Returns (token_string, identity_summary).
    Raises on failure — callers must catch.
    """
    from azure.identity import DefaultAzureCredential, ClientSecretCredential

    secret = _client_secret()
    tid = _tenant_id()
    cid = _client_id()

    if secret and tid and cid:
        cred = ClientSecretCredential(
            tenant_id=tid,
            client_id=cid,
            client_secret=secret,
        )
        identity = f"ClientSecretCredential (tenant {tid[:8]}…)"
    else:
        cred = DefaultAzureCredential()
        identity = "DefaultAzureCredential"

    token_obj = cred.get_token("https://graph.microsoft.com/.default")
    return token_obj.token, identity


# ---------------------------------------------------------------------------
# Live connector
# ---------------------------------------------------------------------------

class Agent365LiveConnector(PlatformConnector):
    """Live Microsoft Agent 365 connector.

    Makes real Microsoft Graph API calls when CONTROL_PLANE_AGENT365_LIVE=true.
    Falls back gracefully to error provenance if auth or API calls fail.
    """

    def get_definition(self) -> ConnectorDefinition:
        status = ConnectorStatus.CONFIGURED if _live_enabled() else ConnectorStatus.NOT_CONFIGURED
        if _live_enabled() and (_tenant_id() or _client_id()):
            status = ConnectorStatus.CONNECTED
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft Agent 365 (Live)",
            description=(
                "Copilot agent registrations, usage, and ownership gaps via "
                "Microsoft Graph API. Uses DefaultAzureCredential or client credentials."
            ),
            mode=ConnectorMode.LIVE,
            status=status,
            auth_type=AuthType.AZURE_DEFAULT_CREDENTIAL,
            base_url=_GRAPH_BASE,
            required_scopes=["https://graph.microsoft.com/.default"],
            supported_signal_types=["agent_registrations", "agent_activity", "ownership_data", "user_activity"],
            supported_tools=[t.name for t in _LIVE_TOOLS],
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if config.mode == ConnectorMode.LIVE:
            if not _tenant_id():
                errors.append("AGENT365_TENANT_ID (or AZURE_TENANT_ID) required for live mode.")
        return errors

    def get_health(self) -> Dict[str, Any]:
        if not _live_enabled():
            return {"status": "not_configured", "message": "Set CONTROL_PLANE_AGENT365_LIVE=true to enable."}
        try:
            token, identity = _acquire_graph_token()
            # Lightweight check — list organisation details
            _graph_get("/v1.0/organization?$select=id,displayName", token)
            return {
                "status": "healthy",
                "message": f"Graph token acquired. Identity: {identity}",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": str(exc),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }

    def get_available_tools(self) -> List[ControlPlaneTool]:
        return _LIVE_TOOLS

    # ------------------------------------------------------------------
    # get_signals — called by the KPI Agent during control package build
    # ------------------------------------------------------------------

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not _live_enabled():
            # Delegate to mock for non-live environments
            return Agent365MockConnector().get_signals(signal_requirements, context)

        signals: List[Dict[str, Any]] = []

        try:
            token, identity = _acquire_graph_token()
        except Exception as exc:
            # Auth failure — return error signals for all requested types
            err_meta = self._source_metadata(
                source_mode=ConnectorMode.LIVE,
                connector_id=_CONNECTOR_ID,
                platform_id=_PLATFORM_ID,
                confidence=0.0,
            )
            err_meta["error"] = f"Graph token acquisition failed: {exc}"
            err_meta["source_mode"] = "error"
            for stype in signal_requirements:
                signals.append({
                    "signal_type": stype,
                    "platform_id": _PLATFORM_ID,
                    "title": f"Agent 365 auth failed — {stype} unavailable",
                    "value": {"severity": "error"},
                    "source_metadata": err_meta,
                })
            return signals

        if "agent_registrations" in signal_requirements or "ownership_data" in signal_requirements:
            sig = self._fetch_agent_registrations(token, identity, signal_requirements)
            signals.extend(sig)

        if "agent_activity" in signal_requirements or "user_activity" in signal_requirements:
            sig = self._fetch_usage_summary(token, identity)
            signals.extend(sig)

        return signals

    # ------------------------------------------------------------------
    # Tool execution — called from the registry directly
    # ------------------------------------------------------------------

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not _live_enabled():
            return Agent365MockConnector().execute_tool(tool_name, payload)

        try:
            token, identity = _acquire_graph_token()
        except Exception as exc:
            return {"error": f"Graph auth failed: {exc}", "source_mode": "error"}

        if tool_name == "list_copilot_agents":
            return self._tool_list_agents(token)
        if tool_name == "get_copilot_usage_summary":
            period = payload.get("period", "D7")
            return self._tool_usage_summary(token, period)
        if tool_name == "get_agent_ownership_gaps":
            return self._tool_ownership_gaps(token)

        return {"error": f"Unknown tool '{tool_name}'", "source_mode": "error"}

    # ------------------------------------------------------------------
    # Private: individual API call implementations
    # ------------------------------------------------------------------

    def _fetch_agent_registrations(
        self, token: str, identity: str, signal_requirements: List[str]
    ) -> List[Dict[str, Any]]:
        """Call Graph /beta/copilot/agents and return registration + ownership signals."""
        signals: List[Dict[str, Any]] = []
        endpoint = f"{_GRAPH_BASE}/beta/copilot/agents?$select=id,displayName,publisherName,createdDateTime&$top=20"
        retrieved_at = datetime.now(timezone.utc).isoformat()

        try:
            data = _graph_get("/beta/copilot/agents?$select=id,displayName,publisherName,createdDateTime&$top=20", token)
            agents = data.get("value", [])
            total = len(agents)
            unowned = [a for a in agents if not a.get("publisherName")]

            safe_preview = [
                {"id": a.get("id", "")[:8] + "…", "displayName": a.get("displayName"), "publisherName": a.get("publisherName")}
                for a in agents[:5]
            ]

            meta = {
                "source_mode": "live",
                "connector_id": _CONNECTOR_ID,
                "platform_id": _PLATFORM_ID,
                "confidence": 0.95,
                "endpoint": endpoint,
                "identity_summary": identity,
                "retrieved_at": retrieved_at,
                "raw_preview": {"sample": safe_preview, "total": total},
            }

            if "agent_registrations" in signal_requirements:
                signals.append({
                    "signal_type": "agent_registrations",
                    "platform_id": _PLATFORM_ID,
                    "title": f"{total} Copilot agent(s) registered in tenant — {len(unowned)} without publisher info",
                    "value": {
                        "severity": "medium" if unowned else "low",
                        "total_agents": total,
                        "agents_without_owner": len(unowned),
                        "agents": safe_preview,
                    },
                    "source_metadata": meta,
                })

            if "ownership_data" in signal_requirements:
                coverage = round((1 - len(unowned) / max(total, 1)) * 100, 1)
                signals.append({
                    "signal_type": "ownership_data",
                    "platform_id": _PLATFORM_ID,
                    "title": f"Ownership coverage: {coverage}% ({total - len(unowned)} of {total} agents have publisher info)",
                    "value": {
                        "severity": "medium" if coverage < 90 else "low",
                        "coverage_pct": coverage,
                        "unowned_count": len(unowned),
                    },
                    "source_metadata": meta,
                })

        except Exception as exc:
            err_meta = {
                "source_mode": "error",
                "connector_id": _CONNECTOR_ID,
                "platform_id": _PLATFORM_ID,
                "confidence": 0.0,
                "endpoint": endpoint,
                "error": str(exc),
                "retrieved_at": retrieved_at,
            }
            for stype in ("agent_registrations", "ownership_data"):
                if stype in signal_requirements:
                    signals.append({
                        "signal_type": stype,
                        "platform_id": _PLATFORM_ID,
                        "title": f"Agent 365 — {stype} unavailable",
                        "value": {"severity": "error"},
                        "source_metadata": err_meta,
                    })

        return signals

    def _fetch_usage_summary(self, token: str, identity: str) -> List[Dict[str, Any]]:
        """Call Graph /v1.0/reports/getMicrosoft365CopilotUsageSummary."""
        endpoint = f"{_GRAPH_BASE}/v1.0/reports/getMicrosoft365CopilotUsageSummary(period='D7')"
        retrieved_at = datetime.now(timezone.utc).isoformat()

        try:
            data = _graph_get(
                "/v1.0/reports/getMicrosoft365CopilotUsageSummary(period='D7')",
                token,
            )

            # The report returns an array of workload summaries
            workloads = data.get("value", [])
            total_active = sum(int(w.get("activeUserCount", 0)) for w in workloads)
            workload_names = [w.get("reportApps", w.get("apps", "")) for w in workloads[:5]]

            meta = {
                "source_mode": "live",
                "connector_id": _CONNECTOR_ID,
                "platform_id": _PLATFORM_ID,
                "confidence": 0.90,
                "endpoint": endpoint,
                "identity_summary": identity,
                "retrieved_at": retrieved_at,
                "raw_preview": {"active_users_7d": total_active, "workloads": workload_names[:5]},
            }

            return [{
                "signal_type": "agent_activity",
                "platform_id": _PLATFORM_ID,
                "title": f"M365 Copilot: {total_active} active user(s) in last 7 days across {len(workloads)} workload(s)",
                "value": {
                    "severity": "low",
                    "active_users_7d": total_active,
                    "workload_count": len(workloads),
                },
                "source_metadata": meta,
            }]

        except Exception as exc:
            return [{
                "signal_type": "agent_activity",
                "platform_id": _PLATFORM_ID,
                "title": "M365 Copilot usage report unavailable",
                "value": {"severity": "error"},
                "source_metadata": {
                    "source_mode": "error",
                    "connector_id": _CONNECTOR_ID,
                    "platform_id": _PLATFORM_ID,
                    "confidence": 0.0,
                    "endpoint": endpoint,
                    "error": str(exc),
                    "retrieved_at": retrieved_at,
                },
            }]

    # Tool execution helpers --------------------------------------------------

    def _tool_list_agents(self, token: str) -> Dict[str, Any]:
        try:
            data = _graph_get("/beta/copilot/agents?$select=id,displayName,publisherName,createdDateTime&$top=50", token)
            agents = data.get("value", [])
            return {
                "agents": [
                    {
                        "id": a.get("id", "")[:8] + "…",
                        "displayName": a.get("displayName"),
                        "publisherName": a.get("publisherName"),
                        "createdDateTime": a.get("createdDateTime"),
                    }
                    for a in agents
                ],
                "total": len(agents),
                "source_mode": "live",
            }
        except Exception as exc:
            return {"error": str(exc), "source_mode": "error"}

    def _tool_usage_summary(self, token: str, period: str) -> Dict[str, Any]:
        try:
            data = _graph_get(
                f"/v1.0/reports/getMicrosoft365CopilotUsageSummary(period='{period}')",
                token,
            )
            workloads = data.get("value", [])
            total_active = sum(int(w.get("activeUserCount", 0)) for w in workloads)
            return {
                "active_users": total_active,
                "period": period,
                "workload_count": len(workloads),
                "source_mode": "live",
            }
        except Exception as exc:
            return {"error": str(exc), "source_mode": "error"}

    def _tool_ownership_gaps(self, token: str) -> Dict[str, Any]:
        try:
            data = _graph_get("/beta/copilot/agents?$select=id,displayName,publisherName&$top=50", token)
            agents = data.get("value", [])
            unowned = [a for a in agents if not a.get("publisherName")]
            coverage = round((1 - len(unowned) / max(len(agents), 1)) * 100, 1)
            return {
                "coverage_pct": coverage,
                "unowned_count": len(unowned),
                "unowned_agents": [
                    {"id": a.get("id", "")[:8] + "…", "displayName": a.get("displayName")}
                    for a in unowned
                ],
                "source_mode": "live",
            }
        except Exception as exc:
            return {"error": str(exc), "source_mode": "error"}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_agent365_connector() -> PlatformConnector:
    """Return a live connector when CONTROL_PLANE_AGENT365_LIVE=true, else mock."""
    if _live_enabled():
        return Agent365LiveConnector()
    return Agent365MockConnector()
