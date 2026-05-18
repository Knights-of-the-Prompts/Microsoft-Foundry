from pathlib import Path
import sys

# Ensure local sample modules import correctly
sys.path.insert(0, str(Path(__file__).resolve().parent))

from models import (
	AzureCostRow,
	AgentRuntimeEvent,
	ValueLedgerEntry,
)
from allocate_costs import allocate_costs, build_agent_economics_summary


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


def _events():
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


def _values():
	return [
		ValueLedgerEntry(
			timestamp="2026-05-01T09:05:00Z",
			agent_id="sales-followup-agent",
			workload_id="crm-opportunity-followup",
			outcome_id="opportunity-progressed",
			efficiency_value=420.0,
			outcome_value=2500.0,
			currency="EUR",
			description="opportunity progressed / revenue opportunity advanced",
		),
		ValueLedgerEntry(
			timestamp="2026-05-01T10:05:00Z",
			agent_id="support-resolution-agent",
			workload_id="incident-resolution",
			outcome_id="incident-resolved",
			efficiency_value=300.0,
			outcome_value=1200.0,
			currency="EUR",
			description="incident resolved / customer risk reduced",
		),
	]


RULES = {
	"period": "2026-05",
	"source": "azure-cost-export-sample",
	"direct": {"method": "direct_tag_mapping"},
	"indirect": {"default_distribution_key": "log_volume_gb", "fallback_distribution_key": "request_count"},
	"platform": {"distribution_key": "weighted_agent_usage", "weights": {"token_share": 0.5, "runtime_share": 0.3, "tool_call_share": 0.2}},
	"unallocated": {"mode": "keep_visible"},
}


def approx(a, b, tol=1e-6):
	return abs(a - b) <= tol


def test_agent_economics_relations():
	rows = [
		_row({"agent_id": "sales-followup-agent"}, 12.40),
		_row({"cost_category": "indirect"}, 18.00),
		_row({"cost_category": "platform"}, 30.00),
		_row({}, 6.25),
	]
	events = _events()
	values = _values()

	ledger = allocate_costs(rows, events, RULES)
	summaries = build_agent_economics_summary(ledger, values, events, RULES)

	# both agents present
	ids = {s.agent_id for s in summaries}
	assert "sales-followup-agent" in ids
	assert "support-resolution-agent" in ids

	# relations hold for each agent
	for s in summaries:
		assert approx(s.efficiency_value + s.outcome_value, s.total_attributed_value)
		assert approx(s.total_attributed_value - s.total_attributed_cost, s.net_value)
		if s.total_attributed_value > 0:
			assert approx(s.total_attributed_cost / s.total_attributed_value, s.cost_to_value_ratio)

	# visible unallocated not assigned to any agent
	unallocated = sum(e.allocated_cost_amount for e in ledger if not e.agent_id)
	assert approx(unallocated, 6.25)

