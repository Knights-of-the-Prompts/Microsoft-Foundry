"""
On-demand governance report for ITHelpDeskAgent.

Prints a structured weekly report to the console covering:
  • Agent identity  : name, ID, environment, registration source, deployment context
  • Governance      : Owner (email), Sponsor (email), Business stream
  • Usage metrics   : requests, successes, errors, error rate, tokens (last 7 days)
  • Cost estimate   : USD total for the AI Services resource (last 7 days)
  • Value           : efficiency value and outcome value (from governance profile)
  • Outcome contrib : business outcome description (from governance profile)
  • Risk indicators : rule-based assessment against configurable thresholds
  • Azure Advisor   : recommendations scoped to the resource group
  • Recommended     : actions for owner, sponsor, or control function

Usage:
    python report/report.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
import yaml
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

_SAMPLE_ROOT = Path(__file__).resolve().parent.parent
_ENV = _SAMPLE_ROOT / ".env"
load_dotenv(dotenv_path=_ENV)

# ── Required env vars ─────────────────────────────────────────────────────────────────
AGENT_GUID            = os.getenv("AGENT_GUID", "")
AZURE_SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
AZURE_RESOURCE_GROUP  = os.environ["AZURE_RESOURCE_GROUP_NAME"]
AI_SERVICES_NAME      = os.environ["AI_SERVICES_NAME"]
AGENT_ENVIRONMENT     = os.getenv("AGENT_ENVIRONMENT", "")

# ── Risk thresholds (configurable) ────────────────────────────────────────────
RISK_MAX_ERROR_RATE      = float(os.getenv("RISK_MAX_ERROR_RATE", "0.05"))
RISK_COST_THRESHOLD_USD  = float(os.getenv("RISK_COST_THRESHOLD_USD", "10.0"))
RISK_IDLE_DAYS           = int(os.getenv("RISK_IDLE_DAYS", "3"))

_REPORT_WIDTH = 66
_SEP = "━" * _REPORT_WIDTH
_PROFILE_PATH = _SAMPLE_ROOT / "governance" / "agent_profile.yaml"


def _h(text: str) -> None:
    print(f"\n  {text}")


def _row(label: str, value: str) -> None:
    print(f"  {label:<30}{value}")


# ── Agent Profile ─────────────────────────────────────────────────────

def load_agent_profile(path: "Optional[Path]" = None) -> dict:
    """Load governance profile YAML if present; return empty dict if absent."""
    target = path or _PROFILE_PATH
    try:
        with open(target, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as exc:  # noqa: BLE001
        print(f"  Warning: could not load agent profile: {exc}")
        return {}


# ── Governance ────────────────────────────────────────────────────────────────

def fetch_governance(agent_guid: str, credential: DefaultAzureCredential,
                     profile: "Optional[dict]" = None) -> dict:
    """
    Read Owner and Sponsor from Graph agentRegistrations.
    Falls back to governance profile values when the Graph path is unavailable.
    """
    _profile = profile or {}
    result = {
        "owner":   _profile.get("owner_email") or "—",
        "sponsor": _profile.get("sponsor_email") or "—",
    }
    if not agent_guid:
        return result

    token = credential.get_token("https://graph.microsoft.com/.default")
    headers = {"Authorization": f"Bearer {token.token}"}
    url = f"https://graph.microsoft.com/beta/copilot/agentRegistrations/{agent_guid}"
    try:
        resp = httpx.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            owner   = data.get("ownerDisplayName") or data.get("ownerUserId")
            sponsor = data.get("sponsorDisplayName") or data.get("sponsorUserId")
            if owner:
                result["owner"] = owner
            if sponsor:
                result["sponsor"] = sponsor
        elif resp.status_code == 403 and not _profile.get("owner_email"):
            result["owner"] = "403 — run governance/set_ownership.py for setup"
    except Exception as exc:  # noqa: BLE001
        if not _profile.get("owner_email"):
            result["owner"] = f"Error: {exc}"
    return result


# ── Usage metrics ─────────────────────────────────────────────────────────────

def fetch_usage(
    credential: DefaultAzureCredential,
    *,
    subscription_id: Optional[str] = None,
    resource_group: Optional[str] = None,
    ai_services_name: Optional[str] = None,
) -> dict:
    """Query Azure Monitor metrics for the AI Services resource."""
    sub = subscription_id or AZURE_SUBSCRIPTION_ID
    rg  = resource_group  or AZURE_RESOURCE_GROUP
    ai  = ai_services_name or AI_SERVICES_NAME
    resource_id = (
        f"/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{ai}"
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

def fetch_cost(
    credential: DefaultAzureCredential,
    *,
    subscription_id: Optional[str] = None,
    resource_group: Optional[str] = None,
) -> dict:
    """Query Cost Management for last-7-days spend in the resource group."""
    sub   = subscription_id or AZURE_SUBSCRIPTION_ID
    rg    = resource_group  or AZURE_RESOURCE_GROUP
    scope = f"/subscriptions/{sub}/resourceGroups/{rg}"
    end   = datetime.now(tz=timezone.utc).date()
    start = end - timedelta(days=7)

    client = CostManagementClient(credential, subscription_id=sub)
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

def fetch_advisor(
    credential: DefaultAzureCredential,
    *,
    subscription_id: Optional[str] = None,
    resource_group: Optional[str] = None,
) -> list[str]:
    """List Azure Advisor recommendations for the resource group."""
    sub = subscription_id or AZURE_SUBSCRIPTION_ID
    rg  = resource_group  or AZURE_RESOURCE_GROUP
    client = AdvisorManagementClient(credential, subscription_id=sub)
    recs: list[str] = []
    try:
        for rec in client.recommendations.list(
            filter=f"resourceGroup eq '{rg}'"
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


# ── Recommended actions ──────────────────────────────────────────────────────────

def generate_recommended_actions(
    risks: list[str],
    advisor: list[str],
    profile: dict,
    governance: dict,
) -> list[str]:
    """
    Derive a short list of actions for the owner, sponsor, or control function.
    Combines risk-based actions, Azure Advisor items, and governance profile
    completeness checks.
    """
    actions: list[str] = []
    owner_contact   = governance.get("owner",   "") or profile.get("owner_email",   "owner")
    sponsor_contact = governance.get("sponsor", "") or profile.get("sponsor_email", "sponsor")

    for risk in risks:
        lower = risk.lower()
        if "error rate" in lower:
            actions.append(
                f"Investigate high error rate with owner — contact: {owner_contact}"
            )
        elif "cost alert" in lower:
            actions.append(
                f"Review cost allocation with FinOps — notify sponsor: {sponsor_contact}"
            )
        elif "idle" in lower:
            actions.append(
                f"Verify agent is still needed — confirm with sponsor: {sponsor_contact}"
            )

    for item in advisor:
        if not item.startswith("Error"):
            actions.append(f"Act on Azure Advisor: {item}")

    # Governance completeness checks
    if not profile.get("business_stream"):
        actions.append(
            "Add business_stream to governance/agent_profile.yaml"
        )
    if not profile.get("efficiency_value_description") and \
       not profile.get("outcome_value_description"):
        actions.append(
            "Connect value attribution — populate value fields in governance/agent_profile.yaml"
        )
    if not profile.get("outcome_description"):
        actions.append(
            "Add outcome_description to governance/agent_profile.yaml"
        )

    return actions


# ── Print ─────────────────────────────────────────────────────────────────────

def print_report(
    agent_name: str,
    period_start: str,
    period_end: str,
    profile: dict,
    governance: dict,
    usage: dict,
    cost: dict,
    risks: list[str],
    advisor: list[str],
    actions: list[str],
) -> None:
    print()
    print(_SEP)
    print(f"  Weekly Agent Governance Report — {agent_name}")
    print(f"  Period : {period_start}  →  {period_end}")
    print(_SEP)

    # ── Agent Identity ──────────────────────────────────────────────────────
    _h("Agent Identity")
    _row("Agent name",         profile.get("agent_name", agent_name))
    _row("Agent ID (Entra)",   AGENT_GUID or "—  (AGENT_GUID not set)")
    _row("Environment",        profile.get("environment", AGENT_ENVIRONMENT or "—"))
    _row("Registration",       profile.get("registration_source", "—"))
    _row("Deployment context", profile.get("deployment_context", "—"))
    _row("Business stream",    profile.get("business_stream") or "—  (not configured)")

    # ── Governance ──────────────────────────────────────────────────────
    _h("Governance")
    _row("Owner (email)",   governance.get("owner", "—"))
    _row("Sponsor (email)", governance.get("sponsor", "—"))

    # ── Usage ────────────────────────────────────────────────────────────
    _h("Usage  (last 7 days)")
    if "error" in usage:
        _row("Error", usage["error"])
    else:
        _row("Total requests",  str(usage.get("total", 0)))
        _row("Successful",      str(usage.get("success", 0)))
        _row("Errors",          str(usage.get("errors", 0)))
        _row("Error rate",      f"{usage.get('error_rate', 0):.1%}")
        _row("Tokens consumed", f"{usage.get('tokens', 0):,}")

    # ── Cost ───────────────────────────────────────────────────────────────
    _h("Cost  (last 7 days)")
    if "error" in cost:
        _row("Error", cost["error"])
    else:
        _row(
            "Estimated spend",
            f"{cost.get('amount', 0):.4f} {cost.get('currency', 'USD')}",
        )

    # ── Value ───────────────────────────────────────────────────────────────
    _h("Value")
    _row("Efficiency value",  profile.get("efficiency_value_description")  or "—  (not configured)")
    _row("Outcome value",     profile.get("outcome_value_description")     or "—  (not configured)")
    _row("Outcome contrib.",  profile.get("outcome_description")           or "—  (not configured)")

    # ── Risks ───────────────────────────────────────────────────────────────
    _h("Risks")
    if risks:
        for r in risks:
            print(f"  ⚠  {r}")
    else:
        print("  ✅  None")

    # ── Azure Advisor ────────────────────────────────────────────────────────
    _h("Azure Advisor  (resource group)")
    if advisor:
        for a in advisor:
            print(f"  •  {a}")
    else:
        print("  ✅  None")

    # ── Recommended Actions ────────────────────────────────────────────────
    _h("Recommended Actions")
    if actions:
        for i, a in enumerate(actions, 1):
            print(f"  {i}.  {a}")
    else:
        print("  ✅  None — no actions required this period")

    print()
    print(_SEP)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("Gathering governance data…")

    now   = datetime.now(tz=timezone.utc).date()
    start = now - timedelta(days=7)

    credential = DefaultAzureCredential()

    profile    = load_agent_profile()
    governance = fetch_governance(AGENT_GUID, credential, profile)
    usage      = fetch_usage(credential)
    cost       = fetch_cost(credential)
    risks      = evaluate_risks(usage, cost)
    advisor    = fetch_advisor(credential)
    actions    = generate_recommended_actions(risks, advisor, profile, governance)

    print_report(
        agent_name   = "ITHelpDeskAgent",
        period_start = str(start),
        period_end   = str(now),
        profile      = profile,
        governance   = governance,
        usage        = usage,
        cost         = cost,
        risks        = risks,
        advisor      = advisor,
        actions      = actions,
    )


if __name__ == "__main__":
    main()
