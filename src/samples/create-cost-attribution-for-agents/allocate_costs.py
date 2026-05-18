"""Cost allocation utilities.

Convert classified Azure cost rows into `CostLedgerEntry` records using
simple distribution keys. This module is intentionally deterministic and
keeps logic minimal for the workshop sample.
"""

from __future__ import annotations

from typing import List, Dict, Optional
from collections import defaultdict

from models import (
    AzureCostRow,
    AgentRuntimeEvent,
    CostLedgerEntry,
    ValueLedgerEntry,
    AgentEconomicsSummary,
)
from classify_costs import classify_cost


def _normalize_tags(tags: Dict[str, str] | None) -> Dict[str, str]:
    if not tags:
        return {}
    return {str(k).lower(): ("" if v is None else str(v)) for k, v in tags.items()}


def _aggregate_runtime(events: List[AgentRuntimeEvent]) -> Dict[str, Dict[str, float]]:
    agg: Dict[str, Dict[str, float]] = {}
    for e in events:
        a = e.agent_id
        if a not in agg:
            agg[a] = {
                "token_count": 0.0,
                "runtime_seconds": 0.0,
                "tool_call_count": 0.0,
                "log_volume_gb": 0.0,
                "request_count": 0.0,
                "workload_id": None,
            }
        agg[a]["token_count"] += float(e.token_count or 0)
        agg[a]["runtime_seconds"] += float(e.runtime_seconds or 0)
        agg[a]["tool_call_count"] += float(e.tool_call_count or 0)
        agg[a]["log_volume_gb"] += float(e.log_volume_gb or 0)
        agg[a]["request_count"] += float(e.request_count or 0)
        if not agg[a]["workload_id"] and getattr(e, "workload_id", None):
            agg[a]["workload_id"] = e.workload_id
    return agg


