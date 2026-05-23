"""
Portfolio roll-up report for the agent estate.

Reads a YAML file listing multiple agents, queries governance, usage, cost, and
risk data for each, then prints:
  • Per-agent summary table
  • Estate-wide totals and spotlight (agents needing attention)

Usage:
    python report/portfolio.py
    python report/portfolio.py --portfolio governance/portfolio.yaml
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

_SAMPLE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SAMPLE_ROOT / "report"))

# Load .env before importing report so env vars are available at module level
_ENV = _SAMPLE_ROOT / ".env"
load_dotenv(dotenv_path=_ENV)

from report import (  # noqa: E402
    evaluate_risks,
    fetch_advisor,
    fetch_cost,
    fetch_governance,
    fetch_usage,
    generate_recommended_actions,
    load_agent_profile,
)

_REPORT_WIDTH = 90
_SEP  = "━" * _REPORT_WIDTH
_SEP2 = "─" * _REPORT_WIDTH


# ── Portfolio loader ──────────────────────────────────────────────────────────

def _load_portfolio(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("agents", [])


# ── Per-agent query ───────────────────────────────────────────────────────────

def _query_agent(entry: dict, credential: DefaultAzureCredential) -> dict:
    """Fetch all data for one agent entry and return a result dict."""
    sub  = entry.get("subscription_id", "") or os.environ.get("AZURE_SUBSCRIPTION_ID", "")
    rg   = entry.get("resource_group",   "") or os.environ.get("AZURE_RESOURCE_GROUP_NAME", "")
    ai   = entry.get("ai_services_name", "") or os.environ.get("AI_SERVICES_NAME", "")
    guid = entry.get("agent_guid", "")

    profile_ref = entry.get("profile", "")
    profile_path = (_SAMPLE_ROOT / profile_ref) if profile_ref else None
    profile = load_agent_profile(profile_path)

    governance = fetch_governance(guid, credential, profile)
    usage      = fetch_usage(credential, subscription_id=sub, resource_group=rg, ai_services_name=ai)
    cost       = fetch_cost(credential, subscription_id=sub, resource_group=rg)
    advisor    = fetch_advisor(credential, subscription_id=sub, resource_group=rg)
    risks      = evaluate_risks(usage, cost)
    actions    = generate_recommended_actions(risks, advisor, profile, governance)

    return {
        "name":           entry.get("name", "—"),
        "owner":          governance.get("owner", "—"),
        "business_stream": profile.get("business_stream", "—"),
        "requests":       usage.get("total", 0) if "error" not in usage else "err",
        "cost_str":       (f"{cost.get('amount', 0):.4f} {cost.get('currency', 'USD')}"
                           if "error" not in cost else "err"),
        "cost_amount":    cost.get("amount", 0.0) if "error" not in cost else 0.0,
        "risk_count":     len(risks),
        "action_count":   len(actions),
        "risks":          risks,
        "actions":        actions,
        "has_owner":      bool(
            profile.get("owner_email") or
            governance.get("owner", "—") not in ("—", "")
        ),
        "has_stream":     bool(profile.get("business_stream")),
    }


# ── Print ─────────────────────────────────────────────────────────────────────

def print_portfolio(rows: list[dict], period_start: str, period_end: str) -> None:
    n = len(rows)
    print()
    print(_SEP)
    print(f"  Agent Estate Roll-Up — {n} agent(s)   Period: {period_start}  →  {period_end}")
    print(_SEP)

    col_name   = 26
    col_owner  = 26
    col_stream = 18
    col_req    = 7
    col_cost   = 17
    col_risk   = 6
    col_action = 8

    header = (
        f"  {'Agent':<{col_name}} {'Owner':<{col_owner}} {'Business Stream':<{col_stream}}"
        f" {'Req':>{col_req}} {'Cost (7d)':>{col_cost}} {'Risks':>{col_risk}} {'Actions':>{col_action}}"
    )
    print(f"\n{header}")
    print(f"  {_SEP2}")

    total_requests = 0
    total_cost     = 0.0
    agents_with_risks     = 0
    agents_missing_owner  = 0
    agents_missing_stream = 0

    for r in rows:
        reqs = r["requests"]
        if isinstance(reqs, int):
            total_requests += reqs
        total_cost += r["cost_amount"]
        if r["risk_count"] > 0:
            agents_with_risks += 1
        if not r["has_owner"]:
            agents_missing_owner += 1
        if not r["has_stream"]:
            agents_missing_stream += 1

        risk_flag   = f"⚠ {r['risk_count']}"  if r["risk_count"]   > 0 else "✅"
        action_flag = f"→ {r['action_count']}" if r["action_count"] > 0 else "✅"

        print(
            f"  {str(r['name'])[:col_name-1]:<{col_name}}"
            f" {str(r['owner'])[:col_owner-1]:<{col_owner}}"
            f" {str(r['business_stream'])[:col_stream-1]:<{col_stream}}"
            f" {str(reqs):>{col_req}}"
            f" {str(r['cost_str']):>{col_cost}}"
            f" {risk_flag:>{col_risk}}"
            f" {action_flag:>{col_action}}"
        )

    print(f"  {_SEP2}")
    print(
        f"  {'TOTALS':<{col_name}} {'':^{col_owner}} {'':^{col_stream}}"
        f" {str(total_requests):>{col_req}} {f'{total_cost:.4f}':>{col_cost}}"
    )

    # ── Estate summary ────────────────────────────────────────────────────────
    print()
    print(f"  Estate Summary")
    print(f"  {'Active agents':<42}{n}")
    print(f"  {'Total requests (7d)':<42}{total_requests:,}")
    print(f"  {'Estimated total cost (7d)':<42}{total_cost:.4f}")
    print(f"  {'Agents with open risks':<42}{agents_with_risks}")
    print(f"  {'Agents missing ownership':<42}{agents_missing_owner}")
    print(f"  {'Agents missing business stream':<42}{agents_missing_stream}")

    # ── Spotlight ─────────────────────────────────────────────────────────────
    spotlight = [
        r for r in rows
        if r["risk_count"] > 0 or not r["has_owner"] or not r["has_stream"]
    ]
    if spotlight:
        print()
        print(f"  Agents needing attention:")
        for r in spotlight:
            flags = []
            if r["risk_count"] > 0:
                flags.append(f"{r['risk_count']} risk(s)")
            if not r["has_owner"]:
                flags.append("no owner")
            if not r["has_stream"]:
                flags.append("no business stream")
            print(f"  ⚠  {r['name']}: {', '.join(flags)}")
            for action in r["actions"]:
                print(f"       → {action}")
    else:
        print()
        print("  ✅  All agents have ownership, business stream, and no open risks.")

    print()
    print(_SEP)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main(portfolio_path: Path) -> None:
    if not portfolio_path.exists():
        print(f"Portfolio file not found: {portfolio_path}")
        print("Copy governance/portfolio.yaml.example to governance/portfolio.yaml and populate it.")
        sys.exit(1)

    agents = _load_portfolio(portfolio_path)
    if not agents:
        print(f"No agents found in {portfolio_path}")
        sys.exit(1)

    now   = datetime.now(tz=timezone.utc).date()
    start = now - timedelta(days=7)

    credential = DefaultAzureCredential()
    rows: list[dict] = []

    print(f"\nQuerying {len(agents)} agent(s) in portfolio…\n")
    for entry in agents:
        name = entry.get("name", "—")
        print(f"  [{name}] fetching data…")
        rows.append(_query_agent(entry, credential))

    print_portfolio(rows, str(start), str(now))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent estate portfolio roll-up report")
    parser.add_argument(
        "--portfolio",
        type=Path,
        default=_SAMPLE_ROOT / "governance" / "portfolio.yaml",
        help="Path to portfolio.yaml (default: governance/portfolio.yaml)",
    )
    args = parser.parse_args()
    main(args.portfolio)
