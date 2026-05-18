from pathlib import Path
import sys

# Ensure local sample modules import correctly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import AzureCostRow, AgentRuntimeEvent
from allocate_costs import allocate_costs


RULES = {
	"period": "2026-05",
	"source": "azure-cost-export-sample",
	"direct": {"method": "direct_tag_mapping"},
	"indirect": {"default_distribution_key": "log_volume_gb", "fallback_distribution_key": "request_count"},
	"platform": {"distribution_key": "weighted_agent_usage", "weights": {"token_share": 0.5, "runtime_share": 0.3, "tool_call_share": 0.2}},
	"unallocated": {"mode": "keep_visible"},
}


def _row(tags: dict, amount: float, date: str = "2026-05-01") -> AzureCostRow:
	return AzureCostRow(
		date=date,
		resource_id="r",
		resource_group="rg",
		service_name="svc",
		meter_category="cat",
		meter_subcategory="sub",
		cost_amount=amount,
		currency="EUR",
		tags=tags,
	)


def _events() -> list[AgentRuntimeEvent]:
	return [
		AgentRuntimeEvent(
			event_id="evt-1",
			timestamp="2026-05-01T09:00:00Z",
			agent_id="sales-followup-agent",
			workload_id="crm-opportunity-followup",
			business_process="sales",
			value_stream="revenue-growth",
			token_count=60000,
			runtime_seconds=420,
			tool_call_count=18,
			log_volume_gb=1.2,
			request_count=35,
			outcome_id="opportunity-progressed",
		),
		AgentRuntimeEvent(
			event_id="evt-2",
			timestamp="2026-05-01T10:00:00Z",
			agent_id="support-resolution-agent",
			workload_id="incident-resolution",
			business_process="support",
			value_stream="customer-retention",
			token_count=30000,
			runtime_seconds=300,
			tool_call_count=12,
			log_volume_gb=0.8,
			request_count=25,
			outcome_id="incident-resolved",
		),
	]


def approx(a, b, tol=1e-6):
	return abs(a - b) <= tol


def test_direct_cost_allocated_to_tagged_agent():
	row = _row({"agent_id": "sales-followup-agent", "workload_id": "crm-opportunity-followup"}, 12.40)
	ledger = allocate_costs([row], _events(), RULES)
	# should produce a single allocation entry assigned to the agent
	assert len(ledger) == 1
	e = ledger[0]
	assert e.agent_id == "sales-followup-agent"
	assert e.workload_id == "crm-opportunity-followup"
	assert approx(e.allocated_cost_amount, 12.40)


def test_indirect_cost_allocated_by_log_volume():
	row = _row({"cost_category": "indirect"}, 18.00)
	ledger = allocate_costs([row], _events(), RULES)
	# expect two entries (one per agent)
	assert len(ledger) == 2
	sums = {e.agent_id: e.allocated_cost_amount for e in ledger}
	assert approx(sums["sales-followup-agent"], 10.8)
	assert approx(sums["support-resolution-agent"], 7.2)


def test_platform_cost_allocated_by_weighted_usage():
	row = _row({"cost_category": "platform"}, 30.00)
	ledger = allocate_costs([row], _events(), RULES)
	assert len(ledger) == 2
	sums = {e.agent_id: e.allocated_cost_amount for e in ledger}
	total = sum(sums.values())
	assert approx(total, 30.0)
	# basic sanity: sales should get a larger share than support
	assert sums["sales-followup-agent"] > sums["support-resolution-agent"]


def test_unallocated_cost_remains_visible():
	row = _row({"accountable_agents_demo": "true"}, 6.25)
	ledger = allocate_costs([row], _events(), RULES)
	assert len(ledger) == 1
	e = ledger[0]
	assert e.agent_id is None
	assert e.workload_id is None
	assert e.cost_category == "unallocated"
	assert approx(e.allocated_cost_amount, 6.25)


def test_cost_conservation_for_mixed_rows():
	rows = [
		_row({"agent_id": "sales-followup-agent"}, 12.40),
		_row({"cost_category": "indirect"}, 18.00),
		_row({"cost_category": "platform"}, 30.00),
		_row({}, 6.25),
	]
	ledger = allocate_costs(rows, _events(), RULES)
	total_input = sum(r.cost_amount for r in rows)
	total_allocated = sum(e.allocated_cost_amount for e in ledger)
	assert approx(total_input, total_allocated)

