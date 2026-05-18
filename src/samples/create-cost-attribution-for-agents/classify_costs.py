"""Cost classification utilities.

Provides deterministic classification of `AzureCostRow` instances into
one of: "direct", "indirect", "platform", "unallocated".

Rules (implemented):
- Direct: explicit `cost_category` or `allocation_scope` == "direct",
  or `agent_id`/`workload_id` tags are present (these take precedence).
- Indirect: `cost_category` or `allocation_scope` == "indirect".
- Platform: `cost_category` or `allocation_scope` == "platform",
  or `shared_service` == "true" and `distribution_key` ==
  "weighted_agent_usage".
- Unallocated: nothing above matches.
"""

from __future__ import annotations

from typing import List, Dict

from models import AzureCostRow


def _normalize_tags(tags: Dict[str, str] | None) -> Dict[str, str]:
	if not tags:
		return {}
	out: Dict[str, str] = {}
	for k, v in tags.items():
		if k is None:
			continue
		key = str(k).lower()
		val = "" if v is None else str(v).lower()
		out[key] = val
	return out


def classify_cost(row: AzureCostRow) -> str:
	"""Classify a single AzureCostRow.

	Returns one of: "direct", "indirect", "platform", "unallocated".
	"""

	tags = _normalize_tags(row.tags)

	# Direct precedence when agent/workload is present
	if tags.get("agent_id") or tags.get("workload_id"):
		return "direct"

	# Explicit direct markers
	if tags.get("cost_category") == "direct" or tags.get("allocation_scope") == "direct":
		return "direct"

	# Indirect
	if tags.get("cost_category") == "indirect" or tags.get("allocation_scope") == "indirect":
		return "indirect"

	# Platform
	if tags.get("cost_category") == "platform" or tags.get("allocation_scope") == "platform":
		return "platform"

	if tags.get("shared_service") == "true" and tags.get("distribution_key") == "weighted_agent_usage":
		return "platform"

	# Fallback: leave as unallocated so it remains visible
	return "unallocated"


def classify_costs(rows: List[AzureCostRow]) -> dict[str, List[AzureCostRow]]:
	groups: dict[str, List[AzureCostRow]] = {
		"direct": [],
		"indirect": [],
		"platform": [],
		"unallocated": [],
	}
	for r in rows:
		cat = classify_cost(r)
		if cat not in groups:
			groups["unallocated"].append(r)
		else:
			groups[cat].append(r)
	return groups

