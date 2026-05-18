from pathlib import Path
import sys

# Ensure the sample directory is on sys.path so tests can import local modules.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import AzureCostRow
from classify_costs import classify_cost, classify_costs


def _row_with_tags(tags: dict, amount: float = 1.0) -> AzureCostRow:
	return AzureCostRow(
		date="2026-05-01",
		resource_id="r",
		resource_group="rg",
		service_name="svc",
		meter_category="cat",
		meter_subcategory="sub",
		cost_amount=amount,
		currency="EUR",
		tags=tags,
	)


def test_row_with_agent_id_is_direct():
	row = _row_with_tags({"agent_id": "sales-followup-agent"})
	assert classify_cost(row) == "direct"


def test_row_with_workload_id_is_direct():
	row = _row_with_tags({"workload_id": "crm-opportunity-followup"})
	assert classify_cost(row) == "direct"


def test_cost_category_indirect_is_indirect():
	row = _row_with_tags({"cost_category": "indirect"})
	assert classify_cost(row) == "indirect"


def test_cost_category_platform_is_platform():
	row = _row_with_tags({"cost_category": "platform"})
	assert classify_cost(row) == "platform"


def test_missing_required_metadata_is_unallocated():
	row = _row_with_tags({})
	assert classify_cost(row) == "unallocated"


def test_direct_precedence_over_shared_service():
	tags = {
		"shared_service": "true",
		"distribution_key": "weighted_agent_usage",
		"agent_id": "explicit-agent",
	}
	row = _row_with_tags(tags)
	assert classify_cost(row) == "direct"


def test_classify_costs_groups_and_sums():
	rows = [
		_row_with_tags({"agent_id": "a"}, amount=10.0),
		_row_with_tags({"cost_category": "indirect"}, amount=5.0),
		_row_with_tags({"cost_category": "platform"}, amount=3.0),
		_row_with_tags({}, amount=2.5),
	]
	groups = classify_costs(rows)
	assert len(groups["direct"]) == 1
	assert len(groups["indirect"]) == 1
	assert len(groups["platform"]) == 1
	assert len(groups["unallocated"]) == 1
