"""Persona and KPI models for the control plane.

Each persona represents a human role that consumes the weekly digest.
Personas have default KPIs, but users can add or adjust KPIs in natural
language — the KPI Agent then interprets and maps them to required signals.

Personas defined here are data-only.  The KPI Agent handles interpretation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# KPI model
# ---------------------------------------------------------------------------


@dataclass
class KPI:
    """A single Key Performance Indicator belonging to a persona.

    ``signal_types`` lists the signal types the KPI Agent should gather
    to evaluate this KPI.  This is pre-mapped for default KPIs; for
    user-entered KPIs the KPI Agent determines the mapping at runtime.

    ``kpi_id`` is a stable identifier used in evidence trail events.
    """

    kpi_id: str
    title: str
    description: str
    signal_types: List[str]
    # Quantified target, e.g. "< 0 unauthorized access events per quarter"
    target: Optional[str] = None
    # Free-text notes from the persona or KPI Agent clarification
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Persona model
# ---------------------------------------------------------------------------


@dataclass
class Persona:
    """A human role that interacts with the control plane.

    ``default_kpis`` are pre-configured; users can supplement or override
    them in natural language via the KPI Agent.

    ``relevant_platforms`` narrows which connectors the KPI Agent should
    prioritise when gathering signals for this persona.
    """

    persona_id: str
    name: str
    description: str
    default_kpis: List[KPI] = field(default_factory=list)
    relevant_platforms: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Default persona catalogue
# ---------------------------------------------------------------------------

PERSONA_CATALOGUE: Dict[str, Persona] = {
    "compliance_officer": Persona(
        persona_id="compliance_officer",
        name="Compliance Officer",
        description=(
            "Accountable for evidence, controls, policy adherence and audit readiness "
            "of AI agents and their data access."
        ),
        relevant_platforms=["azure", "microsoft365", "agent365", "a365", "servicenow"],
        default_kpis=[
            KPI(
                kpi_id="comp_01",
                title="Improve audit readiness for high-risk AI agents",
                description="Increase evidence trail coverage for agents with access to regulated data.",
                target="100% evidence coverage, 0 open P1 audit findings",
                signal_types=["agent_invocations", "agent_registrations", "compliance_status"],
            ),
            KPI(
                kpi_id="comp_02",
                title="Increase evidence coverage for regulated agentic workflows",
                description="Every agent invocation in a regulated workflow must produce an immutable evidence event.",
                target="100% coverage for regulated workflows",
                signal_types=["agent_invocations", "agent_registrations", "security_events"],
            ),
            KPI(
                kpi_id="comp_03",
                title="Reduce open policy exceptions older than 30 days",
                description="Policy exceptions that are open beyond 30 days represent unmitigated compliance risk.",
                target="0 exceptions open >30 days",
                signal_types=["compliance_status", "incidents", "user_activity"],
            ),
            KPI(
                kpi_id="comp_04",
                title="Ensure high-risk agents have documented human oversight",
                description="All agents classified as high-risk must have a documented human-in-the-loop control.",
                target="100% high-risk agents with oversight documentation",
                signal_types=["agent_registrations", "ownership_data", "compliance_status"],
            ),
        ],
    ),
    "cfo": Persona(
        persona_id="cfo",
        name="CFO",
        description=(
            "Accountable for financial control, value realization, budget discipline "
            "and investment confidence across AI and cloud initiatives."
        ),
        relevant_platforms=["azure", "foundry", "salesforce"],
        default_kpis=[
            KPI(
                kpi_id="cfo_01",
                title="Maintain agent ROI above 3x across funded AI initiatives",
                description="Revenue or cost-saving attributed to agents must exceed 3x the total cost of those agents.",
                target="> 3.0 ROI",
                signal_types=["cost_data", "revenue_impact", "agent_invocations"],
            ),
            KPI(
                kpi_id="cfo_02",
                title="Reduce unallocated AI and cloud spend below 10%",
                description="Less than 10% of AI and cloud spend should lack a business-outcome cost attribution tag.",
                target="< 10% unallocated spend",
                signal_types=["cost_data", "model_usage"],
            ),
            KPI(
                kpi_id="cfo_03",
                title="Increase percentage of AI spend linked to measurable business outcomes",
                description="Every funded AI initiative must link its spend to a tracked business outcome.",
                target="> 80% of AI spend outcome-linked",
                signal_types=["cost_data", "revenue_impact", "opportunity_pipeline"],
            ),
            KPI(
                kpi_id="cfo_04",
                title="Improve forecast accuracy for model and platform consumption",
                description="Monthly variance between AI cost forecast and actual spend should be within 10%.",
                target="< 10% forecast variance",
                signal_types=["cost_data", "model_usage"],
            ),
        ],
    ),
    "cto": Persona(
        persona_id="cto",
        name="CTO",
        description=(
            "Accountable for technology strategy, architecture quality, platform leverage, "
            "innovation readiness and strategic technology debt across agentic workloads."
        ),
        relevant_platforms=["azure", "kubernetes", "foundry", "agent365", "a365"],
        default_kpis=[
            KPI(
                kpi_id="cto_01",
                title="Increase reuse of approved agent patterns across business units",
                description="New agent deployments should derive from approved Foundry templates rather than ad-hoc builds.",
                target="> 80% template reuse for new deployments",
                signal_types=["agent_registrations", "project_health", "deployment_status"],
            ),
            KPI(
                kpi_id="cto_02",
                title="Reduce architecture drift across agentic workloads",
                description="Agents running outside approved architecture patterns create platform risk and integration debt.",
                target="< 5% of agents with architecture drift",
                signal_types=["agent_registrations", "deployment_status", "project_health"],
            ),
            KPI(
                kpi_id="cto_03",
                title="Increase percentage of AI workloads running on approved platforms",
                description="Shadow AI deployments on unapproved platforms must be reduced.",
                target="> 95% of AI workloads on approved platforms",
                signal_types=["agent_registrations", "project_health", "resource_health"],
            ),
            KPI(
                kpi_id="cto_04",
                title="Reduce strategic technology debt in business-critical AI capabilities",
                description="Platform and framework versions in business-critical agents must stay within supported lifecycle.",
                target="0 business-critical agents on end-of-life platforms",
                signal_types=["deployment_status", "resource_health", "project_health"],
            ),
        ],
    ),
    "it_manager": Persona(
        persona_id="it_manager",
        name="IT Manager / Platform Owner",
        description=(
            "Accountable for daily platform operations, reliability, incidents, "
            "deployments and capacity for agent infrastructure."
        ),
        relevant_platforms=["azure", "kubernetes", "microsoft365", "agent365", "a365", "servicenow"],
        default_kpis=[
            KPI(
                kpi_id="itm_01",
                title="Reduce operational incidents caused by agent tool failures",
                description="P1 and P2 incidents directly caused by agent tool failures or connector issues.",
                target="< 2 agent-caused incidents per month",
                signal_types=["incidents", "deployment_status", "resource_health"],
            ),
            KPI(
                kpi_id="itm_02",
                title="Reduce mean time to restore service for agent-enabled workflows",
                description="P1 incidents affecting agent-enabled workflows must be resolved within 4 hours.",
                target="MTTR < 4h for agent-enabled workflow incidents",
                signal_types=["incidents", "sla_compliance", "resource_health"],
            ),
            KPI(
                kpi_id="itm_03",
                title="Improve connector health and platform capacity readiness",
                description="All connectors and agent infrastructure must maintain healthy status with no unplanned capacity gaps.",
                target="100% connector health, 0 unplanned capacity incidents",
                signal_types=["resource_health", "deployment_status", "agent_registrations"],
            ),
            KPI(
                kpi_id="itm_04",
                title="Reduce failed deployments for agentic workloads",
                description="Deployment failures for agent workloads must be tracked and reduced.",
                target="< 5% deployment failure rate",
                signal_types=["deployment_status", "change_requests", "incidents"],
            ),
        ],
    ),
    "security_officer": Persona(
        persona_id="security_officer",
        name="Security Officer",
        description=(
            "Accountable for security posture, identity, access controls, "
            "data exposure risk and threat reduction across AI agent deployments."
        ),
        relevant_platforms=["azure", "microsoft365", "servicenow", "agent365", "a365"],
        default_kpis=[
            KPI(
                kpi_id="sec_01",
                title="Reduce sensitive data exposure through unmanaged agents",
                description="Agents accessing sensitive data without explicit classification or governance controls must be identified and remediated.",
                target="0 unmanaged agents with sensitive data access",
                signal_types=["security_events", "user_activity", "agent_registrations"],
            ),
            KPI(
                kpi_id="sec_02",
                title="Increase coverage of least-privilege access for agent tools",
                description="All agent tool permissions must be reviewed against the minimum required access principle.",
                target="> 90% of agents with verified least-privilege access",
                signal_types=["security_events", "user_activity", "compliance_status"],
            ),
            KPI(
                kpi_id="sec_03",
                title="Reduce privileged access drift across AI-connected platforms",
                description="Service principals and managed identities used by agents must not accumulate excess permissions over time.",
                target="0 agents with privilege drift beyond 30 days",
                signal_types=["security_events", "compliance_status", "user_activity"],
            ),
            KPI(
                kpi_id="sec_04",
                title="Detect and quarantine shadow agents accessing sensitive systems",
                description="Agents not registered in the agent registry but accessing sensitive platform APIs must be detected.",
                target="0 unregistered agents with sensitive system access within 24h of detection",
                signal_types=["security_events", "agent_registrations", "user_activity"],
            ),
        ],
    ),
    "business_owner": Persona(
        persona_id="business_owner",
        name="Business Owner",
        description=(
            "Accountable for process outcomes, productivity, revenue impact "
            "and customer and employee experience improvements from AI agents."
        ),
        relevant_platforms=["salesforce", "foundry", "azure"],
        default_kpis=[
            KPI(
                kpi_id="biz_01",
                title="Improve case resolution speed without reducing customer satisfaction",
                description="Agent-assisted cases should resolve faster while maintaining or improving CSAT.",
                target="-25% resolution time, > 4.2 CSAT",
                signal_types=["case_resolution", "revenue_impact", "agent_invocations"],
            ),
            KPI(
                kpi_id="biz_02",
                title="Increase revenue impact from agent-assisted processes",
                description="Measure and grow the pipeline and revenue influenced by agent assistance.",
                target="> 15% pipeline influenced by agents",
                signal_types=["opportunity_pipeline", "revenue_impact", "agent_invocations"],
            ),
            KPI(
                kpi_id="biz_03",
                title="Reduce manual handoffs in priority business workflows",
                description="Manual handoffs in agent-assisted workflows represent process inefficiency and quality risk.",
                target="< 2 manual handoffs per agent-assisted workflow",
                signal_types=["case_resolution", "agent_invocations", "opportunity_pipeline"],
            ),
            KPI(
                kpi_id="biz_04",
                title="Improve process throughput for high-volume operational tasks",
                description="High-volume tasks assisted by agents should show measurable throughput improvement.",
                target="> 20% throughput improvement for top 3 agent-assisted tasks",
                signal_types=["agent_invocations", "case_resolution", "revenue_impact"],
            ),
        ],
    ),
    "product_owner": Persona(
        persona_id="product_owner",
        name="Product Owner",
        description=(
            "Accountable for product adoption, roadmap delivery, quality "
            "and user value for agent-enabled product capabilities."
        ),
        relevant_platforms=["foundry", "agent365", "a365", "servicenow"],
        default_kpis=[
            KPI(
                kpi_id="po_01",
                title="Increase adoption of agent-enabled product capabilities",
                description="Usage metrics for agent-enabled product features must grow quarter-on-quarter.",
                target="> 30% adoption growth per quarter",
                signal_types=["agent_invocations", "agent_activity"],
            ),
            KPI(
                kpi_id="po_02",
                title="Improve delivery predictability for agent-related roadmap items",
                description="Sprint delivery variance for agent-related features must reduce.",
                target="< 15% sprint delivery variance",
                signal_types=["change_requests", "deployment_status", "agent_activity"],
            ),
            KPI(
                kpi_id="po_03",
                title="Reduce backlog aging for AI governance and enablement features",
                description="AI governance features sitting in backlog for more than 90 days create risk.",
                target="0 governance features in backlog >90 days",
                signal_types=["change_requests", "agent_activity"],
            ),
            KPI(
                kpi_id="po_04",
                title="Improve user satisfaction for agent-assisted experiences",
                description="End users of agent-assisted product flows must report improved satisfaction.",
                target="> 4.0 product experience score for agent-assisted flows",
                signal_types=["agent_invocations", "agent_activity", "case_resolution"],
            ),
        ],
    ),
    "service_owner": Persona(
        persona_id="service_owner",
        name="Service Owner",
        description=(
            "Accountable for SLA attainment, service quality, supportability "
            "and operational continuity for agent-enabled services."
        ),
        relevant_platforms=["servicenow", "azure", "kubernetes", "salesforce"],
        default_kpis=[
            KPI(
                kpi_id="svc_01",
                title="Reduce support escalations caused by poor agent handover",
                description="Escalations triggered by incomplete context handover or poor routing from agent interactions.",
                target="< 5% escalation rate for agent-routed interactions",
                signal_types=["incidents", "case_resolution", "sla_compliance"],
            ),
            KPI(
                kpi_id="svc_02",
                title="Improve SLA attainment for agent-enabled services",
                description="Services backed by agents must consistently meet SLA commitments.",
                target="> 98% SLA attainment for agent-enabled services",
                signal_types=["sla_compliance", "incidents"],
            ),
            KPI(
                kpi_id="svc_03",
                title="Reduce repeat incidents in agent-supported workflows",
                description="Recurring incidents in agent-supported workflows indicate systemic reliability issues.",
                target="< 3 repeat incidents per workflow per quarter",
                signal_types=["incidents", "sla_compliance", "resource_health"],
            ),
            KPI(
                kpi_id="svc_04",
                title="Increase service readiness for new agent releases",
                description="New agent releases must pass service readiness checks before going live.",
                target="100% of agent releases pass service readiness gate",
                signal_types=["deployment_status", "change_requests", "incidents"],
            ),
        ],
    ),
}
