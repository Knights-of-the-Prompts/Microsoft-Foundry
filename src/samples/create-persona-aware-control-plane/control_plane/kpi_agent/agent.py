"""KPI Agent — persona-aware control plane intelligence.

Interprets a KPI entered by a persona, maps it to required signals,
gathers those signals via the ToolRegistry, and produces a complete
control plane response including a weekly digest, recommended actions,
agent ideas, and evidence events.

Design rules:
- The KPI Agent NEVER directly calls mock connectors or reads data files.
- It asks the ToolRegistry what tools are available and what signals to gather.
- Every signal used carries source_metadata (source_mode, confidence, etc.).
- Vague KPIs trigger clarification questions; the response is still returned
  with maturity_level="vague" and clarification_questions populated.
- All deterministic scenario data lives in the _SCENARIOS dict below.
  This makes the demo self-contained without a language model dependency.

Phase 2 upgrade path:
  Replace _resolve_scenario() with an LLM call to azure-ai-projects.
  Everything else (ToolRegistry, evidence trail, stores) stays the same.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from control_plane.connectors.registry import ToolRegistry
from control_plane.access_readiness import AccessReadinessAgent
from control_plane.models.governance import (
    AgentIdea,
    AgentRequest,
    AgentRequestStatus,
    EvidenceEvent,
    ImprovesCategory,
    ImplementationComplexity,
    RiskLevel,
)
from control_plane.models.personas import PERSONA_CATALOGUE, KPI, Persona
from control_plane.models.signals import Signal
from control_plane.stores import evidence_store, request_store


# ---------------------------------------------------------------------------
# Vague KPI detection
# ---------------------------------------------------------------------------

_VAGUE_KEYWORDS = {
    "improve", "better", "enhance", "increase", "decrease", "reduce",
    "optimize", "fix", "manage", "handle", "deal with",
}

_VAGUE_KPI_PATTERNS: Dict[str, List[str]] = {
    "compliance_officer": [
        "Which regulatory or internal policy domain should this KPI support? "
        "(e.g. GDPR, ISO 27001, SOC 2, internal AI governance policy)",
        "What evidence would prove that audit readiness improved? "
        "(e.g. audit finding closure rate, percentage of agents with evidence trail coverage)",
        "Which agent risk tiers are in scope? "
        "(e.g. all agents, only production agents with access to sensitive data)",
    ],
    "cfo": [
        "Are you optimizing absolute spend, unit cost per request, or cost per business outcome?",
        "Which value signals should not be degraded while reducing cost? "
        "(e.g. revenue per agent-assisted deal, case resolution speed)",
        "Should shared platform costs be allocated to agents, business units, or outcomes?",
    ],
    "cto": [
        "Which strategic dimension needs improvement: architecture reuse, platform consolidation, "
        "technology debt reduction, or innovation readiness?",
        "Which business units or product lines are in scope for this KPI?",
        "What is the current baseline measurement, and how is it being tracked today?",
    ],
    "it_manager": [
        "Which class of operational issue are you targeting: agent tool failures, "
        "connector health degradation, or infrastructure capacity incidents?",
        "What is the current incident rate baseline and MTTR, and what is the reduction target?",
        "Should this KPI cover only production environments or also staging and dev?",
    ],
    "security_officer": [
        "Which type of sensitive data exposure are you targeting: PII, credentials, "
        "IP, or regulated data?",
        "Are you measuring exposure risk (potential) or confirmed exposure events (actual)?",
        "Which agent permission model is in scope: delegated user identity, "
        "service principal, or both?",
    ],
    "business_owner": [
        "Which business outcome metric should this KPI track: revenue, "
        "cost savings, or customer satisfaction?",
        "What is the current baseline performance and the improvement target?",
        "Should agent-attributed value be measured independently from non-agent-assisted outcomes?",
    ],
    "product_owner": [
        "Which delivery metric matters most: cycle time, throughput, defect rate, "
        "or predictability?",
        "Are you measuring agent-enabled features specifically, or all product delivery?",
        "What is the current sprint velocity baseline you want to improve against?",
    ],
    "service_owner": [
        "Which service tier or escalation category is producing the most support load?",
        "Is the problem in initial routing, handover quality, or resolution completeness?",
        "What SLA or CSAT baseline should this KPI be measured against?",
    ],
}

_DEFAULT_CLARIFICATION_QUESTIONS = [
    "What does success look like for this KPI in measurable terms?",
    "What is the current baseline you are measuring improvement against?",
    "Which systems, agents, or business processes are in scope?",
]


def _is_vague(kpi_text: str) -> bool:
    """Return True if the KPI text is too vague to map directly to signals."""
    lower = kpi_text.lower().strip()
    words = set(lower.split())
    if len(lower) < 25:
        return True
    vague_hit = bool(words & _VAGUE_KEYWORDS)
    specific_terms = {
        "unauthorized", "audit", "compliance", "cost", "uptime", "incident",
        "sla", "pipeline", "latency", "error rate", "coverage", "ownership",
        "token", "spend", "roi", "throughput", "vulnerability", "sign-in",
        "exposure", "resolution", "escalation", "reuse", "pattern", "%", "$",
    }
    has_specifics = any(t in lower for t in specific_terms)
    return vague_hit and not has_specifics


def _classify_maturity(kpi_text: str) -> str:
    if _is_vague(kpi_text):
        return "vague"
    lower = kpi_text.lower()
    has_number = any(c.isdigit() for c in lower)
    has_time = any(t in lower for t in [
        "day", "week", "month", "quarter", "sprint", "q1", "q2", "q3", "q4",
    ])
    if has_number and has_time:
        return "well_articulated"
    return "usable"


# ---------------------------------------------------------------------------
# Scenario catalogue — deterministic demo data per persona
# ---------------------------------------------------------------------------

_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "compliance_officer": {
        "default_kpi": "Improve audit readiness for high-risk AI agents.",
        "normalized_kpi": {
            "domain": "AI governance / regulatory compliance",
            "metric": "audit trail coverage and open compliance findings",
            "target": "100% coverage, 0 open P1 findings",
            "time_horizon": "30 days",
            "scope": "high-risk agents in production",
        },
        "confidence_score": 0.72,
        "required_signal_types": [
            "security_events", "user_activity", "compliance_status",
            "agent_registrations", "agent_invocations",
        ],
        "selected_platforms": ["azure", "microsoft365", "agent365", "servicenow"],
        "digest": {
            "title": "Weekly Compliance Digest — High-Risk AI Agents",
            "executive_summary": (
                "Audit readiness for high-risk agents is at 73%. "
                "3 agents lack full evidence trail coverage. "
                "2 open P2 security incidents exceed the 24h SLA. "
                "DLP violations in M365 indicate potential data boundary breaches."
            ),
            "top_risks": [
                "3 anomalous sign-in events detected for agent service principals (Azure)",
                "2 open P2 security incidents unresolved for >24h (ServiceNow)",
                "15 files shared externally without classification labels (M365)",
                "1 agent (reporting-agent) has no assigned owner (Agent 365)",
            ],
            "top_opportunities": [
                "Automated evidence trail agent could close the 27% audit coverage gap",
                "Connecting Agent 365 live API would surface ownership gaps in real time",
                "DLP policy tightening in M365 could eliminate external share violations",
            ],
            "value_signals": ["4,820 agent invocations — 0.3% error rate (Foundry)"],
            "cost_signals": ["Azure OpenAI: $820 MTD, AKS: $310 MTD (Azure)"],
            "reporting_signals": [
                "80% agent ownership coverage (Agent 365)",
                "93% SLA compliance — below 95% target (ServiceNow)",
            ],
            "risk_compliance_signals": [
                "3 high-severity security events (Azure)",
                "2 DLP violations (M365)",
                "2 open P2 incidents (ServiceNow)",
            ],
            "recommended_actions": [
                "Assign owner to reporting-agent in Agent 365 immediately.",
                "Investigate and close 3 anomalous sign-in events for agent service principals.",
                "Enable mandatory classification labels for all SharePoint/OneDrive agent outputs.",
                "Resolve 2 open P2 security incidents before next audit window.",
                "Configure live Agent 365 connector to automate ownership gap detection.",
            ],
            "evidence_gaps": [
                "Kubernetes pod health not mapped to compliance signals — configure K8s connector.",
            ],
            "affected_agents_resources": [
                "sp-foundry-agent (Azure — anomalous sign-in)",
                "sp-reporting-agent (Azure — anomalous sign-in)",
                "reporting-agent (Agent 365 — no owner)",
            ],
            "connectors_used": ["azure", "microsoft365", "agent365", "servicenow"],
        },
        "agent_ideas": [
            {
                "id": "comp_idea_01",
                "title": "Automated Evidence Trail Completeness Agent",
                "problem_statement": "3 of 5 agents have incomplete evidence trails, creating a 27% audit coverage gap.",
                "proposed_agent_capability": (
                    "Continuously monitors agent invocations and checks that each run "
                    "produces required evidence events."
                ),
                "required_tools": ["agent365.list_agent_registrations", "foundry.get_agent_invocations"],
                "required_data_sources": ["agent365", "foundry"],
                "expected_value": "Close 27% evidence coverage gap within 30 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Agent must have read-only access. Evidence events must be immutable.",
                "improves": [ImprovesCategory.COMPLIANCE, ImprovesCategory.EVIDENCE],
            },
            {
                "id": "comp_idea_02",
                "title": "Anomalous Sign-In Responder Agent",
                "problem_statement": "3 anomalous sign-in events for agent service principals require manual investigation.",
                "proposed_agent_capability": (
                    "Detects anomalous sign-in events in Azure, revokes compromised tokens "
                    "with human-in-the-loop approval, and opens a ServiceNow incident."
                ),
                "required_tools": ["azure.get_anomalous_signins", "servicenow.get_open_incidents"],
                "required_data_sources": ["azure", "servicenow"],
                "expected_value": "Reduce mean time to respond to sign-in anomalies from hours to minutes.",
                "risk_level": RiskLevel.HIGH,
                "implementation_complexity": ImplementationComplexity.HIGH,
                "governance_notes": "Requires write access to Entra ID. Must have human-in-the-loop approval.",
                "improves": [ImprovesCategory.RISK, ImprovesCategory.COMPLIANCE],
            },
            {
                "id": "comp_idea_03",
                "title": "DLP Policy Enforcement Monitor",
                "problem_statement": "15 files shared externally without sensitivity labels.",
                "proposed_agent_capability": "Monitors M365 sharing events and automatically applies classification labels.",
                "required_tools": ["microsoft365.get_external_shares"],
                "required_data_sources": ["microsoft365"],
                "expected_value": "Eliminate external share violations within 14 days.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Requires Sites.ReadWrite.All and Compliance permissions.",
                "improves": [ImprovesCategory.COMPLIANCE, ImprovesCategory.RISK],
            },
        ],
    },

    "cfo": {
        "default_kpi": "Maintain agent ROI above 3x and reduce unallocated AI spend below 10%.",
        "normalized_kpi": {
            "domain": "AI investment efficiency",
            "metric": "cost per request and agent-attributed pipeline growth",
            "target": "-20% cost per request, >10% pipeline growth",
            "time_horizon": "60 days",
            "scope": "all production agents",
        },
        "confidence_score": 0.85,
        "required_signal_types": [
            "cost_data", "model_usage", "revenue_impact",
            "agent_invocations", "opportunity_pipeline",
        ],
        "selected_platforms": ["azure", "foundry", "salesforce"],
        "digest": {
            "title": "Weekly CFO Digest — AI Investment Efficiency",
            "executive_summary": (
                "Current AI infrastructure cost is $1,240 MTD with 4,820 agent invocations "
                "($0.26/request). Agent-assisted pipeline represents $4.2M (14% of total). "
                "gpt-4o consumes 75% of token budget. Model mix optimisation could reduce "
                "cost per request by 15-25%."
            ),
            "top_risks": [
                "gpt-4o accounts for $820 of $1,240 MTD — single model dependency",
                "No cost per business outcome tracking — ROI is estimated, not measured",
                "Cost attribution tags missing for 2 Azure resources",
            ],
            "top_opportunities": [
                "Shift 30% of gpt-4o traffic to gpt-4o-mini for low-complexity tasks",
                "Agent-influenced pipeline at 14% — growth target of 18% is achievable",
                "Case resolution 18% faster with agent assist — quantify cost saving",
            ],
            "value_signals": [
                "$4.2M agent-influenced pipeline (14% of total) — 30 days (Salesforce)",
                "Case resolution 18% faster with agent assist (Salesforce)",
                "4,820 agent invocations — 0.3% error rate (Foundry)",
            ],
            "cost_signals": [
                "Azure OpenAI: $820 MTD (Foundry/Azure)",
                "AKS compute: $310 MTD (Azure)",
                "Storage: $110 MTD (Azure)",
                "Total: $1,240 MTD — $0.26/request",
            ],
            "reporting_signals": ["1.2M tokens across gpt-4o and gpt-4o-mini (Foundry)"],
            "risk_compliance_signals": [],
            "recommended_actions": [
                "Analyse gpt-4o vs gpt-4o-mini quality parity for low-complexity agent tasks.",
                "Implement cost-per-request tracking with per-agent cost tags in Azure.",
                "Set monthly budget alerts at 80% and 95% of the AI cost envelope.",
                "Quantify agent-attributed case resolution savings to close the value loop.",
            ],
            "evidence_gaps": [
                "No per-agent cost allocation — configure cost tags in Azure deployment.",
                "Live Salesforce connector not configured — pipeline data is mock.",
            ],
            "affected_agents_resources": [
                "sales-followup-agent (Foundry — 2,100 invocations)",
                "support-resolution-agent (Foundry — 1,980 invocations)",
            ],
            "connectors_used": ["azure", "foundry", "salesforce"],
        },
        "agent_ideas": [
            {
                "id": "cfo_idea_01",
                "title": "AI Cost Optimisation Advisor Agent",
                "problem_statement": "gpt-4o consumes 75% of token budget; no model routing by task complexity.",
                "proposed_agent_capability": "Analyses invocation patterns and recommends model routing rules.",
                "required_tools": ["foundry.get_model_usage", "foundry.get_agent_invocations", "azure.get_cost_summary"],
                "required_data_sources": ["foundry", "azure"],
                "expected_value": "15-25% reduction in cost per request within 30 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Model routing changes must be approved and logged.",
                "improves": [ImprovesCategory.COST, ImprovesCategory.OPERATIONS],
            },
            {
                "id": "cfo_idea_02",
                "title": "Per-Agent ROI Tracker",
                "problem_statement": "ROI is estimated from aggregate data — no per-agent attribution.",
                "proposed_agent_capability": (
                    "Tags every agent invocation with a cost allocation key, "
                    "joins with Salesforce pipeline and ServiceNow resolution data."
                ),
                "required_tools": ["azure.get_cost_summary", "salesforce.get_opportunity_pipeline", "foundry.get_agent_invocations"],
                "required_data_sources": ["azure", "salesforce", "foundry"],
                "expected_value": "Per-agent ROI visible within weekly CFO digest.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.HIGH,
                "governance_notes": "Cost ledger must align with existing cost attribution sample.",
                "improves": [ImprovesCategory.COST, ImprovesCategory.VALUE, ImprovesCategory.REPORTING],
            },
            {
                "id": "cfo_idea_03",
                "title": "Budget Alert Responder",
                "problem_statement": "No automated response when AI spend approaches monthly budget limit.",
                "proposed_agent_capability": (
                    "Monitors Azure cost alerts and throttles non-critical agent workloads "
                    "when the 80% budget threshold is reached."
                ),
                "required_tools": ["azure.get_cost_summary"],
                "required_data_sources": ["azure"],
                "expected_value": "Prevent budget overruns; reduce finance escalations.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Throttle actions require CTO co-approval. Must be logged.",
                "improves": [ImprovesCategory.COST, ImprovesCategory.OPERATIONS],
            },
        ],
    },

    "cto": {
        "default_kpi": "Increase reuse of approved agent patterns across business units.",
        "normalized_kpi": {
            "domain": "technology strategy / platform governance",
            "metric": "approved template reuse rate and architecture drift rate",
            "target": "> 80% template reuse, < 5% architecture drift",
            "time_horizon": "Q3",
            "scope": "all new agent deployments",
        },
        "confidence_score": 0.82,
        "required_signal_types": [
            "agent_registrations", "deployment_status", "project_health",
            "resource_health",
        ],
        "selected_platforms": ["azure", "kubernetes", "foundry", "agent365"],
        "digest": {
            "title": "Weekly CTO Digest — Platform Governance & Agent Pattern Reuse",
            "executive_summary": (
                "Template reuse tracking not yet implemented — architecture drift risk unquantified. "
                "3 agents registered with no documented template lineage. "
                "All Foundry deployments healthy. "
                "1 pod restarted 4 times (OOMKilled) — potential memory leak requiring platform review."
            ),
            "top_risks": [
                "Template reuse rate not tracked — risk of architectural drift across business units",
                "3 agents with no template lineage — not derived from approved Foundry patterns",
                "1 pod OOMKilled ×4 — potential memory leak in sales-followup-agent (Kubernetes)",
                "2 agents running on unapproved infrastructure outside Foundry platform",
            ],
            "top_opportunities": [
                "Standardise on Foundry templates — 3 agents lack documented template lineage",
                "Template compliance enforcement could increase reuse from unmeasured to >80% in Q3",
                "Kubernetes resource limits review could eliminate OOM restarts and reduce platform debt",
            ],
            "value_signals": ["3 Foundry agents, 4,820 invocations/week, 0.3% error rate"],
            "cost_signals": ["AKS: $310 MTD (Azure)"],
            "reporting_signals": [
                "All 8 K8s deployments available (Kubernetes)",
                "Foundry project healthy (Foundry)",
                "3 agent registrations — template lineage undocumented (Agent 365)",
            ],
            "risk_compliance_signals": [
                "1 pod OOMKilled ×4 (Kubernetes)",
                "2 agents outside approved platform — architecture drift (Agent 365)",
            ],
            "recommended_actions": [
                "Define and publish approved Foundry agent templates in the platform catalog.",
                "Implement template reuse tracking — tag each deployment with template_id.",
                "Increase memory limits for sales-followup-agent and investigate root cause.",
                "Audit all registered agents for approved platform lineage and remediate gaps.",
                "Set Q3 target: 80% of new deployments from approved templates.",
            ],
            "evidence_gaps": [
                "Template reuse rate has no signal source — requires new tag convention in Foundry.",
                "Architecture drift detection requires Agent 365 live connector configuration.",
            ],
            "affected_agents_resources": [
                "sales-followup-agent-6d8c9b-xkzpt (Kubernetes — OOMKilled)",
                "3 agents with undocumented template lineage (Agent 365)",
            ],
            "connectors_used": ["azure", "kubernetes", "foundry", "agent365"],
        },
        "agent_ideas": [
            {
                "id": "cto_idea_01",
                "title": "Template Compliance Enforcer",
                "problem_statement": "No tracking of approved template reuse — architectural drift risk.",
                "proposed_agent_capability": (
                    "Scans new agent deployments and verifies they derive from an approved "
                    "Foundry template. Flags non-compliant deployments for platform review."
                ),
                "required_tools": ["foundry.get_project_health", "agent365.list_agent_registrations"],
                "required_data_sources": ["foundry", "agent365"],
                "expected_value": "Increase template reuse from unmeasured to >80% within Q3.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.HIGH,
                "governance_notes": "Requires deployment pipeline hooks — coordinate with platform team.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.COMPLIANCE],
            },
            {
                "id": "cto_idea_02",
                "title": "Architecture Drift Detector",
                "problem_statement": "2 agents running outside approved platforms — architecture debt accumulating.",
                "proposed_agent_capability": (
                    "Continuously compares registered agent configurations against the approved "
                    "architecture catalogue. Reports drift weekly to CTO."
                ),
                "required_tools": ["agent365.list_agent_registrations", "foundry.get_project_health"],
                "required_data_sources": ["agent365", "foundry"],
                "expected_value": "Reduce architecture drift from 40% to <5% within two quarters.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Read-only audit agent. CTO reviews and signs off on remediation plan.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.RISK],
            },
        ],
    },

    "it_manager": {
        "default_kpi": "Reduce operational incidents caused by agent tool failures.",
        "normalized_kpi": {
            "domain": "IT operations / platform reliability",
            "metric": "agent-caused P1/P2 incident count and mean time to restore",
            "target": "< 2 agent-caused incidents/month, MTTR < 4h",
            "time_horizon": "60 days",
            "scope": "production agents, P1 and P2 incidents",
        },
        "confidence_score": 0.75,
        "required_signal_types": [
            "incidents", "deployment_status", "resource_health",
            "agent_registrations", "ownership_data",
        ],
        "selected_platforms": ["azure", "kubernetes", "microsoft365", "agent365", "servicenow"],
        "digest": {
            "title": "Weekly IT Manager Digest — Agent Operational Health",
            "executive_summary": (
                "2 open P2 incidents, oldest at 38h — above 24h SLA. "
                "SLA compliance at 93% — below 95% target. "
                "1 agent has no assigned owner. "
                "1 OOM pod restart indicates a capacity planning issue."
            ),
            "top_risks": [
                "2 P2 incidents open >24h (ServiceNow)",
                "SLA compliance 93% — 2% below target (ServiceNow)",
                "reporting-agent has no assigned owner (Agent 365)",
                "sales-followup-agent pod OOMKilled ×4 (Kubernetes)",
            ],
            "top_opportunities": [
                "Automated incident triage agent could halve mean response time",
                "Ownership gap detection automated via Agent 365 live integration",
            ],
            "value_signals": ["4,820 agent invocations processed without P1 incident (Foundry)"],
            "cost_signals": [],
            "reporting_signals": [
                "80% agent ownership coverage (Agent 365)",
                "93% SLA compliance (ServiceNow)",
            ],
            "risk_compliance_signals": [
                "2 open P2 incidents >24h (ServiceNow)",
                "1 pod OOMKilled ×4 (Kubernetes)",
            ],
            "recommended_actions": [
                "Escalate and resolve 2 open P2 incidents — oldest is 38h past SLA.",
                "Assign owner to reporting-agent in Agent 365.",
                "Review and increase memory limits for sales-followup-agent.",
                "Set up automated SLA breach alerts for IT on-call rotation.",
                "Configure live ServiceNow connector to replace mock incident data.",
            ],
            "evidence_gaps": [
                "Tool failure root cause not surfaced — requires agent diagnostic logging.",
                "No direct mapping from K8s OOM events to ServiceNow incidents.",
            ],
            "affected_agents_resources": [
                "reporting-agent (Agent 365 — no owner)",
                "sales-followup-agent (Kubernetes — OOM)",
            ],
            "connectors_used": ["azure", "kubernetes", "microsoft365", "agent365", "servicenow"],
        },
        "agent_ideas": [
            {
                "id": "itm_idea_01",
                "title": "Incident Auto-Triage Agent",
                "problem_statement": "P2 incidents require manual triage — average response time >4h.",
                "proposed_agent_capability": "Reads new incidents, classifies them using agent diagnostic signals, assigns to on-call team.",
                "required_tools": ["servicenow.get_open_incidents", "foundry.get_agent_invocations", "kubernetes.get_pod_health"],
                "required_data_sources": ["servicenow", "foundry", "kubernetes"],
                "expected_value": "Reduce mean triage time from 4h to <30 minutes.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Requires ServiceNow ITIL role. Auto-assignment must be reversible.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.RISK],
            },
            {
                "id": "itm_idea_02",
                "title": "Ownership Gap Monitor",
                "problem_statement": "1 agent has no owner — creates accountability gap.",
                "proposed_agent_capability": "Monitors Agent 365 registry for agents without owners and sends weekly reports.",
                "required_tools": ["agent365.get_ownership_coverage"],
                "required_data_sources": ["agent365"],
                "expected_value": "100% ownership coverage within 14 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.LOW,
                "governance_notes": "Read-only agent — no write permissions required.",
                "improves": [ImprovesCategory.COMPLIANCE, ImprovesCategory.EVIDENCE],
            },
            {
                "id": "itm_idea_03",
                "title": "SLA Compliance Early Warning Agent",
                "problem_statement": "SLA compliance at 93% — no proactive warning before breach.",
                "proposed_agent_capability": "Monitors open incidents and predicts SLA breaches 2h in advance.",
                "required_tools": ["servicenow.get_open_incidents", "servicenow.get_sla_compliance"],
                "required_data_sources": ["servicenow"],
                "expected_value": "Reduce SLA breaches by 60% within 30 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Read-only. Alert recipients must be configurable per service tier.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.REPORTING],
            },
        ],
    },

    "security_officer": {
        "default_kpi": "Reduce sensitive data exposure through unmanaged or over-permissioned agents.",
        "normalized_kpi": {
            "domain": "AI security / data governance",
            "metric": "unmanaged PII-access agents and unlabelled external shares",
            "target": "0 unmanaged PII agents, 0 unlabelled external shares",
            "time_horizon": "21 days",
            "scope": "all agents, SharePoint/OneDrive",
        },
        "confidence_score": 0.88,
        "required_signal_types": [
            "security_events", "incidents", "user_activity",
            "compliance_status", "agent_registrations",
        ],
        "selected_platforms": ["azure", "microsoft365", "servicenow"],
        "digest": {
            "title": "Weekly Security Officer Digest — Agent Data Exposure Risk",
            "executive_summary": (
                "Critical: 3 anomalous sign-in events for agent service principals. "
                "15 files shared externally without sensitivity labels. "
                "2 open P2 security incidents. "
                "1 unmanaged agent (no owner)."
            ),
            "top_risks": [
                "3 anomalous sign-in events for agent service principals (Azure) — CRITICAL",
                "15 external file shares without sensitivity labels (M365) — HIGH",
                "2 open P2 security incidents >24h (ServiceNow) — MEDIUM",
                "1 unmanaged agent — no owner (Agent 365) — MEDIUM",
            ],
            "top_opportunities": [
                "Automated token revocation on anomalous sign-in detection",
                "M365 DLP policy enforcement agent eliminates external share violations",
                "Permission audit agent surfaces over-permissioned service principals",
            ],
            "value_signals": [],
            "cost_signals": [],
            "reporting_signals": [
                "3 high-severity security events (Azure)",
                "2 DLP violations — 3 incidents (M365)",
            ],
            "risk_compliance_signals": [
                "3 anomalous sign-in events (Azure) — CRITICAL",
                "15 unlabelled external shares (M365)",
                "2 open P2 incidents (ServiceNow)",
            ],
            "recommended_actions": [
                "Immediately investigate and contain 3 anomalous service principal sign-ins.",
                "Revoke and rotate credentials for sp-foundry-agent and sp-reporting-agent.",
                "Enable mandatory sensitivity labels for all SharePoint external sharing.",
                "Conduct permission audit for all agent service principals in Entra ID.",
                "Escalate 2 open P2 security incidents to resolution.",
            ],
            "evidence_gaps": [
                "No real-time permission scope monitoring — Entra ID connector not configured.",
                "Salesforce and Kubernetes not in scope for this security KPI.",
            ],
            "affected_agents_resources": [
                "sp-foundry-agent (Azure — anomalous sign-in)",
                "sp-reporting-agent (Azure — anomalous sign-in)",
            ],
            "connectors_used": ["azure", "microsoft365", "servicenow"],
        },
        "agent_ideas": [
            {
                "id": "sec_idea_01",
                "title": "Service Principal Anomaly Responder",
                "problem_statement": "3 anomalous sign-ins require manual investigation and containment.",
                "proposed_agent_capability": (
                    "Monitors Entra sign-in logs for anomalous service principal activity, "
                    "revokes tokens with human-in-the-loop approval, opens a ServiceNow P1 incident."
                ),
                "required_tools": ["azure.get_anomalous_signins", "azure.get_security_events", "servicenow.get_open_incidents"],
                "required_data_sources": ["azure", "servicenow"],
                "expected_value": "Reduce containment time from hours to <15 minutes.",
                "risk_level": RiskLevel.HIGH,
                "implementation_complexity": ImplementationComplexity.HIGH,
                "governance_notes": "Token revocation requires Security Officer approval. All actions logged.",
                "improves": [ImprovesCategory.RISK, ImprovesCategory.COMPLIANCE, ImprovesCategory.EVIDENCE],
            },
            {
                "id": "sec_idea_02",
                "title": "Permission Scope Auditor Agent",
                "problem_statement": "Agent service principals may have excessive permissions — no automated audit.",
                "proposed_agent_capability": "Compares configured permissions against minimum required and flags over-permissioned agents.",
                "required_tools": ["agent365.list_agent_registrations", "azure.get_security_events"],
                "required_data_sources": ["agent365", "azure"],
                "expected_value": "Identify and remediate all over-permissioned agents within 30 days.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.HIGH,
                "governance_notes": "Read-only audit — remediation requires Security Officer sign-off.",
                "improves": [ImprovesCategory.RISK, ImprovesCategory.COMPLIANCE],
            },
            {
                "id": "sec_idea_03",
                "title": "DLP Auto-Labelling Agent",
                "problem_statement": "15 files shared externally without sensitivity labels.",
                "proposed_agent_capability": "Scans files shared externally and applies sensitivity labels based on content classification.",
                "required_tools": ["microsoft365.get_external_shares"],
                "required_data_sources": ["microsoft365"],
                "expected_value": "Zero unlabelled external shares within 14 days.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Requires Sites.ReadWrite.All. Labels must align with classification taxonomy.",
                "improves": [ImprovesCategory.COMPLIANCE, ImprovesCategory.RISK],
            },
        ],
    },

    "business_owner": {
        "default_kpi": "Improve case resolution speed without reducing customer satisfaction.",
        "normalized_kpi": {
            "domain": "customer operations / agent value",
            "metric": "case resolution time and CSAT",
            "target": "-25% resolution time, >4.2 CSAT",
            "time_horizon": "30 days",
            "scope": "agent-assisted cases",
        },
        "confidence_score": 0.80,
        "required_signal_types": [
            "opportunity_pipeline", "revenue_impact", "case_resolution", "agent_invocations",
        ],
        "selected_platforms": ["salesforce", "foundry", "azure"],
        "digest": {
            "title": "Weekly Business Owner Digest — Agent Business Value",
            "executive_summary": (
                "Agent-assisted case resolution is 18% faster (3.2h vs 3.9h baseline). "
                "42% of cases use agent assistance. $4.2M pipeline influenced by agents (14%). "
                "Path to 25% resolution improvement requires expanding agent coverage to 65%+ cases."
            ),
            "top_risks": [
                "Agent coverage at 42% — insufficient to reach 25% resolution target without expansion",
                "No CSAT signal configured — cannot confirm customer satisfaction is preserved",
                "Live Salesforce connector not configured — business value data is mock",
            ],
            "top_opportunities": [
                "Expand agent-assisted case coverage from 42% to 65% to reach resolution target",
                "Agent-influenced pipeline at $4.2M — target $5M is achievable",
            ],
            "value_signals": [
                "$4.2M agent-influenced pipeline (14% of total) (Salesforce)",
                "18% faster case resolution with agent assist (Salesforce)",
                "4,820 agent invocations — 42% of cases agent-assisted (Foundry/Salesforce)",
            ],
            "cost_signals": ["Total agent cost $1,240 MTD — $0.26/invocation"],
            "reporting_signals": ["42% agent-assisted case rate (Salesforce)"],
            "risk_compliance_signals": [],
            "recommended_actions": [
                "Expand agent assistance to cover complex case categories currently handled manually.",
                "Integrate Salesforce CSAT data to validate satisfaction is not degraded.",
                "Set up A/B comparison for agent-assisted vs unassisted resolution quality.",
                "Configure live Salesforce connector to replace mock pipeline data.",
            ],
            "evidence_gaps": [
                "CSAT signal absent — no Salesforce Survey/CSAT connector configured.",
                "Agent coverage expansion plan not quantified — requires product team input.",
            ],
            "affected_agents_resources": ["support-resolution-agent (Foundry — 1,980 invocations)"],
            "connectors_used": ["salesforce", "foundry", "azure"],
        },
        "agent_ideas": [
            {
                "id": "biz_idea_01",
                "title": "Case Complexity Classifier",
                "problem_statement": "Agent coverage is 42% — complex cases are not routed to agent assistance.",
                "proposed_agent_capability": "Analyses incoming case content and routes eligible cases to agent assistance.",
                "required_tools": ["salesforce.get_case_resolution", "foundry.get_agent_invocations"],
                "required_data_sources": ["salesforce", "foundry"],
                "expected_value": "Expand agent-assisted coverage from 42% to 65%.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Must preserve customer escalation path. CSAT monitoring required.",
                "improves": [ImprovesCategory.VALUE, ImprovesCategory.OPERATIONS],
            },
            {
                "id": "biz_idea_02",
                "title": "Agent Value Attribution Reporter",
                "problem_statement": "Agent business value is estimated — not directly measured.",
                "proposed_agent_capability": "Joins agent invocation data with Salesforce case outcomes for per-agent value attribution.",
                "required_tools": ["salesforce.get_case_resolution", "salesforce.get_opportunity_pipeline", "foundry.get_agent_invocations"],
                "required_data_sources": ["salesforce", "foundry"],
                "expected_value": "Accurate ROI attribution visible in weekly digest within 14 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Connects to Part 1 (Value Attribution) and Part 2 (Cost Attribution) of this series.",
                "improves": [ImprovesCategory.VALUE, ImprovesCategory.REPORTING],
            },
        ],
    },

    "product_owner": {
        "default_kpi": "Increase adoption of agent-enabled product capabilities.",
        "normalized_kpi": {
            "domain": "product delivery / agent reliability",
            "metric": "sprint delivery variance for agent features",
            "target": "<15% variance (from 35%)",
            "time_horizon": "3 sprints",
            "scope": "agent-enabled features",
        },
        "confidence_score": 0.70,
        "required_signal_types": [
            "agent_invocations", "agent_activity", "change_requests", "deployment_status",
        ],
        "selected_platforms": ["foundry", "agent365", "servicenow"],
        "digest": {
            "title": "Weekly Product Owner Digest — Agent Delivery Predictability",
            "executive_summary": (
                "Agent invocations stable at 4,820/week with 0.3% error rate. "
                "3 pending change requests for agent infrastructure. "
                "1 change request failed in last 30 days. "
                "No direct sprint velocity signal — delivery variance unmeasured."
            ),
            "top_risks": [
                "Sprint delivery variance unmeasured — no tracking signal configured",
                "3 pending infrastructure change requests may delay agent feature releases",
                "1 failed change request last 30 days — root cause unknown",
            ],
            "top_opportunities": [
                "Agent error rate at 0.3% — headroom to increase delivery confidence",
                "Change request tracking integration could surface delivery blockers earlier",
            ],
            "value_signals": ["4,820 agent invocations, 0.3% error rate (Foundry)"],
            "cost_signals": [],
            "reporting_signals": [
                "3 pending change requests (ServiceNow)",
                "1 failed change request in 30 days (ServiceNow)",
            ],
            "risk_compliance_signals": [],
            "recommended_actions": [
                "Define sprint delivery variance metric and connect to reporting pipeline.",
                "Review and unblock 3 pending infrastructure change requests.",
                "Document root cause for the 1 failed change request.",
                "Set agent error rate SLA for feature-bearing agents (e.g. <0.5%).",
            ],
            "evidence_gaps": [
                "Sprint velocity and delivery variance have no signal source in current connectors.",
                "Agent test coverage signal not available — requires test reporting integration.",
            ],
            "affected_agents_resources": [],
            "connectors_used": ["foundry", "agent365", "servicenow"],
        },
        "agent_ideas": [
            {
                "id": "po_idea_01",
                "title": "Sprint Readiness Gate Agent",
                "problem_statement": "No automated check that agent dependencies are ready before sprint starts.",
                "proposed_agent_capability": "Checks agent health, pending change requests, and open incidents before sprint planning.",
                "required_tools": ["foundry.get_project_health", "servicenow.get_change_requests", "servicenow.get_open_incidents"],
                "required_data_sources": ["foundry", "servicenow"],
                "expected_value": "Reduce sprint start blockers by 50%.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.LOW,
                "governance_notes": "Read-only. Sprint gate results must be archived in evidence trail.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.REPORTING],
            },
            {
                "id": "po_idea_02",
                "title": "Change Risk Scorer",
                "problem_statement": "1 failed change in 30 days with no documented root cause.",
                "proposed_agent_capability": "Scores incoming change requests by risk level based on historical failure patterns.",
                "required_tools": ["servicenow.get_change_requests", "foundry.get_agent_invocations"],
                "required_data_sources": ["servicenow", "foundry"],
                "expected_value": "Predict and prevent high-risk change failures.",
                "risk_level": RiskLevel.MEDIUM,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Scoring model must be explainable and logged in evidence.",
                "improves": [ImprovesCategory.RISK, ImprovesCategory.OPERATIONS],
            },
        ],
    },

    "service_owner": {
        "default_kpi": "Reduce support escalations caused by agent misrouting or poor handover.",
        "normalized_kpi": {
            "domain": "service operations / agent quality",
            "metric": "agent-caused escalation rate",
            "target": "<5% (from 12%)",
            "time_horizon": "30 days",
            "scope": "all agent-routed service interactions",
        },
        "confidence_score": 0.73,
        "required_signal_types": [
            "incidents", "sla_compliance", "case_resolution", "agent_invocations",
        ],
        "selected_platforms": ["servicenow", "azure", "kubernetes", "salesforce"],
        "digest": {
            "title": "Weekly Service Owner Digest — Agent Escalation & SLA Compliance",
            "executive_summary": (
                "SLA compliance at 93% — 2% below 95% target. "
                "2 open P2 incidents with oldest at 38h. "
                "Agent-assisted cases resolve 18% faster. "
                "Escalation rate unmeasured — this is the key evidence gap."
            ),
            "top_risks": [
                "SLA compliance at 93% — below 95% target (ServiceNow)",
                "2 P2 incidents open >24h (ServiceNow)",
                "Escalation rate unmeasured — no signal for agent misrouting",
            ],
            "top_opportunities": [
                "Configure escalation tracking signal in Salesforce/ServiceNow",
                "Agent-assisted resolution 18% faster — expand coverage to close SLA gap",
            ],
            "value_signals": ["18% faster case resolution with agent assist (Salesforce)"],
            "cost_signals": [],
            "reporting_signals": [
                "93% SLA compliance (ServiceNow)",
                "2 open P2 incidents (ServiceNow)",
            ],
            "risk_compliance_signals": [],
            "recommended_actions": [
                "Resolve 2 open P2 incidents to restore SLA compliance.",
                "Define and configure escalation rate tracking signal in ServiceNow/Salesforce.",
                "Analyse root cause of SLA misses — are agent handovers contributing?",
                "Set up proactive SLA breach warning 2h before deadline.",
            ],
            "evidence_gaps": [
                "Escalation rate signal absent — configure ServiceNow escalation tracking.",
                "Agent handover quality signal not available — requires conversation log analysis.",
            ],
            "affected_agents_resources": [],
            "connectors_used": ["servicenow", "azure", "kubernetes", "salesforce"],
        },
        "agent_ideas": [
            {
                "id": "svc_idea_01",
                "title": "Escalation Root Cause Analyst",
                "problem_statement": "Agent-caused escalations are not tracked — root causes unknown.",
                "proposed_agent_capability": "Analyses escalated cases to identify routing errors, poor context handover, or capability gaps.",
                "required_tools": ["servicenow.get_open_incidents", "salesforce.get_case_resolution", "foundry.get_agent_invocations"],
                "required_data_sources": ["servicenow", "salesforce", "foundry"],
                "expected_value": "Identify top 3 escalation root causes within 14 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.MEDIUM,
                "governance_notes": "Read-only analysis. Results shared with agent development team.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.REPORTING],
            },
            {
                "id": "svc_idea_02",
                "title": "Proactive SLA Monitor",
                "problem_statement": "SLA compliance at 93% — no early warning before breach.",
                "proposed_agent_capability": "Monitors open cases and predicts SLA breaches 2h in advance.",
                "required_tools": ["servicenow.get_open_incidents", "servicenow.get_sla_compliance"],
                "required_data_sources": ["servicenow"],
                "expected_value": "Restore SLA compliance to >95% within 30 days.",
                "risk_level": RiskLevel.LOW,
                "implementation_complexity": ImplementationComplexity.LOW,
                "governance_notes": "Read-only. Alert routing must be configurable per service tier.",
                "improves": [ImprovesCategory.OPERATIONS, ImprovesCategory.RISK],
            },
        ],
    },
}


class KPIAgent:
    """Persona-aware KPI Agent.

    Interprets a KPI, maps it to required signals via the ToolRegistry,
    gathers those signals, and produces a complete control plane response.

    Usage::

        registry = ToolRegistry()
        for cls in ALL_CONNECTORS:
            registry.register(cls())

        agent = KPIAgent(registry)
        result = agent.run(persona_id="compliance_officer")
        result = agent.run(persona_id="cfo", kpi="Lower costs.")

    Phase 2 upgrade path:
        Replace the _SCENARIOS lookup in run() with an LLM call.
        Everything else (ToolRegistry, evidence trail, stores) stays the same.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        persona_id: str,
        kpi: Optional[str] = None,
        mode: str = "mock",
    ) -> Dict[str, Any]:
        """Run the KPI Agent for a persona and return a full control plane response.

        Returns a dict with:
        - persona, original_kpi, normalized_kpi
        - maturity_level: "vague" | "usable" | "well_articulated"
        - confidence_score
        - clarification_questions (non-empty only when maturity == "vague")
        - required_signals, selected_platforms, available_tools_used
        - weekly_digest
        - control_insights, recommended_actions
        - agent_ideas
        - evidence_events
        - source_mode_summary
        """
        persona = PERSONA_CATALOGUE.get(persona_id)
        if persona is None:
            return {
                "error": f"Unknown persona_id '{persona_id}'.",
                "available": list(PERSONA_CATALOGUE.keys()),
            }

        scenario = _SCENARIOS.get(persona_id, {})
        kpi_text = kpi or scenario.get("default_kpi", "")
        maturity = _classify_maturity(kpi_text)

        run_id = str(uuid.uuid4())[:8]
        events: List[Dict[str, Any]] = []

        # -- Event 1: KPI interpreted
        normalized_kpi = scenario.get("normalized_kpi", {"title": kpi_text})
        events.append(self._evt("kpi_interpreted", persona_id, None, {
            "persona_id": persona_id,
            "original_kpi": kpi_text,
            "maturity_level": maturity,
            "normalized_kpi": normalized_kpi,
        }))
        evidence_store.add_event(
            "kpi_interpreted",
            {"persona_id": persona_id, "kpi": kpi_text, "maturity": maturity},
            persona_id=persona_id,
            source_mode=mode,
        )

        # Clarification questions for vague KPIs
        clarification_questions: List[str] = []
        if maturity == "vague":
            clarification_questions = (
                _VAGUE_KPI_PATTERNS.get(persona_id) or _DEFAULT_CLARIFICATION_QUESTIONS
            )

        # -- Event 2: signal requirements selected
        required_signals = scenario.get("required_signal_types", ["resource_health"])
        selected_platforms = scenario.get("selected_platforms", [])
        events.append(self._evt("signals_selected", persona_id, None, {
            "required_signal_types": required_signals,
            "selected_platforms": selected_platforms,
        }))
        evidence_store.add_event(
            "signals_selected",
            {"signal_types": required_signals, "platforms": selected_platforms},
            persona_id=persona_id,
            source_mode=mode,
        )

        # -- Event 3: tools discovered
        available_tools = self._registry.tools_for_signal_types(required_signals)
        tools_summary = [
            {"id": t.id, "platform": t.platform_id, "source_mode": t.source_mode.value}
            for t in available_tools
        ]
        events.append(self._evt("tools_discovered", persona_id, None, {
            "available_tools": tools_summary,
            "total": len(tools_summary),
        }))
        evidence_store.add_event(
            "tools_discovered", {"count": len(tools_summary)},
            persona_id=persona_id, source_mode=mode,
        )

        # -- Event 4: signals gathered via ToolRegistry
        raw_signals = self._registry.gather_signals(
            required_signals,
            context={"persona_id": persona_id, "run_id": run_id, "mode": mode},
        )
        signals = [Signal.from_dict(s) for s in raw_signals]
        tools_used = list({s.platform_id for s in signals})
        events.append(self._evt("tools_used", persona_id, None, {
            "tools_used": tools_used,
            "signals_gathered": len(signals),
        }))
        evidence_store.add_event(
            "tools_used",
            {"platforms": tools_used, "signal_count": len(signals)},
            persona_id=persona_id,
            source_mode=mode,
        )

        # -- Digest from scenario catalogue
        digest_data = dict(scenario.get("digest", {}))
        confidence_score = scenario.get("confidence_score", 0.70)
        events.append(self._evt("insights_generated", persona_id, None, {
            "digest_sections": list(digest_data.keys()),
            "confidence_score": confidence_score,
        }))
        evidence_store.add_event(
            "insights_generated", {"confidence": confidence_score},
            persona_id=persona_id, source_mode=mode,
        )

        # -- Assemble weekly digest
        weekly_digest = {
            "title": digest_data.get("title", "Weekly Digest"),
            "executive_summary": digest_data.get("executive_summary", ""),
            "top_risks": digest_data.get("top_risks", []),
            "top_opportunities": digest_data.get("top_opportunities", []),
            "recommended_actions": digest_data.get("recommended_actions", []),
            "evidence_gaps": digest_data.get("evidence_gaps", []),
            "affected_agents_resources": digest_data.get("affected_agents_resources", []),
            "value_signals": digest_data.get("value_signals", []),
            "cost_signals": digest_data.get("cost_signals", []),
            "reporting_signals": digest_data.get("reporting_signals", []),
            "risk_compliance_signals": digest_data.get("risk_compliance_signals", []),
            "confidence_level": confidence_score,
            "data_source_mode": mode,
            "connectors_used": digest_data.get("connectors_used", []),
        }
        evidence_store.add_event(
            "weekly_digest_generated",
            {"title": weekly_digest["title"], "confidence": confidence_score},
            persona_id=persona_id,
            source_mode=mode,
        )

        # -- Agent ideas
        raw_ideas = scenario.get("agent_ideas", [])
        agent_ideas_out: List[Dict[str, Any]] = []
        for raw in raw_ideas:
            idea = AgentIdea(
                id=raw["id"],
                title=raw["title"],
                persona_id=persona_id,
                related_kpi_id=(
                    persona.default_kpis[0].kpi_id if persona.default_kpis else "custom_01"
                ),
                problem_statement=raw["problem_statement"],
                proposed_agent_capability=raw["proposed_agent_capability"],
                required_tools=raw.get("required_tools", []),
                required_data_sources=raw.get("required_data_sources", []),
                expected_value=raw.get("expected_value", ""),
                risk_level=raw.get("risk_level", RiskLevel.MEDIUM),
                implementation_complexity=raw.get(
                    "implementation_complexity", ImplementationComplexity.MEDIUM
                ),
                governance_notes=raw.get("governance_notes", ""),
                improves=raw.get("improves", []),
            )
            agent_ideas_out.append(idea.to_dict())

        if agent_ideas_out:
            events.append(self._evt("agent_ideas_generated", persona_id, None, {
                "count": len(agent_ideas_out),
                "idea_ids": [i["id"] for i in agent_ideas_out],
            }))
            evidence_store.add_event(
                "agent_ideas_generated",
                {"count": len(agent_ideas_out)},
                persona_id=persona_id,
                source_mode=mode,
            )

        # Access Readiness — checks whether the persona has access to
        # the data/tools needed for this KPI.  No access is granted here.
        access_agent = AccessReadinessAgent(self._registry)
        kpi_partial = {
            "required_signals": required_signals,
            "selected_platforms": selected_platforms,
            "available_tools_used": tools_summary,
            "normalized_kpi": normalized_kpi,
        }
        access_result = access_agent.check(
            persona_id=persona_id,
            kpi_agent_result=kpi_partial,
            mode=mode,
        )
        access_summary = {
            "overall_status": access_result["overall_status"],
            "checked_signals": len(access_result["access_check_results"]),
            "access_gaps_count": len(access_result["access_gaps"]),
            "recommended_requests_count": len(access_result["recommended_access_requests"]),
        }

        return {
            "persona": {"id": persona_id, "name": persona.name},
            "original_kpi": kpi_text,
            "normalized_kpi": normalized_kpi,
            "maturity_level": maturity,
            "confidence_score": confidence_score,
            "clarification_questions": clarification_questions,
            "required_signals": required_signals,
            "selected_platforms": selected_platforms,
            "available_tools_used": tools_summary,
            "weekly_digest": weekly_digest,
            "control_insights": [
                {
                    "insight": digest_data.get("executive_summary", ""),
                    "type": "executive_summary",
                    "source_mode": mode,
                }
            ],
            "recommended_actions": digest_data.get("recommended_actions", []),
            "agent_ideas": agent_ideas_out,
            "evidence_events": events,
            "source_mode_summary": self._source_mode_summary(signals),
            # Access readiness summary
            "access_readiness_summary": access_summary,
            "access_check_results": access_result["access_check_results"],
            "access_gaps": access_result["access_gaps"],
            "recommended_access_requests": access_result["recommended_access_requests"],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _evt(
        event_type: str,
        persona_id: Optional[str],
        kpi_id: Optional[str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "event_type": event_type,
            "persona_id": persona_id,
            "kpi_id": kpi_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

    @staticmethod
    def _source_mode_summary(signals: List[Signal]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for s in signals:
            counts[s.source_metadata.source_mode] = (
                counts.get(s.source_metadata.source_mode, 0) + 1
            )
        return counts
