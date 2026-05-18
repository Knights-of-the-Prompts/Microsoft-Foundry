"""Data models for Cost Attribution sample.

This module defines simple, typed dataclasses used by the cost
attribution sample. These are intentionally minimal and focus on data
shape rather than behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class AgentRuntimeEvent:
	event_id: str
	timestamp: str
	agent_id: str
	workload_id: str
	business_process: str
	value_stream: str
	token_count: float
	runtime_seconds: float
	tool_call_count: float
	log_volume_gb: float
	request_count: float
	outcome_id: str


@dataclass
class AzureCostRow:
	date: str
	resource_id: str
	resource_group: str
	service_name: str
	meter_category: str
	meter_subcategory: str
	cost_amount: float
	currency: str
	tags: Dict[str, str]


@dataclass
class ValueLedgerEntry:
	timestamp: str
	agent_id: str
	workload_id: str
	outcome_id: str
	efficiency_value: float
	outcome_value: float
	currency: str
	description: str


@dataclass
class CostLedgerEntry:
	entry_type: str
	timestamp: str
	period: str
	agent_id: Optional[str]
	workload_id: Optional[str]
	cost_category: str
	source_resource_id: str
	source_service_name: str
	original_cost_amount: float
	allocated_cost_amount: float
	currency: str
	allocation_method: str
	distribution_key: Optional[str]
	allocation_confidence: str
	explanation: str
	source: str


@dataclass
class AgentEconomicsSummary:
	period: str
	agent_id: str
	workload_id: str
	currency: str
	efficiency_value: float
	outcome_value: float
	total_attributed_value: float
	direct_cost: float
	indirect_allocated_cost: float
	platform_allocated_cost: float
	unallocated_visible_cost: float
	total_attributed_cost: float
	net_value: float
	cost_to_value_ratio: float
	allocation_coverage_percentage: float
	explanation: str

