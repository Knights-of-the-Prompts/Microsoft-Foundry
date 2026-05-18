"""Offline example for Cost Attribution for Accountable Agents.

This script demonstrates loading deterministic sample data for the
cost-attribution sample. It intentionally performs no allocation or
business logic and only prints counts of loaded rows.
"""

from pathlib import Path

from loaders import (
	load_cost_rows,
	load_runtime_events,
	load_value_entries,
	load_cost_rows_from_blob,
)
from classify_costs import classify_costs
from allocate_costs import allocate_costs, build_agent_economics_summary
from ledger_store import CostLedgerStore

import json
from pathlib import Path

try:
	import yaml  # type: ignore
except Exception:
	yaml = None


def main() -> None:
	base = Path(__file__).parent
	# Choose cost source: local file (default) or blob (COST_SOURCE=blob)
	import os

	if os.getenv("COST_SOURCE", "file") == "blob":
		# read required blob env vars. For production prefer Managed Identity.
		conn = os.getenv("AZ_BLOB_CONNECTION_STRING")
		container = os.getenv("AZ_BLOB_CONTAINER")
		blob = os.getenv("AZ_BLOB_BLOBNAME")
		costs = load_cost_rows_from_blob(connection_string=conn, container_name=container, blob_name=blob)
	else:
		costs = load_cost_rows(base / "data" / "azure-cost-export-sample.csv")
	events = load_runtime_events(base / "data" / "agent-runtime-events.json")
	values = load_value_entries(base / "data" / "value-ledger-sample.json")

	# Load allocation rules with a safe fallback if PyYAML is not present.
	rules_path = base / "allocation_rules.yaml"
	if yaml:
		with open(rules_path, encoding="utf-8") as fh:
			rules = yaml.safe_load(fh)
	else:
		# Minimal fallback to keep example runnable
		rules = {
			"period": "2026-05",
			"source": "azure-cost-export-sample",
			"direct": {"method": "direct_tag_mapping"},
			"indirect": {"default_distribution_key": "log_volume_gb", "fallback_distribution_key": "request_count"},
			"platform": {"distribution_key": "weighted_agent_usage", "weights": {"token_share": 0.5, "runtime_share": 0.3, "tool_call_share": 0.2}},
			"unallocated": {"mode": "keep_visible"},
		}

	groups = classify_costs(costs)

	def _sum(rows):
		return sum(r.cost_amount for r in rows)

	print(f"Loaded {len(costs)} cost rows")
	print(f"Loaded {len(events)} runtime events")
	print(f"Loaded {len(values)} value ledger entries")
	print("")
	print(f"Direct total: {_sum(groups['direct']):.2f}")
	print(f"Indirect total: {_sum(groups['indirect']):.2f}")
	print(f"Platform total: {_sum(groups['platform']):.2f}")
	print(f"Unallocated total: {_sum(groups['unallocated']):.2f}")

	# Allocate costs and store ledger entries
	ledger_store = CostLedgerStore()
	allocations = allocate_costs(costs, events, rules)
	for e in allocations:
		ledger_store.append(e)

	cost_entries = ledger_store.list_entries()

	# Print cost ledger entries
	print("\nCost ledger entries:")
	for e in cost_entries:
		aid = e.agent_id or "UNALLOCATED"
		print(f"- {aid} | {e.cost_category} | {e.allocated_cost_amount:.2f} | {e.explanation}")

	# Build agent economics summaries
	summaries = build_agent_economics_summary(cost_entries, values, events, rules)

	print("\nAgent economics summary:")
	for s in summaries:
		print(f"- Agent: {s.agent_id} (workload: {s.workload_id})")
		print(f"  Period: {s.period}")
		print(f"  Efficiency value: {s.efficiency_value:.2f}")
		print(f"  Outcome value (contributed to): {s.outcome_value:.2f}")
		print(f"  Total attributed value: {s.total_attributed_value:.2f}")
		print(f"  Direct cost: {s.direct_cost:.2f}")
		print(f"  Indirect allocated cost: {s.indirect_allocated_cost:.2f}")
		print(f"  Platform allocated cost: {s.platform_allocated_cost:.2f}")
		print(f"  Visible unallocated cost (context): {s.unallocated_visible_cost:.2f}")
		print(f"  Total attributed cost: {s.total_attributed_cost:.2f}")
		print(f"  Net value: {s.net_value:.2f}")
		print(f"  Cost-to-value ratio: {s.cost_to_value_ratio:.6f}")
		print(f"  Allocation coverage: {s.allocation_coverage_percentage:.3f}")
		print(f"  Explanation: {s.explanation}")


if __name__ == "__main__":
	main()

