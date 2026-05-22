"""
On-demand governance report for ITHelpDeskAgent.

Prints a structured weekly report to the console covering:
  • Agent governance: Owner and Sponsor from Graph agentRegistrations
  • Usage metrics  : requests, successes, errors, error rate, tokens (last 7 days)
  • Cost estimate  : USD total for the AI Services resource (last 7 days)
  • Risk indicators: rule-based assessment against configurable thresholds
  • Azure Advisor  : recommendations scoped to the resource group

Usage:
    python report/report.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from azure.identity import DefaultAzureCredential
from azure.monitor.query import MetricsQueryClient, MetricAggregationType
from azure.mgmt.costmanagement import CostManagementClient
from azure.mgmt.costmanagement.models import (
    QueryDefinition,
    QueryTimePeriod,
    QueryDataset,
    QueryAggregation,
    QueryGrouping,
    TimeframeType,
)
from azure.mgmt.advisor import AdvisorManagementClient
from dotenv import load_dotenv

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(dotenv_path=_ENV)

# ── Required env vars ──────────────────────────────────────────────────────────
AGENT_GUID            = os.getenv("AGENT_GUID", "")
AZURE_SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
AZURE_RESOURCE_GROUP  = os.environ["AZURE_RESOURCE_GROUP_NAME"]
AI_SERVICES_NAME      = os.environ["AI_SERVICES_NAME"]

# ── Risk thresholds (configurable) ────────────────────────────────────────────
RISK_MAX_ERROR_RATE      = float(os.getenv("RISK_MAX_ERROR_RATE", "0.05"))
RISK_COST_THRESHOLD_USD  = float(os.getenv("RISK_COST_THRESHOLD_USD", "10.0"))
RISK_IDLE_DAYS           = int(os.getenv("RISK_IDLE_DAYS", "3"))

_REPORT_WIDTH = 66
_SEP = "━" * _REPORT_WIDTH


def _h(text: str) -> None:
    print(f"\n  {text}")


def _row(label: str, value: str) -> None:
    print(f"  {label:<30}{value}")


# ── Governance ────────────────────────────────────────────────────────────────

def fetch_governance(agent_guid: str, credential: DefaultAzureCredential) -> dict:
    """Read Owner and Sponsor from Graph agentRegistrations."""
    if not agent_guid:
        return {"owner": "—  (AGENT_GUID not set)", "sponsor": "—  (AGENT_GUID not set)"}

    token = credential.get_token("https://graph.microsoft.com/.default")
    headers = {"Authorization": f"Bearer {token.token}"}
    url = f"https://graph.microsoft.com/beta/copilot/agentRegistrations/{agent_guid}"
    try:
        resp = httpx.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "owner":   data.get("ownerDisplayName") or data.get("ownerUserId") or "—",
                "sponsor": data.get("sponsorDisplayName") or data.get("sponsorUserId") or "—",
            }
        if resp.status_code == 403:
            return {"owner": "403 — run governance/set_ownership.py for setup instructions",
                    "sponsor": "403"}
    except Exception as exc:  # noqa: BLE001
        return {"owner": f"Error: {exc}", "sponsor": "—"}
    return {"owner": "—", "sponsor": "—"}


# ── Usage metrics ─────────────────────────────────────────────────────────────

def fetch_usage(credential: DefaultAzureCredential) -> dict:
    """Query Azure Monitor metrics for the AI Services resource."""
    resource_id = (
        f"/subscriptions/{AZURE_SUBSCRIPTION_ID}/resourceGroups/{AZURE_RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{AI_SERVICES_NAME}"
    )
    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=7)

    metrics_client = MetricsQueryClient(credential)
    try:
        result = metrics_client.query_resource(
            resource_uri=resource_id,
            metric_names=["TotalCalls", "SuccessfulCalls", "TotalErrors", "TokenTransaction"],
            timespan=(start, end),
            aggregations=[MetricAggregationType.TOTAL],
            granularity=timedelta(days=7),
        )
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    def _sum(name: str) -> float:
        for m in result.metrics:
            if m.name == name:
                for ts in m.timeseries:
                    for dp in ts.data:
                        if dp.total is not None:
                            return float(dp.total)
        return 0.0

    total    = _sum("TotalCalls")
    success  = _sum("SuccessfulCalls")
    errors   = _sum("TotalErrors")
    tokens   = _sum("TokenTransaction")
    err_rate = (errors / total) if total > 0 else 0.0

    return {
        "total": int(total),
        "success": int(success),
        "errors": int(errors),
        "error_rate": err_rate,
        "tokens": int(tokens),
    }


# ── Cost ──────────────────────────────────────────────────────────────────────

def fetch_cost(credential: DefaultAzureCredential) -> dict:
    """Query Cost Management for last-7-days spend in the resource group."""
    scope = (
        f"/subscriptions/{AZURE_SUBSCRIPTION_ID}/resourceGroups/{AZURE_RESOURCE_GROUP}"
    )
    end   = datetime.now(tz=timezone.utc).date()
    start = end - timedelta(days=7)

    client = CostManagementClient(credential, subscription_id=AZURE_SUBSCRIPTION_ID)
    try:
        result = client.query.usage(
            scope=scope,
            parameters=QueryDefinition(
                type="Usage",
                timeframe=TimeframeType.CUSTOM,
                time_period=QueryTimePeriod(
                    from_property=datetime(start.year, start.month, start.day, tzinfo=timezone.utc),
                    to=datetime(end.year, end.month, end.day, tzinfo=timezone.utc),
                ),
                dataset=QueryDataset(
                    granularity="None",
                    aggregation={"TotalCost": QueryAggregation(name="Cost", function="Sum")},
                    grouping=[QueryGrouping(type="Dimension", name="Currency")],
                ),
            ),
        )
        rows = result.rows or []
        if rows:
            amount   = rows[0][0]
            currency = rows[0][1] if len(rows[0]) > 1 else "USD"
            return {"amount": float(amount), "currency": currency}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    return {"amount": 0.0, "currency": "USD"}


# ── Advisor ───────────────────────────────────────────────────────────────────

def fetch_advisor(credential: DefaultAzureCredential) -> list[str]:
    """List Azure Advisor recommendations for the resource group."""
    client = AdvisorManagementClient(credential, subscription_id=AZURE_SUBSCRIPTION_ID)
    recs: list[str] = []
    try:
        for rec in client.recommendations.list(
            filter=f"resourceGroup eq '{AZURE_RESOURCE_GROUP}'"
        ):
            short = getattr(rec, "short_description", None)
            if short:
                problem = getattr(short, "problem", str(short))
                recs.append(problem)
    except Exception as exc:  # noqa: BLE001
        recs.append(f"Error fetching Advisor data: {exc}")
    return recs


# ── Risk assessment ───────────────────────────────────────────────────────────

def evaluate_risks(usage: dict, cost: dict) -> list[str]:
    """Return a list of human-readable risk strings, empty if none."""
    if "error" in usage or "error" in cost:
        return []
    risks: list[str] = []

    err_rate = usage.get("error_rate", 0.0)
    if err_rate > RISK_MAX_ERROR_RATE:
        risks.append(
            f"High error rate: {err_rate:.1%} exceeds threshold {RISK_MAX_ERROR_RATE:.1%}"
        )

    amount = cost.get("amount", 0.0)
    if amount > RISK_COST_THRESHOLD_USD:
        currency = cost.get("currency", "USD")
        risks.append(
            f"Cost alert: {amount:.2f} {currency} exceeds threshold "
            f"{RISK_COST_THRESHOLD_USD:.2f} USD"
        )

    total = usage.get("total", 0)
    if total == 0:
        risks.append(f"Idle agent: no requests in the last 7 days (threshold: {RISK_IDLE_DAYS}d)")

    return risks


# ── Print ─────────────────────────────────────────────────────────────────────

def print_report(
    agent_name: str,
    period_start: str,
    period_end: str,
    governance: dict,
    usage: dict,
    cost: dict,
    risks: list[str],
    advisor: list[str],
) -> None:
    print()
    print(_SEP)
    print(f"  Weekly Agent Governance Report — {agent_name}")
    print(f"  Period : {period_start}  →  {period_end}")
    print(_SEP)

    _h("Governance")
    _row("Owner",   governance.get("owner", "—"))
    _row("Sponsor", governance.get("sponsor", "—"))

    _h("Usage  (last 7 days)")
    if "error" in usage:
        _row("Error", usage["error"])
    else:
        _row("Total requests",  str(usage.get("total", 0)))
        _row("Successful",      str(usage.get("success", 0)))
        _row("Errors",          str(usage.get("errors", 0)))
        _row("Error rate",      f"{usage.get('error_rate', 0):.1%}")
        _row("Tokens consumed", f"{usage.get('tokens', 0):,}")

    _h("Cost  (last 7 days)")
    if "error" in cost:
        _row("Error", cost["error"])
    else:
        _row(
            "Estimated spend",
            f"{cost.get('amount', 0):.4f} {cost.get('currency', 'USD')}",
        )

    _h("Risks")
    if risks:
        for r in risks:
            print(f"  ⚠  {r}")
    else:
        print("  ✅  None")

    _h("Azure Advisor  (resource group)")
    if advisor:
        for a in advisor:
            print(f"  •  {a}")
    else:
        print("  ✅  None")

    print()
    print(_SEP)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Gathering governance data…")

    now   = datetime.now(tz=timezone.utc).date()
    start = now - timedelta(days=7)

    credential = DefaultAzureCredential()

    governance = fetch_governance(AGENT_GUID, credential)
    usage      = fetch_usage(credential)
    cost       = fetch_cost(credential)
    risks      = evaluate_risks(usage, cost)
    advisor    = fetch_advisor(credential)

    print_report(
        agent_name   = "ITHelpDeskAgent",
        period_start = str(start),
        period_end   = str(now),
        governance   = governance,
        usage        = usage,
        cost         = cost,
        risks        = risks,
        advisor      = advisor,
    )


if __name__ == "__main__":
    main()