def allocate_costs(
    cost_rows: List[AzureCostRow],
    runtime_events: List[AgentRuntimeEvent],
    rules: Dict,
) -> List[CostLedgerEntry]:
    """Allocate costs from `cost_rows` to agents using `runtime_events`.

    `rules` is a dictionary typically parsed from ``allocation_rules.yaml``.
    Returns a list of `CostLedgerEntry` objects describing the allocations.
    """

    period = rules.get("period")
    source = rules.get("source", "azure-cost-export")

    runtime_agg = _aggregate_runtime(runtime_events)

    # Precompute totals used by indirect/platform allocations
    total_log = sum(v["log_volume_gb"] for v in runtime_agg.values())
    total_tokens = sum(v["token_count"] for v in runtime_agg.values())
    total_runtime = sum(v["runtime_seconds"] for v in runtime_agg.values())
    total_tool_calls = sum(v["tool_call_count"] for v in runtime_agg.values())
    total_requests = sum(v["request_count"] for v in runtime_agg.values())

    ledger: List[CostLedgerEntry] = []

    # Deterministic agent ordering
    agent_ids = sorted(runtime_agg.keys())

    for row in cost_rows:
        cat = classify_cost(row)
        tags = _normalize_tags(row.tags)
        original = float(row.cost_amount or 0.0)
        timestamp = row.date
        this_period = period or (row.date[:7] if row.date else "")

        if cat == "direct":
            agent_id = tags.get("agent_id")
            workload_id = tags.get("workload_id")
            # infer workload if missing
            if not workload_id and agent_id and agent_id in runtime_agg:
                workload_id = runtime_agg[agent_id].get("workload_id")

            entry = CostLedgerEntry(
                entry_type="cost_allocation",
                timestamp=timestamp,
                period=this_period,
                agent_id=agent_id,
                workload_id=workload_id,
                cost_category="direct",
                source_resource_id=row.resource_id,
                source_service_name=row.service_name,
                original_cost_amount=original,
                allocated_cost_amount=original,
                currency=row.currency,
                allocation_method=rules.get("direct", {}).get("method", "direct_tag_mapping"),
                distribution_key="agent_id/workload_id",
                allocation_confidence="high",
                explanation="Direct cost mapped using agent_id/workload_id tags.",
                source=source,
            )
            ledger.append(entry)
            continue

        if cat == "indirect":
            # allocate by log_volume_gb, fallback to request_count
            key = rules.get("indirect", {}).get("default_distribution_key", "log_volume_gb")
            fallback = rules.get("indirect", {}).get("fallback_distribution_key", "request_count")

            # choose metric
            if total_log > 0:
                metric = "log_volume_gb"
                totals = total_log
            elif total_requests > 0:
                metric = "request_count"
                totals = total_requests
            else:
                # Nothing to allocate against: make visible unallocated entry
                entry = CostLedgerEntry(
                    entry_type="cost_allocation",
                    timestamp=timestamp,
                    period=this_period,
                    agent_id=None,
                    workload_id=None,
                    cost_category="indirect",
                    source_resource_id=row.resource_id,
                    source_service_name=row.service_name,
                    original_cost_amount=original,
                    allocated_cost_amount=original,
                    currency=row.currency,
                    allocation_method="keep_unallocated_visible",
                    distribution_key=None,
                    allocation_confidence="none",
                    explanation="Indirect cost could not be allocated because no usage metrics were available.",
                    source=source,
                )
                ledger.append(entry)
                continue

            # allocate across agents
            allocations: List[tuple[str, float]] = []
            for aid in agent_ids:
                agent_metric = runtime_agg[aid].get(metric, 0.0)
                share = (agent_metric / totals) if totals > 0 else 0.0
                allocations.append((aid, share * original))

            # make deterministic: adjust last agent to conserve total
            allocated_sum = sum(a for _, a in allocations)
            if allocations:
                diff = original - allocated_sum
                allocations[-1] = (allocations[-1][0], allocations[-1][1] + diff)

            for aid, amt in allocations:
                entry = CostLedgerEntry(
                    entry_type="cost_allocation",
                    timestamp=timestamp,
                    period=this_period,
                    agent_id=aid,
                    workload_id=runtime_agg[aid].get("workload_id"),
                    cost_category="indirect",
                    source_resource_id=row.resource_id,
                    source_service_name=row.service_name,
                    original_cost_amount=original,
                    allocated_cost_amount=float(amt),
                    currency=row.currency,
                    allocation_method="usage_based_allocation",
                    distribution_key=metric,
                    allocation_confidence="medium",
                    explanation="Indirect cost allocated by {}.".format(metric),
                    source=source,
                )
                ledger.append(entry)
            continue

        if cat == "platform":
            # weighted usage allocation
            weights = rules.get("platform", {}).get("weights", {})
            w_token = float(weights.get("token_share", 0.5))
            w_runtime = float(weights.get("runtime_share", 0.3))
            w_tool = float(weights.get("tool_call_share", 0.2))

            allocations: List[tuple[str, float]] = []
            # compute shares
            for aid in agent_ids:
                ag = runtime_agg[aid]
                token_share = (ag["token_count"] / total_tokens) if total_tokens > 0 else 0.0
                runtime_share = (ag["runtime_seconds"] / total_runtime) if total_runtime > 0 else 0.0
                tool_share = (ag["tool_call_count"] / total_tool_calls) if total_tool_calls > 0 else 0.0
                weighted = w_token * token_share + w_runtime * runtime_share + w_tool * tool_share
                allocations.append((aid, weighted * original))

            allocated_sum = sum(a for _, a in allocations)
            if allocations:
                diff = original - allocated_sum
                allocations[-1] = (allocations[-1][0], allocations[-1][1] + diff)

            for aid, amt in allocations:
                entry = CostLedgerEntry(
                    entry_type="cost_allocation",
                    timestamp=timestamp,
                    period=this_period,
                    agent_id=aid,
                    workload_id=runtime_agg[aid].get("workload_id"),
                    cost_category="platform",
                    source_resource_id=row.resource_id,
                    source_service_name=row.service_name,
                    original_cost_amount=original,
                    allocated_cost_amount=float(amt),
                    currency=row.currency,
                    allocation_method="weighted_platform_allocation",
                    distribution_key=rules.get("platform", {}).get("distribution_key", "weighted_agent_usage"),
                    allocation_confidence="medium",
                    explanation="Platform cost allocated by weighted usage: token share, runtime share and tool-call share.",
                    source=source,
                )
                ledger.append(entry)
            continue

        # unallocated
        entry = CostLedgerEntry(
            entry_type="cost_allocation",
            timestamp=timestamp,
            period=this_period,
            agent_id=None,
            workload_id=None,
            cost_category="unallocated",
            source_resource_id=row.resource_id,
            source_service_name=row.service_name,
            original_cost_amount=original,
            allocated_cost_amount=original,
            currency=row.currency,
            allocation_method="keep_unallocated_visible",
            distribution_key=None,
            allocation_confidence="none",
            explanation="Cost kept visible as unallocated because required attribution tags were missing.",
            source=source,
        )
        ledger.append(entry)

    return ledger


