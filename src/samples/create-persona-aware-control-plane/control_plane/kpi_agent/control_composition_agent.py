"""Control Composition Agent — composes a Control Package from a FormalizedKpi.

Responsibilities:
1. Accept a FormalizedKpi.
2. Use the existing KPI Agent to map the KPI to required signals.
3. Use ToolRegistry to identify required connector tools.
4. Use Access Readiness Agent to determine access gaps.
5. Compose "what you get" — the control-plane outputs the persona will receive.
6. Compose "what you need" — the signals, connectors, tools, access and evidence required.
7. Generate recommended actions and agent ideas.
8. Write evidence events: control_package_composed, required_signals_identified,
   required_access_identified, control_outputs_defined.

Design rules:
- Never duplicates logic already in KPIAgent or AccessReadinessAgent.
- Orchestrates those agents; does NOT re-implement their logic.
- Deterministic in mock mode — no LLM dependency.
- The ControlPackage is only valid after KPI formalization.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from control_plane.access_readiness import AccessReadinessAgent
from control_plane.connectors.registry import ToolRegistry
from control_plane.kpi_agent.agent import KPIAgent
from control_plane.models.kpi_refinement import ControlPackage
from control_plane.models.provenance import SignalExecution, SourceSummary
from control_plane.stores import evidence_store


# ---------------------------------------------------------------------------
# Persona-specific "what you get" templates
# ---------------------------------------------------------------------------

_WHAT_YOU_GET: Dict[str, List[str]] = {
    "cfo": [
        "Agent ROI control briefing (weekly)",
        "Cost-to-value summary per funded initiative",
        "Value confidence score with evidence quality indicator",
        "Investment risk indicators (unallocated spend, ROI shortfall)",
        "Recommended scale / stop / investigate actions",
        "Agent ideas to improve cost attribution and value traceability",
        "Access request recommendations for missing financial signals",
        "Evidence trail of all investment decisions and KPI assessments",
    ],
    "compliance_officer": [
        "Audit readiness briefing (weekly)",
        "Evidence trail coverage score per agent",
        "Open compliance findings with age and priority",
        "Policy exception tracking with escalation recommendations",
        "Regulatory gap analysis against active control domains",
        "Agent ideas to automate evidence collection",
        "Access request recommendations for audit trail connectors",
        "Immutable evidence trail of all compliance assessments",
    ],
    "cto": [
        "Platform governance briefing (weekly)",
        "Architecture pattern reuse rate by business unit",
        "Architecture drift alerts for non-compliant deployments",
        "Strategic technology debt summary",
        "Platform health indicators across Foundry, Kubernetes and Azure",
        "Agent ideas to enforce template compliance and detect drift",
        "Recommended actions for platform remediation",
        "Evidence trail of all architecture assessments",
    ],
    "it_manager": [
        "Operational control briefing (weekly)",
        "Incident volume and MTTR by agent and connector",
        "Connector health and availability status",
        "Deployment stability summary",
        "Capacity and resource utilisation indicators",
        "Agent ideas to automate incident response",
        "Recommended actions for platform reliability",
        "Evidence trail of all operational incidents",
    ],
    "security_officer": [
        "Security control briefing (weekly)",
        "Data access risk summary by agent and sensitivity level",
        "Privileged access drift indicators",
        "Unmanaged or over-permissioned agent alerts",
        "Access anomaly detection results",
        "Agent ideas to enforce least-privilege access and detect anomalies",
        "Recommended access remediation actions",
        "Evidence trail of all security assessments and access events",
    ],
    "business_owner": [
        "Business outcome control briefing (weekly)",
        "Agent-attributed value signal by process and journey",
        "Outcome confidence score with attribution quality",
        "Operational risk indicators affecting business outcomes",
        "Agent ideas to improve value measurement and process coverage",
        "Recommended actions to increase agent-attributed value",
        "Evidence trail of all value attribution assessments",
    ],
    "product_owner": [
        "Product governance briefing (weekly)",
        "Feature adoption and delivery predictability metrics",
        "Agent-enabled capability quality and usage indicators",
        "Roadmap impact assessment for agent-enabled features",
        "Agent ideas to improve adoption tracking and delivery quality",
        "Recommended actions for feature and agent improvements",
        "Evidence trail of all product delivery assessments",
    ],
    "service_owner": [
        "Service control briefing (weekly)",
        "SLA attainment and escalation summary",
        "Handover quality and resolution completeness indicators",
        "Repeat incident and root cause summary",
        "Agent ideas to automate service routing and resolution",
        "Recommended actions for SLA recovery and service quality",
        "Evidence trail of all service assessments",
    ],
}

_DEFAULT_WHAT_YOU_GET = [
    "Weekly control briefing",
    "KPI trend and confidence score",
    "Signal summary (value, cost, risk)",
    "Top risks and evidence gaps",
    "Recommended actions",
    "Agent ideas",
    "Evidence trail",
]

# ---------------------------------------------------------------------------
# Persona-specific "what you need" templates
# ---------------------------------------------------------------------------

_WHAT_YOU_NEED: Dict[str, List[str]] = {
    "cfo": [
        "Azure Cost Management data (cost per resource, per agent)",
        "Foundry model and agent usage data (invocations, model consumption)",
        "Salesforce opportunity and case impact data (revenue attribution)",
        "Agent 365 lifecycle and ownership data",
        "Cost Management Reader role on Azure subscription",
        "Foundry Project Read access",
        "Salesforce Read access to Opportunity and Case objects",
        "Evidence-backed value attribution events per agent invocation",
    ],
    "compliance_officer": [
        "Agent 365 agent registration and ownership data",
        "Foundry agent invocation and evaluation records",
        "Azure security events and anomalous sign-in data",
        "Microsoft 365 sharing and DLP events",
        "ServiceNow incident and policy exception records",
        "Agent Registry Viewer role in Agent 365",
        "Security Reader role in Azure",
        "ITSM Viewer role in ServiceNow",
        "Evidence events for every high-risk agent invocation",
    ],
    "cto": [
        "Agent 365 agent registration and template lineage data",
        "Foundry project health and deployment data",
        "Azure resource health and subscription data",
        "Kubernetes pod and deployment health data",
        "AI Platform Architect read access in Foundry",
        "Cluster Viewer role in Kubernetes",
        "Reader role in Azure",
        "Agent Registry Viewer in Agent 365",
        "Template lineage tags on all agent deployments",
    ],
    "it_manager": [
        "Azure resource health and infrastructure data",
        "Kubernetes deployment and pod health data",
        "ServiceNow incident, change and SLA records",
        "Agent 365 agent operational status data",
        "Foundry agent invocation error and latency data",
        "Platform Operations role in Kubernetes",
        "ITSM Operations role in ServiceNow",
        "Reader role in Azure",
    ],
    "security_officer": [
        "Azure security events and anomalous sign-in data",
        "Microsoft 365 DLP and sensitivity label events",
        "Agent 365 agent access scope and permission data",
        "Foundry agent invocation data with access context",
        "Security Reader role in Azure",
        "Compliance Reader role in Microsoft 365",
        "Agent Registry Viewer in Agent 365",
        "Access scope and sensitivity classification tags on all agents",
    ],
    "business_owner": [
        "Salesforce opportunity and case outcome data",
        "ServiceNow business impact and resolution data",
        "Foundry agent invocation data correlated to business outcomes",
        "Agent 365 agent ownership and outcome linkage data",
        "Sales Analyst read access in Salesforce",
        "ITSM Viewer role in ServiceNow",
        "Foundry Project Read access",
        "Outcome attribution tags on agent-assisted transactions",
    ],
    "product_owner": [
        "Foundry agent invocation and evaluation data",
        "Agent 365 feature adoption and usage data",
        "Azure deployment and release data",
        "Product telemetry for agent-enabled features",
        "Foundry Project Read access",
        "Agent Registry Viewer in Agent 365",
        "Reader role in Azure",
        "Feature adoption instrumentation in product",
    ],
    "service_owner": [
        "ServiceNow incident, escalation and SLA data",
        "Agent 365 agent service assignment and handover data",
        "Foundry agent invocation data for service workflows",
        "Microsoft 365 service communication and routing data",
        "ITSM Viewer role in ServiceNow",
        "Agent Registry Viewer in Agent 365",
        "Foundry Project Read access",
        "SLA and escalation tags on agent-assisted service cases",
    ],
}

_DEFAULT_WHAT_YOU_NEED = [
    "Required signal connector access",
    "Required connector tools from ToolRegistry",
    "Required scopes and roles per platform",
    "Evidence sources for KPI validation",
]

# ---------------------------------------------------------------------------
# Persona-specific recommended actions
# ---------------------------------------------------------------------------

_RECOMMENDED_ACTIONS: Dict[str, List[Dict[str, Any]]] = {
    "cfo": [
        {
            "action": "Request Salesforce Read access for opportunity pipeline signal",
            "why": "ROI cannot be evidence-backed without agent-attributed revenue data",
            "impact": "Enables evidence-grade ROI calculation",
            "approver": "Salesforce Admin / CISO",
            "risk": "Low — read-only access to opportunity and case data",
            "evidence_created": "access_request_submitted",
        },
        {
            "action": "Implement cost attribution tags on all Azure agent resources",
            "why": "Unallocated spend reduces ROI confidence below threshold",
            "impact": "Closes the largest gap in cost-to-value attribution",
            "approver": "Cloud Platform Team",
            "risk": "Low — tagging only; no code changes",
            "evidence_created": "cost_tag_coverage_improved",
        },
        {
            "action": "Request Per-Agent ROI Tracker agent from Agent Ideas",
            "why": "Aggregate ROI is estimated; per-agent attribution requires automation",
            "impact": "Per-agent ROI visible in weekly CFO digest within 30 days",
            "approver": "CTO",
            "risk": "Medium — requires pipeline hooks and data joins",
            "evidence_created": "agent_request_submitted",
        },
    ],
    "compliance_officer": [
        {
            "action": "Assign ownership to all unowned agents in Agent 365",
            "why": "Agents without owners cannot be audited or remediated",
            "impact": "Closes ownership gap immediately; zero agent management cost",
            "approver": "AI Governance Lead",
            "risk": "Low",
            "evidence_created": "agent_ownership_assigned",
        },
        {
            "action": "Enable mandatory sensitivity labels on SharePoint/OneDrive agent outputs",
            "why": "Unclassified external shares represent an active DLP compliance risk",
            "impact": "Eliminates external share violations within 14 days",
            "approver": "Microsoft 365 Admin",
            "risk": "Low — enforces existing policy",
            "evidence_created": "dlp_policy_enforced",
        },
        {
            "action": "Configure live Agent 365 connector for real-time ownership gap detection",
            "why": "Mock connector cannot detect new ownership gaps as they arise",
            "impact": "Real-time visibility into all ownership and compliance gaps",
            "approver": "Platform Engineering",
            "risk": "Low — read-only API connection",
            "evidence_created": "connector_configured",
        },
    ],
    "cto": [
        {
            "action": "Define and publish approved Foundry agent templates in the platform catalog",
            "why": "No approved templates means reuse cannot be enforced or measured",
            "impact": "Enables template compliance tracking from next sprint",
            "approver": "CTO / Platform Lead",
            "risk": "Low — documentation and catalog update",
            "evidence_created": "template_catalog_published",
        },
        {
            "action": "Investigate and remediate OOMKilled pod in sales-followup-agent",
            "why": "Repeated OOM kills indicate a memory leak that may cascade",
            "impact": "Eliminates platform instability risk for the highest-traffic agent",
            "approver": "Platform Operations",
            "risk": "Medium — requires code investigation",
            "evidence_created": "incident_resolved",
        },
    ],
    "it_manager": [
        {
            "action": "Configure ServiceNow connector for live incident signal",
            "why": "Mock incident data cannot detect new platform failures in real time",
            "impact": "Real-time operational alerting for agent-caused incidents",
            "approver": "ServiceNow Admin",
            "risk": "Low — read-only ITSM connection",
            "evidence_created": "connector_configured",
        },
        {
            "action": "Request incident automation agent from Agent Ideas",
            "why": "Agent-caused incidents are currently handled manually",
            "impact": "Reduces MTTR from hours to minutes for connector failures",
            "approver": "IT Director",
            "risk": "Medium — automated remediation requires human-in-the-loop approval",
            "evidence_created": "agent_request_submitted",
        },
    ],
    "security_officer": [
        {
            "action": "Investigate and close anomalous sign-in events for agent service principals",
            "why": "3 unresolved anomalous sign-ins represent an active credential risk",
            "impact": "Eliminates uncontrolled access risk for compromised service principals",
            "approver": "CISO",
            "risk": "High — token revocation may impact agent availability",
            "evidence_created": "security_incident_resolved",
        },
        {
            "action": "Enforce least-privilege access review for all production agents",
            "why": "Over-permissioned agents create data exposure risk",
            "impact": "Reduces blast radius of any future compromise",
            "approver": "CISO / IAM Team",
            "risk": "Medium — reducing permissions may require agent reconfiguration",
            "evidence_created": "access_review_completed",
        },
    ],
}

_DEFAULT_RECOMMENDED_ACTIONS: List[Dict[str, Any]] = [
    {
        "action": "Request missing connector access",
        "why": "Control plane cannot gather required signals without connector access",
        "impact": "Enables full KPI signal coverage",
        "approver": "Platform Admin",
        "risk": "Low",
        "evidence_created": "access_request_submitted",
    },
    {
        "action": "Configure required connectors",
        "why": "Connectors in mock mode cannot detect live changes",
        "impact": "Real-time governance signals",
        "approver": "Platform Engineering",
        "risk": "Low",
        "evidence_created": "connector_configured",
    },
]


# ---------------------------------------------------------------------------
# Control Composition Agent
# ---------------------------------------------------------------------------


class ControlCompositionAgent:
    """Composes a ControlPackage from a FormalizedKpi.

    Orchestrates KPIAgent, ToolRegistry and AccessReadinessAgent.
    Does NOT duplicate their internal logic.
    """

    def __init__(
        self,
        kpi_agent: KPIAgent,
        tool_registry: ToolRegistry,
        access_agent: AccessReadinessAgent,
    ) -> None:
        self._kpi_agent = kpi_agent
        self._registry = tool_registry
        self._access_agent = access_agent

    def compose(
        self,
        persona_id: str,
        formalized_kpi: Dict[str, Any],
        mode: str = "mock",
    ) -> Dict[str, Any]:
        """Compose a ControlPackage for the given persona and formalized KPI.

        Evidence events written:
          required_signals_identified, required_access_identified,
          control_outputs_defined, control_package_composed.
        """
        package_id = str(uuid.uuid4())

        # --- Step 1: Run KPI Agent to get signal/tool/platform mapping ---
        kpi_title = formalized_kpi.get("title", "")
        kpi_result = self._kpi_agent.run(
            persona_id=persona_id,
            kpi=kpi_title,
            mode=mode,
        )

        required_signals: List[str] = kpi_result.get("required_signals", [])
        selected_platforms: List[str] = kpi_result.get("selected_platforms", [])
        tools_used: List[str] = [
            t.get("id", "") for t in kpi_result.get("available_tools_used", [])
        ]

        evidence_store.add_event(
            "required_signals_identified",
            {
                "package_id": package_id,
                "persona_id": persona_id,
                "required_signals": required_signals,
                "selected_platforms": selected_platforms,
            },
            persona_id=persona_id,
            source_mode=mode,
        )

        # --- Step 2: Identify connector tools from ToolRegistry ---
        available_tools = self._registry.tools_for_signal_types(required_signals)
        required_connectors = list({t.platform_id for t in available_tools})
        required_tool_ids = [t.id for t in available_tools]

        # --- Step 2.5: Execute live signals from connectors (provenance) ---
        signal_executions: List[SignalExecution] = []
        context: Dict[str, Any] = {
            "persona_id": persona_id,
            "mode": mode,
            "kpi_title": kpi_title,
        }
        for platform in selected_platforms:
            connector = self._registry.get_connector(platform)
            if connector is None:
                continue
            try:
                raw_signals = connector.get_signals(required_signals, context)
            except Exception as exc:
                raw_signals = []
                evidence_store.add_event(
                    "connector_signal_error",
                    {"platform": platform, "error": str(exc)[:200]},
                    persona_id=persona_id,
                    source_mode=mode,
                )
            for sig_dict in raw_signals:
                exec_data = sig_dict.get("signal_execution")
                if exec_data and isinstance(exec_data, dict):
                    exec_obj = SignalExecution(
                        signal_name=exec_data.get("signal_name", sig_dict.get("signal_type", "unknown")),
                        platform_id=exec_data.get("platform_id", platform),
                        tool_name=exec_data.get("tool_name", ""),
                        source_mode=exec_data.get("source_mode", "mock"),
                        retrieved_at=exec_data.get("retrieved_at", ""),
                        confidence=exec_data.get("confidence", 0.5),
                        query_summary=exec_data.get("query_summary"),
                        endpoint=exec_data.get("endpoint"),
                        identity_summary=exec_data.get("identity_summary"),
                        raw_preview=exec_data.get("raw_preview"),
                        error=exec_data.get("error"),
                        evidence_ref=exec_data.get("evidence_ref"),
                        used_in_composition=True,  # signals returned are used
                    )
                    signal_executions.append(exec_obj)
                    evidence_store.add_event(
                        "live_signal_retrieved" if exec_obj.source_mode == "live"
                        else "mock_signal_used",
                        {
                            "signal_name": exec_obj.signal_name,
                            "platform_id": exec_obj.platform_id,
                            "tool_name": exec_obj.tool_name,
                            "source_mode": exec_obj.source_mode,
                            "confidence": exec_obj.confidence,
                        },
                        persona_id=persona_id,
                        source_mode=exec_obj.source_mode,
                    )

        source_summary = SourceSummary.from_executions(signal_executions)

        # --- Step 3: Run Access Readiness Agent ---
        access_result = self._access_agent.check(
            persona_id=persona_id,
            kpi_agent_result=kpi_result,
            mode=mode,
        )

        evidence_store.add_event(
            "required_access_identified",
            {
                "package_id": package_id,
                "persona_id": persona_id,
                "overall_access_status": access_result.get("overall_status"),
                "gap_count": len(access_result.get("access_gaps", [])),
            },
            persona_id=persona_id,
            source_mode=mode,
        )

        # Extract access requirements from access result
        required_access = [
            {
                "platform": gap.get("platform_id", ""),
                "scope": gap.get("required_scope", ""),
                "role": gap.get("required_role", ""),
                "status": gap.get("status", "missing"),
            }
            for gap in access_result.get("access_gaps", [])
        ]

        # --- Step 4: Build "what you get" and "what you need" ---
        what_you_get = _WHAT_YOU_GET.get(persona_id, _DEFAULT_WHAT_YOU_GET)
        what_you_need = _WHAT_YOU_NEED.get(persona_id, _DEFAULT_WHAT_YOU_NEED)

        # Required evidence from the KPI definition
        required_evidence = [
            f"Evidence events for {sig} signal from {plat}"
            for sig, plat in zip(required_signals[:4], selected_platforms[:4])
        ] + [formalized_kpi.get("evidence_standard", "Evidence events per KPI action")]

        evidence_store.add_event(
            "control_outputs_defined",
            {
                "package_id": package_id,
                "what_you_get_count": len(what_you_get),
                "what_you_need_count": len(what_you_need),
            },
            persona_id=persona_id,
            source_mode=mode,
        )

        # --- Step 5: Build recommended actions ---
        recommended_actions = _RECOMMENDED_ACTIONS.get(
            persona_id, _DEFAULT_RECOMMENDED_ACTIONS
        )

        # --- Step 6: Extract agent ideas from KPI Agent result ---
        raw_ideas = kpi_result.get("agent_ideas", [])
        agent_ideas = [
            {
                "id": idea.get("id", ""),
                "title": idea.get("title", ""),
                "problem_statement": idea.get("problem_statement", ""),
                "expected_value": idea.get("expected_value", ""),
                "risk_level": idea.get("risk_level", "low"),
                "implementation_complexity": idea.get("implementation_complexity", "medium"),
            }
            for idea in raw_ideas
        ]

        # --- Step 7: Access readiness summary ---
        access_readiness_summary = {
            "overall_status": access_result.get("overall_status", "unknown"),
            "ready_connectors": [
                r["connector_id"]
                for r in access_result.get("access_check_results", [])
                if r.get("status") == "has_access"
            ],
            "missing_connectors": [
                r["connector_id"]
                for r in access_result.get("access_check_results", [])
                if r.get("status") == "missing_access"
            ],
            "gap_count": len(access_result.get("access_gaps", [])),
        }

        # --- Step 8: Connector readiness summary ---
        connector_readiness_summary = {
            platform: {
                "available": any(t.platform_id == platform for t in available_tools),
                "tool_count": sum(1 for t in available_tools if t.platform_id == platform),
            }
            for platform in selected_platforms
        }

        # --- Step 9: Limitations ---
        limitations = kpi_result.get("weekly_digest", {}).get("evidence_gaps", [])

        confidence = min(
            0.95,
            formalized_kpi.get("confidence_score", 0.7) * 0.9
            + (0.1 if access_result.get("overall_status") == "ready" else 0.0),
        )

        evidence_events = [
            "required_signals_identified",
            "required_access_identified",
            "control_outputs_defined",
            "control_package_composed",
        ]

        package = ControlPackage(
            id=package_id,
            formalized_kpi_id=formalized_kpi.get("id", ""),
            persona_id=persona_id,
            what_you_get=what_you_get,
            what_you_need=what_you_need,
            required_signals=required_signals,
            required_connectors=required_connectors,
            required_tools=required_tool_ids,
            required_access=required_access,
            required_evidence=required_evidence,
            access_readiness_summary=access_readiness_summary,
            connector_readiness_summary=connector_readiness_summary,
            recommended_actions=recommended_actions,
            agent_ideas=agent_ideas,
            evidence_events=evidence_events,
            limitations=limitations,
            confidence_score=round(confidence, 2),
            signal_provenance=[e.to_dict() for e in signal_executions],
            source_summary=source_summary.to_dict(),
        )

        evidence_store.add_event(
            "control_package_composed",
            {
                "package_id": package_id,
                "persona_id": persona_id,
                "confidence_score": package.confidence_score,
                "required_connector_count": len(required_connectors),
                "required_tool_count": len(required_tool_ids),
            },
            persona_id=persona_id,
            source_mode=mode,
        )

        return {"control_package": package.to_dict()}
