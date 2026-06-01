"""Live Azure connector — real API calls via azure-identity + azure SDK.

Uses DefaultAzureCredential so the connector works with:
  - Azure CLI login (az login)
  - Managed identity in Azure-hosted environments
  - Service principal via AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID
  - GitHub Actions OIDC (workload identity)

Required environment variables (all optional for mock fallback):
  AZURE_TENANT_ID              — AAD tenant
  AZURE_SUBSCRIPTION_ID        — subscription to query
  AZURE_CLIENT_ID              — optional, for service principal auth
  AZURE_CLIENT_SECRET          — optional, for service principal auth (keep in env, not UI)
  AZURE_RESOURCE_GROUP         — optional, filter resources to this RG
  AZURE_RESOURCE_ID            — optional, for metric queries
  CONTROL_PLANE_AZURE_LIVE     — set to "true" to enable live calls

Design rules:
  - Never raises: all errors are caught and returned as error provenance.
  - Each tool returns a SignalExecution record.
  - Mock fallback is returned if CONTROL_PLANE_AZURE_LIVE is not "true".
  - Raw preview is a small, safe subset of the API response (no secrets).
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
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
from control_plane.models.provenance import SignalExecution

_PLATFORM_ID = "azure"
_CONNECTOR_ID = "azure"

# ---------------------------------------------------------------------------
# Live tools exposed by this connector
# ---------------------------------------------------------------------------

_LIVE_TOOLS = [
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_subscription_context",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_subscription_context",
        description=(
            "Prove Azure connectivity: return tenant, subscription name, "
            "and authenticated principal summary."
        ),
        input_schema={},
        output_schema={"subscription_id": "string", "display_name": "string", "status": "string"},
        required_permissions=["Microsoft.Resources/subscriptions/read"],
        signal_types_returned=["resource_health", "compliance_status"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Reader"],
        sensitive_data_level="low",
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_activity_log_summary",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_activity_log_summary",
        description=(
            "Retrieve Azure Activity Log entries for governance/change signals — "
            "failed deployments, auth changes, resource writes/deletes."
        ),
        input_schema={
            "timespan_days": {"type": "integer", "default": 7},
            "resource_group": {"type": "string", "required": False},
            "failed_only": {"type": "boolean", "default": False},
        },
        output_schema={
            "total_events": "integer",
            "failed_events": "integer",
            "warning_events": "integer",
            "latest_events": "array",
        },
        required_permissions=[
            "Microsoft.Insights/eventtypes/values/read",
            "Microsoft.Insights/eventtypes/management/values/read",
        ],
        signal_types_returned=["resource_health", "security_events", "compliance_status"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Monitoring Reader", "Reader"],
        sensitive_data_level="low",
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_cost_summary",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_cost_summary",
        description=(
            "Retrieve real cost signal via Azure Cost Management Query API — "
            "month-to-date totals, grouped by resource group."
        ),
        input_schema={
            "timeframe": {"type": "string", "default": "MonthToDate"},
            "scope": {"type": "string", "required": False},
        },
        output_schema={
            "total_cost": "number",
            "currency": "string",
            "cost_by_resource_group": "object",
        },
        required_permissions=["Microsoft.CostManagement/query/action"],
        signal_types_returned=["cost_data"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Cost Management Reader"],
        sensitive_data_level="medium",
    ),
    ControlPlaneTool(
        id=f"{_PLATFORM_ID}.get_resource_metric_summary",
        connector_id=_CONNECTOR_ID,
        platform_id=_PLATFORM_ID,
        name="get_resource_metric_summary",
        description=(
            "Retrieve Azure Monitor metrics for a configured resource — "
            "CPU, memory, request rate, error rate, latency."
        ),
        input_schema={
            "resource_id": {"type": "string", "required": True},
            "metric_names": {"type": "array", "default": ["Percentage CPU"]},
            "timespan_hours": {"type": "integer", "default": 24},
        },
        output_schema={"metrics": "array"},
        required_permissions=["Microsoft.Insights/metrics/read"],
        signal_types_returned=["resource_health"],
        source_mode=ConnectorMode.LIVE,
        required_roles=["Monitoring Reader"],
        sensitive_data_level="low",
    ),
]


# ---------------------------------------------------------------------------
# Helper: check if live mode is enabled
# ---------------------------------------------------------------------------

def _live_enabled() -> bool:
    return os.environ.get("CONTROL_PLANE_AZURE_LIVE", "").lower() in ("true", "1", "yes")


def _subscription_id() -> Optional[str]:
    return os.environ.get("AZURE_SUBSCRIPTION_ID") or None


def _resource_group() -> Optional[str]:
    return os.environ.get("AZURE_RESOURCE_GROUP") or None


def _resource_id() -> Optional[str]:
    return os.environ.get("AZURE_RESOURCE_ID") or None


# ---------------------------------------------------------------------------
# Simple in-process cache for expensive / rate-limited calls
# ---------------------------------------------------------------------------

_cost_cache: Dict[str, Any] = {}   # key → {"result": SignalExecution, "expires": datetime}
_COST_CACHE_TTL_SECONDS = 300      # 5 minutes — cost data doesn't change per second


def _cost_cache_get(key: str) -> Optional[Any]:
    entry = _cost_cache.get(key)
    if entry and entry["expires"] > datetime.now(timezone.utc):
        return entry["result"]
    return None


def _cost_cache_set(key: str, result: Any) -> None:
    _cost_cache[key] = {
        "result": result,
        "expires": datetime.now(timezone.utc) + timedelta(seconds=_COST_CACHE_TTL_SECONDS),
    }


# ---------------------------------------------------------------------------
# Live connector
# ---------------------------------------------------------------------------

class AzureLiveConnector(PlatformConnector):
    """Live Azure connector — makes real API calls using DefaultAzureCredential.

    Instantiated when CONTROL_PLANE_AZURE_LIVE=true.
    Falls back to error provenance (not crash) if auth fails.
    """

    def get_definition(self) -> ConnectorDefinition:
        status = ConnectorStatus.CONFIGURED
        if _live_enabled() and _subscription_id():
            status = ConnectorStatus.CONNECTED
        return ConnectorDefinition(
            id=_CONNECTOR_ID,
            platform_id=_PLATFORM_ID,
            name="Microsoft Azure (Live)",
            description=(
                "Resource health, Activity Log, Cost Management and Azure Monitor "
                "via real Azure APIs. Uses DefaultAzureCredential."
            ),
            mode=ConnectorMode.LIVE,
            status=status,
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
            supported_tools=[t.name for t in _LIVE_TOOLS],
            health_check_endpoint="/subscriptions",
            last_checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def validate_config(self, config: ConnectorConfig) -> List[str]:
        errors: List[str] = []
        if not config.subscription_id and not _subscription_id():
            errors.append(
                "AZURE_SUBSCRIPTION_ID is required for live mode. "
                "Set it in .env or environment."
            )
        return errors

    def get_health(self) -> Dict[str, Any]:
        """Run a lightweight auth check against Azure Resource Manager."""
        if not _live_enabled():
            return {
                "status": "mock",
                "latency_ms": None,
                "message": "Live mode disabled. Set CONTROL_PLANE_AZURE_LIVE=true to enable.",
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        result = self._tool_get_subscription_context()
        if result.source_mode == "live":
            return {
                "status": "authenticated",
                "latency_ms": None,
                "message": result.query_summary or "Azure connection verified.",
                "identity": result.identity_summary,
                "checked_at": result.retrieved_at,
                "stages": {
                    "configured": True,
                    "authenticated": True,
                    "authorized": True,
                    "live_data_received": True,
                },
            }
        return {
            "status": "error",
            "latency_ms": None,
            "message": result.error or "Azure authentication failed.",
            "checked_at": result.retrieved_at,
            "stages": {
                "configured": True,
                "authenticated": False,
                "authorized": False,
                "live_data_received": False,
            },
        }

    def get_available_tools(self) -> List[ControlPlaneTool]:
        return _LIVE_TOOLS

    def get_signals(
        self, signal_requirements: List[str], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute live tool calls and return signal dicts with provenance.

        All tool calls are included in provenance — even errors — so the UI can
        show what was attempted vs what succeeded.  ``used_in_composition`` is set
        to False for error results so the composition agent knows the value was
        not used in the package.
        """
        signals: List[Dict[str, Any]] = []

        def _append(signal_type: str, exec_result: Any) -> None:
            """Always record the execution in provenance; mark errors as unused."""
            exec_dict = exec_result.to_dict()
            if exec_result.source_mode == "error":
                exec_dict["used_in_composition"] = False
            signals.append({
                "signal_type": signal_type,
                "platform_id": _PLATFORM_ID,
                "title": exec_result.query_summary or f"Azure {signal_type}",
                "value": exec_result.raw_preview or {},
                "source_metadata": self._meta_from_exec(exec_result),
                "signal_execution": exec_dict,
            })

        # Always fetch subscription context — proves live Azure connection for
        # any signal request on this platform.
        sub_result = self._tool_get_subscription_context()
        _append("subscription_context", sub_result)

        # Activity log — for resource health, security, compliance, or generic azure requests
        if any(s in signal_requirements for s in (
            "resource_health", "security_events", "compliance_status",
            "agent_invocations", "model_usage",
        )):
            _append("activity_log", self._tool_get_activity_log_summary())

        # Cost data
        if "cost_data" in signal_requirements:
            _append("cost_data", self._tool_get_cost_summary())

        return signals

    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named tool and return its result with provenance."""
        if tool_name == "get_subscription_context":
            return self._tool_get_subscription_context().to_dict()
        if tool_name == "get_activity_log_summary":
            return self._tool_get_activity_log_summary(
                timespan_days=int(payload.get("timespan_days", 7)),
                resource_group=payload.get("resource_group"),
                failed_only=bool(payload.get("failed_only", False)),
            ).to_dict()
        if tool_name == "get_cost_summary":
            return self._tool_get_cost_summary(
                timeframe=payload.get("timeframe", "MonthToDate"),
                scope=payload.get("scope"),
            ).to_dict()
        if tool_name == "get_resource_metric_summary":
            resource_id = payload.get("resource_id") or _resource_id()
            if not resource_id:
                return SignalExecution(
                    signal_name="resource_metrics",
                    platform_id=_PLATFORM_ID,
                    tool_name=f"{_PLATFORM_ID}.get_resource_metric_summary",
                    source_mode="error",
                    confidence=0.0,
                    error="AZURE_RESOURCE_ID not configured. Set it in .env to enable metric queries.",
                    query_summary="Resource metric query not configured.",
                ).to_dict()
            return self._tool_get_resource_metric_summary(
                resource_id=resource_id,
                metric_names=payload.get("metric_names", ["Percentage CPU"]),
                timespan_hours=int(payload.get("timespan_hours", 24)),
            ).to_dict()
        return {"error": f"Unknown tool '{tool_name}' on {_PLATFORM_ID} connector."}

    # -----------------------------------------------------------------------
    # Private tool implementations
    # -----------------------------------------------------------------------

    def _tool_get_subscription_context(self) -> SignalExecution:
        """Return Azure subscription context and identity summary."""
        if not _live_enabled():
            return SignalExecution(
                signal_name="subscription_context",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_subscription_context",
                source_mode="mock",
                confidence=0.7,
                query_summary="Live mode disabled — returning mock subscription context.",
                raw_preview={
                    "subscription_id": "mock-sub-id",
                    "display_name": "Mock Subscription",
                    "state": "Enabled",
                    "status": "mock",
                },
            )
        sub_id = _subscription_id()
        if not sub_id:
            return SignalExecution(
                signal_name="subscription_context",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_subscription_context",
                source_mode="error",
                confidence=0.0,
                error="AZURE_SUBSCRIPTION_ID not set.",
                query_summary="Subscription ID missing — cannot authenticate.",
            )
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.subscription import SubscriptionClient
            credential = DefaultAzureCredential()
            client = SubscriptionClient(credential)
            sub = client.subscriptions.get(sub_id)
            identity_summary = _get_identity_summary(credential)
            raw_preview = {
                "subscription_id": sub.subscription_id,
                "display_name": sub.display_name,
                "state": str(sub.state),
                "tenant_id": os.environ.get("AZURE_TENANT_ID", ""),
            }
            return SignalExecution(
                signal_name="subscription_context",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_subscription_context",
                source_mode="live",
                confidence=1.0,
                query_summary=f"Authenticated to '{sub.display_name}' ({sub.subscription_id}).",
                endpoint=f"GET https://management.azure.com/subscriptions/{sub_id}?api-version=2022-12-01",
                identity_summary=identity_summary,
                raw_preview=raw_preview,
            )
        except Exception as exc:
            return SignalExecution(
                signal_name="subscription_context",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_subscription_context",
                source_mode="error",
                confidence=0.0,
                error=_safe_error(exc),
                query_summary="Azure authentication failed.",
                endpoint=f"GET https://management.azure.com/subscriptions/{sub_id}",
            )

    def _tool_get_activity_log_summary(
        self,
        timespan_days: int = 7,
        resource_group: Optional[str] = None,
        failed_only: bool = False,
    ) -> SignalExecution:
        """Retrieve and summarise Azure Activity Log entries."""
        if not _live_enabled():
            return SignalExecution(
                signal_name="recent_failed_operations",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_activity_log_summary",
                source_mode="mock",
                confidence=0.65,
                query_summary="Live mode disabled — returning mock activity log summary.",
                raw_preview={
                    "total_events": 42,
                    "failed_events": 3,
                    "warning_events": 7,
                    "recent_change_count": 12,
                    "top_operations": ["Microsoft.Compute/virtualMachines/write"],
                    "latest_events": [],
                },
            )
        sub_id = _subscription_id()
        if not sub_id:
            return SignalExecution(
                signal_name="recent_failed_operations",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_activity_log_summary",
                source_mode="error",
                confidence=0.0,
                error="AZURE_SUBSCRIPTION_ID not set.",
            )
        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.monitor import MonitorManagementClient

            credential = DefaultAzureCredential()
            monitor_client = MonitorManagementClient(credential, sub_id)

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=timespan_days)
            filter_str = (
                f"eventTimestamp ge '{start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}' "
                f"and eventTimestamp le '{end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}'"
            )
            if resource_group:
                filter_str += f" and resourceGroupName eq '{resource_group}'"

            select_fields = (
                "eventTimestamp,operationName,status,resourceGroupName,"
                "resourceId,correlationId,level,caller"
            )

            events_iter = monitor_client.activity_logs.list(
                filter=filter_str,
                select=select_fields,
            )
            events = list(events_iter)

            total = len(events)
            failed = sum(
                1 for e in events
                if e.status and str(e.status.value).lower() == "failed"
            )
            warnings = sum(
                1 for e in events
                if e.level and str(e.level).lower() == "warning"
            )

            # Top operations (by frequency, capped at 5)
            op_counts: Dict[str, int] = {}
            for e in events:
                op = str(e.operation_name.value) if e.operation_name else "unknown"
                op_counts[op] = op_counts.get(op, 0) + 1
            top_ops = sorted(op_counts, key=lambda k: op_counts[k], reverse=True)[:5]

            # Latest 10 events (most recent first)
            sorted_events = sorted(
                events,
                key=lambda e: e.event_timestamp or datetime.min,
                reverse=True,
            )[:10]
            latest = [
                {
                    "timestamp": e.event_timestamp.isoformat() if e.event_timestamp else None,
                    "operation": str(e.operation_name.value) if e.operation_name else None,
                    "status": str(e.status.value) if e.status else None,
                    "resource_group": e.resource_group_name,
                    "level": str(e.level) if e.level else None,
                    "caller": e.caller,
                }
                for e in sorted_events
            ]

            rg_label = f" in '{resource_group}'" if resource_group else ""
            query_summary = (
                f"Activity Log: {total} events in last {timespan_days} days{rg_label}. "
                f"{failed} failed, {warnings} warnings."
            )

            return SignalExecution(
                signal_name="recent_failed_operations",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_activity_log_summary",
                source_mode="live",
                confidence=0.9,
                query_summary=query_summary,
                endpoint=(
                    f"GET https://management.azure.com/subscriptions/{sub_id}/"
                    "providers/microsoft.insights/eventtypes/management/values"
                    f"?api-version=2015-04-01&$filter={filter_str[:80]}..."
                ),
                raw_preview={
                    "total_events": total,
                    "failed_events": failed,
                    "warning_events": warnings,
                    "recent_change_count": total,
                    "top_operations": top_ops,
                    "latest_events": latest,
                },
            )

        except Exception as exc:
            error_msg = _safe_error(exc)
            # Check if it's a permissions error
            source = "error"
            if "AuthorizationFailed" in error_msg or "Forbidden" in error_msg:
                source = "error"
            return SignalExecution(
                signal_name="recent_failed_operations",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_activity_log_summary",
                source_mode=source,
                confidence=0.0,
                error=error_msg,
                query_summary="Activity log query failed.",
                endpoint=(
                    f"GET https://management.azure.com/subscriptions/{sub_id}/"
                    "providers/microsoft.insights/eventtypes/management/values"
                ),
            )

    def _tool_get_cost_summary(
        self,
        timeframe: str = "MonthToDate",
        scope: Optional[str] = None,
    ) -> SignalExecution:
        """Retrieve cost data via Azure Cost Management Query API."""
        if not _live_enabled():
            return SignalExecution(
                signal_name="month_to_date_cost",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_cost_summary",
                source_mode="mock",
                confidence=0.65,
                query_summary="Live mode disabled — returning mock cost summary.",
                raw_preview={
                    "total_cost": 1240.0,
                    "currency": "USD",
                    "timeframe": timeframe,
                    "cost_by_resource_group": {
                        "rg-agents": 820.0,
                        "rg-foundry": 310.0,
                        "rg-shared": 110.0,
                    },
                },
            )
        sub_id = _subscription_id()
        if not sub_id:
            return SignalExecution(
                signal_name="month_to_date_cost",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_cost_summary",
                source_mode="error",
                confidence=0.0,
                error="AZURE_SUBSCRIPTION_ID not set.",
            )

        scope = scope or f"/subscriptions/{sub_id}"
        cache_key = f"cost:{scope}:{timeframe}"

        # Return cached result if still fresh (avoids Cost Management rate limits)
        cached = _cost_cache_get(cache_key)
        if cached is not None:
            return cached

        try:
            from azure.identity import DefaultAzureCredential
            from azure.mgmt.costmanagement import CostManagementClient
            from azure.mgmt.costmanagement.models import (
                QueryDefinition,
                QueryTimePeriod,
                TimeframeType,
                ExportType,
                QueryDataset,
                QueryAggregation,
                QueryGrouping,
                QueryColumnType,
            )

            credential = DefaultAzureCredential()
            client = CostManagementClient(credential)

            query = QueryDefinition(
                type=ExportType.ACTUAL_COST,
                timeframe=TimeframeType.MONTH_TO_DATE,
                dataset=QueryDataset(
                    granularity="None",
                    aggregation={
                        "totalCost": QueryAggregation(name="Cost", function="Sum")
                    },
                    grouping=[
                        QueryGrouping(
                            type=QueryColumnType.DIMENSION,
                            name="ResourceGroupName",
                        )
                    ],
                ),
            )
            result = client.query.usage(scope=scope, parameters=query)

            # Parse result rows
            columns = [col.name for col in (result.columns or [])]
            rows = result.rows or []

            total_cost = 0.0
            cost_by_rg: Dict[str, float] = {}
            currency = "USD"

            cost_idx = next((i for i, c in enumerate(columns) if c == "Cost"), None)
            rg_idx = next((i for i, c in enumerate(columns) if c == "ResourceGroupName"), None)
            cur_idx = next((i for i, c in enumerate(columns) if "Currency" in c), None)

            for row in rows:
                cost_val = float(row[cost_idx]) if cost_idx is not None else 0.0
                rg_name = str(row[rg_idx]) if rg_idx is not None else "unknown"
                if cur_idx is not None and currency == "USD":
                    currency = str(row[cur_idx])
                total_cost += cost_val
                cost_by_rg[rg_name] = round(cost_val, 2)

            raw_preview = {
                "total_cost": round(total_cost, 2),
                "currency": currency,
                "timeframe": timeframe,
                "scope": scope,
                "cost_by_resource_group": cost_by_rg,
            }
            exec_result = SignalExecution(
                signal_name="month_to_date_cost",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_cost_summary",
                source_mode="live",
                confidence=0.85,
                query_summary=(
                    f"Cost Management: {currency} {total_cost:,.2f} MTD "
                    f"across {len(cost_by_rg)} resource group(s)."
                ),
                endpoint=f"POST https://management.azure.com{scope}/providers/Microsoft.CostManagement/query",
                raw_preview=raw_preview,
            )
            _cost_cache_set(cache_key, exec_result)
            return exec_result

        except Exception as exc:
            # Extract Retry-After from response headers when available (429 rate-limit)
            retry_after: Optional[int] = None
            resp = getattr(exc, "response", None)
            if resp is not None:
                headers = getattr(resp, "headers", {}) or {}
                ra = (
                    headers.get("x-ms-ratelimit-microsoft.costmanagement-clienttype-retry-after")
                    or headers.get("Retry-After")
                )
                if ra:
                    try:
                        retry_after = int(ra)
                    except (ValueError, TypeError):
                        pass

            error_msg = _safe_error(exc)
            if retry_after is not None:
                error_msg = f"{error_msg} Retry after {retry_after}s."

            return SignalExecution(
                signal_name="month_to_date_cost",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_cost_summary",
                source_mode="error",
                confidence=0.0,
                error=error_msg,
                query_summary=(
                    f"Cost Management rate-limited — retry in {retry_after}s."
                    if retry_after is not None
                    else "Cost Management query failed."
                ),
                endpoint=f"POST https://management.azure.com{scope}/providers/Microsoft.CostManagement/query",
            )

    def _tool_get_resource_metric_summary(
        self,
        resource_id: str,
        metric_names: Optional[List[str]] = None,
        timespan_hours: int = 24,
    ) -> SignalExecution:
        """Retrieve Azure Monitor metrics for a specific resource."""
        metric_names = metric_names or ["Percentage CPU"]
        if not _live_enabled():
            return SignalExecution(
                signal_name="resource_metrics",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_resource_metric_summary",
                source_mode="mock",
                confidence=0.6,
                query_summary="Live mode disabled — returning mock metrics.",
                raw_preview={
                    "resource_id": resource_id,
                    "metrics": [
                        {"name": "Percentage CPU", "average": 12.4, "unit": "Percent"}
                    ],
                    "timespan_hours": timespan_hours,
                },
            )
        if not resource_id:
            return SignalExecution(
                signal_name="resource_metrics",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_resource_metric_summary",
                source_mode="error",
                confidence=0.0,
                error="resource_id is required. Set AZURE_RESOURCE_ID in .env.",
                query_summary="Metric query not configured — AZURE_RESOURCE_ID missing.",
            )
        try:
            from azure.identity import DefaultAzureCredential
            from azure.monitor.query import MetricsQueryClient, MetricAggregationType
            import datetime as dt

            credential = DefaultAzureCredential()
            client = MetricsQueryClient(credential)

            end_dt = dt.datetime.now(dt.timezone.utc)
            start_dt = end_dt - dt.timedelta(hours=timespan_hours)

            response = client.query_resource(
                resource_uri=resource_id,
                metric_names=metric_names,
                timespan=(start_dt, end_dt),
                granularity=dt.timedelta(hours=1),
                aggregations=[
                    MetricAggregationType.AVERAGE,
                    MetricAggregationType.MAXIMUM,
                    MetricAggregationType.MINIMUM,
                ],
            )

            metrics_out = []
            for metric in response.metrics:
                for ts in metric.timeseries:
                    for dp in ts.data:
                        metrics_out.append({
                            "name": metric.name,
                            "average": dp.average,
                            "maximum": dp.maximum,
                            "minimum": dp.minimum,
                            "unit": str(metric.unit),
                            "timestamp": dp.timestamp.isoformat() if dp.timestamp else None,
                        })
                        break  # first data point as preview

            return SignalExecution(
                signal_name="resource_metrics",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_resource_metric_summary",
                source_mode="live",
                confidence=0.9,
                query_summary=f"Metrics: {', '.join(metric_names)} for last {timespan_hours}h.",
                endpoint=(
                    f"GET https://management.azure.com{resource_id}/providers/"
                    "microsoft.insights/metrics?api-version=2023-10-01"
                ),
                raw_preview={
                    "resource_id": resource_id,
                    "metrics": metrics_out[:5],
                    "timespan_hours": timespan_hours,
                },
            )

        except Exception as exc:
            return SignalExecution(
                signal_name="resource_metrics",
                platform_id=_PLATFORM_ID,
                tool_name=f"{_PLATFORM_ID}.get_resource_metric_summary",
                source_mode="error",
                confidence=0.0,
                error=_safe_error(exc),
                query_summary="Metric query failed.",
            )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _meta_from_exec(self, exec_result: SignalExecution) -> Dict[str, Any]:
        """Convert a SignalExecution to a source_metadata dict."""
        return {
            "source_mode": exec_result.source_mode,
            "connector_id": _CONNECTOR_ID,
            "platform_id": _PLATFORM_ID,
            "retrieved_at": exec_result.retrieved_at,
            "confidence": exec_result.confidence,
            "raw_reference": exec_result.endpoint,
            "data_quality_notes": exec_result.query_summary,
        }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _get_identity_summary(credential: Any) -> str:
    """Return a safe, non-secret description of the active Azure identity."""
    try:
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        if client_id:
            return f"Service principal {client_id[:8]}... in tenant {tenant_id[:8]}..."
        # Try to discover from token
        token = credential.get_token("https://management.azure.com/.default")
        if token:
            return f"DefaultAzureCredential — token acquired (tenant {tenant_id[:8]}...)"
        return "DefaultAzureCredential (identity details unavailable)"
    except Exception:
        return "DefaultAzureCredential (identity details unavailable)"


def _safe_error(exc: Exception) -> str:
    """Return a safe error string that does not leak secrets."""
    msg = str(exc)
    # Strip any token or secret material that might appear in error messages
    for env_var in ("AZURE_CLIENT_SECRET", "AZURE_CLIENT_ID", "AZURE_TENANT_ID"):
        val = os.environ.get(env_var, "")
        if val and val in msg:
            msg = msg.replace(val, f"[{env_var}]")
    # Truncate to avoid huge stack traces in API responses
    return msg[:500]


# ---------------------------------------------------------------------------
# Factory: return the right connector based on environment
# ---------------------------------------------------------------------------

def get_azure_connector() -> PlatformConnector:
    """Return a live or mock connector based on CONTROL_PLANE_AZURE_LIVE."""
    from control_plane.connectors.azure import AzureMockConnector  # avoid circular import
    if _live_enabled():
        return AzureLiveConnector()
    return AzureMockConnector()