def build_agent_economics_summary(
    cost_entries: List[CostLedgerEntry],
    value_entries: List[ValueLedgerEntry],
    runtime_events: List[AgentRuntimeEvent],
    rules: Dict,
) -> List[AgentEconomicsSummary]:
    """Build per-agent economics summaries by combining costs and value.

    Returns a list of `AgentEconomicsSummary` objects, one per agent.
    """

    runtime_agg = _aggregate_runtime(runtime_events)

    # Agents come from runtime, value entries, or cost ledger entries
    agent_ids = set(runtime_agg.keys())
    for v in value_entries:
        if getattr(v, "agent_id", None):
            agent_ids.add(v.agent_id)
    for c in cost_entries:
        if c.agent_id:
            agent_ids.add(c.agent_id)

    total_input_cost = sum(float(c.allocated_cost_amount or 0.0) for c in cost_entries)
    unallocated_visible_cost = sum(float(c.allocated_cost_amount or 0.0) for c in cost_entries if not c.agent_id)
    assignable_pool = total_input_cost - unallocated_visible_cost

    # Aggregate value entries
    val_by_agent: Dict[str, Dict[str, float]] = {}
    for v in value_entries:
        aid = v.agent_id
        if aid not in val_by_agent:
            val_by_agent[aid] = {"efficiency": 0.0, "outcome": 0.0}
        val_by_agent[aid]["efficiency"] += float(getattr(v, "efficiency_value", 0.0) or 0.0)
        val_by_agent[aid]["outcome"] += float(getattr(v, "outcome_value", 0.0) or 0.0)

    # Aggregate costs by agent and category
    costs_by_agent: Dict[str, Dict[str, float]] = {}
    for c in cost_entries:
        aid = c.agent_id
        cat = c.cost_category
        if not aid:
            continue
        if aid not in costs_by_agent:
            costs_by_agent[aid] = {"direct": 0.0, "indirect": 0.0, "platform": 0.0}
        costs_by_agent[aid][cat] = costs_by_agent[aid].get(cat, 0.0) + float(c.allocated_cost_amount or 0.0)

    summaries: List[AgentEconomicsSummary] = []
    period = rules.get("period")

    for aid in sorted(agent_ids):
        eff = val_by_agent.get(aid, {}).get("efficiency", 0.0)
        outv = val_by_agent.get(aid, {}).get("outcome", 0.0)
        total_value = eff + outv
        direct = costs_by_agent.get(aid, {}).get("direct", 0.0)
        indirect = costs_by_agent.get(aid, {}).get("indirect", 0.0)
        platform = costs_by_agent.get(aid, {}).get("platform", 0.0)
        total_cost = direct + indirect + platform
        net = total_value - total_cost
        cost_to_value = (total_cost / total_value) if total_value > 0 else 0.0
        coverage = (total_cost / assignable_pool) if assignable_pool > 0 else 0.0

        workload_id = None
        if aid in runtime_agg:
            workload_id = runtime_agg[aid].get("workload_id")

        # Determine currency for this agent: prefer a cost entry currency, else value ledger currency
        currency = ""
        for c in cost_entries:
            if c.agent_id == aid and getattr(c, "currency", None):
                currency = c.currency
                break
        if not currency:
            for v in value_entries:
                if getattr(v, "currency", None):
                    currency = v.currency
                    break

        explanation = (
            f"Agent {aid} contributed to outcomes (contributed to {outv:.2f}) and efficiency ({eff:.2f}). "
            f"Allocated costs: direct {direct:.2f}, indirect {indirect:.2f}, platform {platform:.2f}. "
            f"Net value (total value - total cost): {net:.2f}. "
            f"Unallocated visible pool: {unallocated_visible_cost:.2f}."
        )

        summary = AgentEconomicsSummary(
            period=period or "",
            agent_id=aid,
            workload_id=workload_id,
            currency=currency,
            efficiency_value=eff,
            outcome_value=outv,
            total_attributed_value=total_value,
            direct_cost=direct,
            indirect_allocated_cost=indirect,
            platform_allocated_cost=platform,
            unallocated_visible_cost=unallocated_visible_cost,
            total_attributed_cost=total_cost,
            net_value=net,
            cost_to_value_ratio=cost_to_value,
            allocation_coverage_percentage=coverage,
            explanation=explanation,
        )
        summaries.append(summary)

    return summaries
