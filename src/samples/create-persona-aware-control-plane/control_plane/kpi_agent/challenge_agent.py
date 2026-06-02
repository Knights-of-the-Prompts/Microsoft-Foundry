"""KPI Challenge Agent — helps personas turn vague KPIs into governance-grade KPIs.

Responsibilities:
1. Accept persona and draft KPI.
2. Determine maturity level: vague | usable | well_articulated | control_ready.
3. Generate persona-specific challenge questions targeting governance gaps.
4. Identify missing KPI fields (metric, target, timeframe, scope, etc.).
5. Suggest a stronger formalized KPI based on available context.
6. Accept user answers and produce a FormalizedKpi when sufficient.
7. Write evidence events: kpi_challenge_started, kpi_questions_generated, kpi_formalized.

Design rules:
- Deterministic in mock mode — no LLM dependency for demo.
- Never duplicates KPI Agent interpret logic.
- Persona-specific question banks ensure relevance.
- Confidence score reflects how complete the KPI fields are.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from control_plane.models.kpi_refinement import (
    ChallengeSessionStatus,
    FormalizedKpi,
    KpiChallengeSession,
    KpiMaturityLevel,
)
from control_plane.stores import evidence_store

if TYPE_CHECKING:
    from control_plane.kpi_agent.llm_client import LlmClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persona descriptions — used in LLM system prompts
# ---------------------------------------------------------------------------

_PERSONA_DESCRIPTIONS: Dict[str, str] = {
    "cfo": "Chief Financial Officer — responsible for AI investment ROI, cost governance and value attribution.",
    "cto": "Chief Technology Officer — responsible for architecture quality, platform adoption and technical strategy.",
    "compliance_officer": "Compliance Officer — responsible for regulatory adherence, audit readiness and evidence coverage.",
    "it_manager": "IT Manager — responsible for operational stability, incident management and platform reliability.",
    "security_officer": "Security Officer — responsible for data protection, access governance and risk reduction.",
    "business_owner": "Business Owner — responsible for measurable business outcomes, revenue and customer impact.",
    "product_owner": "Product Owner — responsible for feature delivery, adoption metrics and user value.",
    "service_owner": "Service Owner — responsible for SLA attainment, escalation reduction and service quality.",
}

# ---------------------------------------------------------------------------
# JSON schemas for structured LLM output
# ---------------------------------------------------------------------------

_CHALLENGE_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "challenge_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "4-6 targeted governance questions to improve the KPI.",
        },
        "suggested_formalized_kpi": {
            "type": "object",
            "description": "A suggested formalized KPI structure with all governance fields.",
        },
        "missing_fields": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of governance fields still missing from the draft KPI.",
        },
        "confidence_score": {
            "type": "number",
            "description": "Confidence score between 0.0 and 1.0 reflecting KPI completeness.",
        },
    },
    "required": ["challenge_questions", "suggested_formalized_kpi", "missing_fields", "confidence_score"],
}

_FORMALIZE_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "outcome_statement": {"type": "string"},
        "metric": {"type": "string"},
        "target": {"type": "string"},
        "timeframe": {"type": "string"},
        "scope": {"type": "string"},
        "included_entities": {"type": "array", "items": {"type": "string"}},
        "excluded_entities": {"type": "array", "items": {"type": "string"}},
        "tradeoffs": {"type": "array", "items": {"type": "string"}},
        "evidence_standard": {"type": "string"},
        "risk_tolerance": {"type": "string"},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "confidence_score": {"type": "number"},
    },
    "required": [
        "title", "outcome_statement", "metric", "target", "timeframe", "scope",
        "included_entities", "excluded_entities", "tradeoffs", "evidence_standard",
        "risk_tolerance", "success_criteria", "confidence_score",
    ],
}


# ---------------------------------------------------------------------------
# LLM prompt helpers
# ---------------------------------------------------------------------------

def _build_challenge_system_prompt(persona_id: str) -> str:
    persona_desc = _PERSONA_DESCRIPTIONS.get(persona_id, f"Business persona: {persona_id}")
    return (
        "You are a KPI governance advisor helping an enterprise persona turn a vague "
        "draft KPI into a governance-grade, control-ready KPI.\n\n"
        f"Persona: {persona_desc}\n\n"
        "Your task:\n"
        "1. Generate 4-6 targeted challenge questions that uncover governance gaps in the draft KPI.\n"
        "2. Suggest a formalized KPI structure with all fields filled.\n"
        "3. Identify which governance fields are still missing (metric, target, timeframe, scope, "
        "evidence_standard, risk_tolerance).\n"
        "4. Assign a confidence score between 0.0 and 1.0 reflecting KPI completeness.\n\n"
        "The suggested_formalized_kpi must contain: title, outcome_statement, metric, target, "
        "timeframe, scope, included_entities, excluded_entities, tradeoffs, evidence_standard, "
        "risk_tolerance, success_criteria, confidence_score.\n\n"
        "Respond strictly in JSON matching the provided schema. No markdown, no prose outside JSON."
    )


def _build_challenge_user_prompt(
    draft_kpi: str,
    maturity: str,
    missing_fields: List[str],
) -> str:
    return (
        f"Draft KPI: {draft_kpi}\n"
        f"Assessed maturity: {maturity}\n"
        f"Missing governance fields: {', '.join(missing_fields) if missing_fields else 'none identified yet'}\n\n"
        "Generate challenge questions, a suggested formalized KPI, and a confidence score."
    )


def _build_formalize_system_prompt(persona_id: str) -> str:
    persona_desc = _PERSONA_DESCRIPTIONS.get(persona_id, f"Business persona: {persona_id}")
    return (
        "You are a KPI governance advisor finalizing a governance-grade KPI based on user answers.\n\n"
        f"Persona: {persona_desc}\n\n"
        "Your task: Incorporate the user's answers into the draft KPI and produce a complete, "
        "governance-grade formalized KPI with all required fields.\n\n"
        "The output must be a JSON object with: title, outcome_statement, metric, target, timeframe, "
        "scope, included_entities (list), excluded_entities (list), tradeoffs (list), "
        "evidence_standard, risk_tolerance, success_criteria (list), confidence_score (0.0–1.0).\n\n"
        "Respond strictly in JSON matching the provided schema. No markdown, no prose outside JSON."
    )


def _build_formalize_user_prompt(
    draft_kpi: str,
    answers: Dict[str, str],
    maturity: str,
) -> str:
    answers_text = "\n".join(f"  - {k}: {v}" for k, v in answers.items()) if answers else "  (none)"
    return (
        f"Draft KPI: {draft_kpi}\n"
        f"Maturity after enrichment: {maturity}\n"
        f"User answers:\n{answers_text}\n\n"
        "Produce a complete formalized KPI incorporating all of the above."
    )


# ---------------------------------------------------------------------------

_CHALLENGE_QUESTIONS: Dict[str, List[str]] = {
    "cfo": [
        "Are you optimizing total AI spend, cost per outcome, cost-to-value ratio or ROI?",
        "Which value signal must not degrade while you reduce cost?",
        "Should shared platform costs be allocated to agents, business units or business outcomes?",
        "What minimum evidence confidence is required before scaling investment?",
        "Over what timeframe should ROI be measured — monthly, quarterly or annually?",
        "Which funded agent initiatives are in scope?",
    ],
    "cto": [
        "Are you improving architecture consistency, platform adoption, reuse or strategic technical debt?",
        "Which agentic workloads or business units are in scope?",
        "What counts as approved architecture: platform, pattern, reference implementation or control baseline?",
        "Which trade-off is acceptable: slower delivery, higher platform cost or lower autonomy?",
        "What is the current baseline and how is it measured today?",
    ],
    "compliance_officer": [
        "Which regulatory or internal control domain is in scope?",
        "Which risk tiers or agent types are included?",
        "What evidence would prove audit readiness improved?",
        "What is the acceptable age of open exceptions or waivers?",
        "Should this cover all agents or only agents with access to regulated data?",
    ],
    "it_manager": [
        "Are you targeting incident volume, MTTR, tool failure rate, deployment stability or connector health?",
        "Which platforms or agent-enabled workflows are in scope?",
        "What incident severity levels should be included?",
        "What operational action should become possible if the KPI is breached?",
        "Should this KPI cover production only or also staging and dev environments?",
    ],
    "security_officer": [
        "Are you reducing data exposure, privileged access drift, unmanaged agents or tool over-permissioning?",
        "Which sensitivity levels are in scope?",
        "Which access model should be enforced: least privilege, approval-based, time-bound or break-glass?",
        "What signal would prove that risk was reduced rather than redistributed?",
        "Are you measuring potential exposure risk or confirmed exposure events?",
    ],
    "business_owner": [
        "Which business outcome matters most: revenue, case resolution, throughput, customer satisfaction or productivity?",
        "Which process or customer journey is in scope?",
        "What value signal should the control plane track?",
        "Which operational trade-off is acceptable while pursuing this KPI?",
        "What current baseline are you improving against?",
    ],
    "product_owner": [
        "Are you optimizing adoption, delivery predictability, feature quality or user value?",
        "Which roadmap item or agent-enabled capability is in scope?",
        "What adoption or quality threshold defines success?",
        "Which user segment is affected?",
        "Over what delivery period should progress be measured?",
    ],
    "service_owner": [
        "Are you targeting SLA attainment, escalations, repeat incidents, handover quality or service readiness?",
        "Which service or support workflow is in scope?",
        "What threshold should trigger a control action?",
        "Which evidence is needed for service review?",
        "Should this KPI include all severity levels or only P1/P2?",
    ],
}

_DEFAULT_CHALLENGE_QUESTIONS = [
    "What does success look like for this KPI in measurable terms?",
    "What is the current baseline you are improving against?",
    "Which systems, agents or business processes are in scope?",
    "What is the timeframe for achieving this KPI?",
    "What evidence would prove the KPI was met?",
]

# ---------------------------------------------------------------------------
# Required KPI fields — used for gap analysis
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = [
    "business_outcome",
    "metric",
    "target",
    "timeframe",
    "scope",
    "evidence_standard",
]

# ---------------------------------------------------------------------------
# Persona-specific suggested formalized KPIs for common draft patterns
# ---------------------------------------------------------------------------

_SUGGESTED_KPI_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "cfo": {
        "title": "Maintain minimum 3x ROI for funded agent initiatives",
        "outcome_statement": (
            "Demonstrate that funded agent initiatives generate at least 3x the value "
            "relative to their total cost — measured by evidence-backed business value "
            "divided by allocated model, runtime, platform and operational costs."
        ),
        "metric": "ROI = (attributed business value) / (model + compute + platform + operational cost)",
        "target": ">= 3.0x ROI with >= 80% value confidence",
        "timeframe": "Rolling quarter",
        "scope": "All production agent initiatives with allocated budget",
        "included_entities": ["funded agent workloads", "Azure OpenAI costs", "AKS compute", "Salesforce pipeline impact"],
        "excluded_entities": ["experimental / sandbox agents", "shared infrastructure not attributable to agents"],
        "tradeoffs": ["Higher evidence rigor may slow initial measurement", "Some value attribution is estimated, not directly observed"],
        "evidence_standard": "Minimum 80% value confidence; evidence events required for every attributed outcome",
        "risk_tolerance": "Low — investment decisions must not be made on unverified ROI signals",
        "success_criteria": [
            "Agent ROI >= 3x for all funded initiatives",
            "< 10% unallocated AI spend",
            "Evidence confidence >= 80% for all value signals",
            "Cost attribution tags present on >= 90% of Azure resources",
        ],
        "confidence_score": 0.87,
    },
    "compliance_officer": {
        "title": "Achieve 100% evidence trail coverage for high-risk agent invocations",
        "outcome_statement": (
            "Every invocation of a high-risk AI agent must produce an immutable "
            "evidence event traceable to an accountability owner."
        ),
        "metric": "% of high-risk agent invocations with evidence trail coverage",
        "target": "100% coverage, 0 open P1 audit findings",
        "timeframe": "30-day rolling window",
        "scope": "All agents classified as high-risk in production",
        "included_entities": ["agents with access to regulated data", "agents with financial approval capability"],
        "excluded_entities": ["read-only agents", "experimental agents in sandbox environments"],
        "tradeoffs": ["Evidence generation adds minimal latency per invocation"],
        "evidence_standard": "Immutable evidence event per invocation; ownership documented in Agent 365",
        "risk_tolerance": "Zero — high-risk agents without evidence trail coverage represent unacceptable audit risk",
        "success_criteria": [
            "100% high-risk agent invocation coverage",
            "0 agents without assigned ownership",
            "0 open P1 compliance findings",
        ],
        "confidence_score": 0.82,
    },
    "cto": {
        "title": "Maintain >= 80% approved architecture pattern reuse across new agent deployments",
        "outcome_statement": (
            "New agent deployments must derive from approved Foundry templates or reference "
            "implementations to reduce architecture drift and integration debt."
        ),
        "metric": "% of new agent deployments using approved patterns",
        "target": ">= 80% template reuse for new deployments this quarter",
        "timeframe": "Quarterly",
        "scope": "All new agent deployments across all business units",
        "included_entities": ["production deployments", "staged for production"],
        "excluded_entities": ["proof-of-concept agents", "sandbox experiments"],
        "tradeoffs": ["Requiring pattern reuse may slow initial development for novel use cases"],
        "evidence_standard": "Deployment tagged with template reference; architecture review sign-off",
        "risk_tolerance": "Medium — some exceptions acceptable with documented justification",
        "success_criteria": [
            ">= 80% new deployments using approved templates",
            "< 5% architecture drift across existing agents",
            "All exceptions documented with rationale",
        ],
        "confidence_score": 0.79,
    },
    "it_manager": {
        "title": "Reduce agent-caused P1/P2 operational incidents below 2 per month",
        "outcome_statement": (
            "Minimize operational disruption caused by agent tool failures, "
            "connector degradation or deployment instability."
        ),
        "metric": "Count of P1/P2 incidents directly caused by agent tooling failures per month",
        "target": "< 2 agent-caused P1/P2 incidents per calendar month",
        "timeframe": "Monthly",
        "scope": "All production agent infrastructure and connector integrations",
        "included_entities": ["production agents", "connector health", "deployment pipelines"],
        "excluded_entities": ["incidents caused by upstream platform failures outside agent control"],
        "tradeoffs": ["Zero tolerance may require additional monitoring overhead"],
        "evidence_standard": "Incident linked to agent tooling root cause in ServiceNow; MTTR tracked",
        "risk_tolerance": "Low for P1; Medium for P2",
        "success_criteria": [
            "< 2 agent-caused P1/P2 incidents per month",
            "MTTR for agent-caused incidents < 4 hours",
            "100% incidents have root cause documented",
        ],
        "confidence_score": 0.81,
    },
    "security_officer": {
        "title": "Eliminate unauthorized data access events by AI agents within 30 days",
        "outcome_statement": (
            "No AI agent should access data classified above its authorized sensitivity level. "
            "All access must comply with least-privilege assignments."
        ),
        "metric": "Count of unauthorized data access events by AI agents",
        "target": "0 unauthorized access events per quarter",
        "timeframe": "30-day detection window; quarterly review",
        "scope": "All production agents with access to data classified as Confidential or above",
        "included_entities": ["agents with delegated user identity", "agents with service principal access"],
        "excluded_entities": ["agents accessing only public data"],
        "tradeoffs": ["Stricter access controls may require additional approval workflows"],
        "evidence_standard": "Access event log with classification level; anomaly detection signal from Azure",
        "risk_tolerance": "Zero — unauthorized access events are unacceptable regardless of business justification",
        "success_criteria": [
            "0 unauthorized data access events",
            "100% agents operating under least-privilege assignments",
            "All access reviewed within 90-day cycle",
        ],
        "confidence_score": 0.84,
    },
    "business_owner": {
        "title": "Achieve measurable business outcome improvement from agent-assisted processes",
        "outcome_statement": (
            "Agent-assisted processes must demonstrate measurable improvement in the "
            "designated business outcome metric within the defined timeframe."
        ),
        "metric": "Primary business outcome metric (revenue / throughput / resolution speed / CSAT)",
        "target": "Define specific target during formalization",
        "timeframe": "Quarterly",
        "scope": "Designated process or customer journey in scope",
        "included_entities": ["agent-assisted interactions", "process steps where agents are active"],
        "excluded_entities": ["interactions not touched by agents"],
        "tradeoffs": ["Attribution of value to agents vs other improvements requires controlled measurement"],
        "evidence_standard": "Outcome signal from source system; agent invocation correlated to outcome event",
        "risk_tolerance": "Medium — some variance in attribution methodology is acceptable",
        "success_criteria": [
            "Measurable improvement in primary outcome metric",
            "Agent contribution attributable with >= 70% confidence",
        ],
        "confidence_score": 0.72,
    },
    "product_owner": {
        "title": "Improve agent-enabled feature adoption and delivery predictability",
        "outcome_statement": (
            "Agent-enabled capabilities must demonstrate measurable improvement in adoption, "
            "delivery predictability or user-perceived value within the product roadmap."
        ),
        "metric": "Adoption rate / delivery cycle time / defect rate for agent-enabled features",
        "target": "Define specific threshold during formalization",
        "timeframe": "Per sprint / quarterly",
        "scope": "Agent-enabled features in the active product roadmap",
        "included_entities": ["released agent features", "features in active delivery"],
        "excluded_entities": ["features not yet in development"],
        "tradeoffs": ["Measuring adoption requires instrumentation investment"],
        "evidence_standard": "Usage telemetry from product; delivery metrics from engineering",
        "risk_tolerance": "Medium",
        "success_criteria": [
            "Adoption target met within defined timeframe",
            "Delivery predictability improved",
        ],
        "confidence_score": 0.70,
    },
    "service_owner": {
        "title": "Improve SLA attainment and reduce escalations for agent-assisted service workflows",
        "outcome_statement": (
            "Agent-assisted service workflows must achieve defined SLA targets and "
            "reduce escalation volume through improved routing and resolution quality."
        ),
        "metric": "SLA attainment rate and escalation count for agent-assisted cases",
        "target": ">= 95% SLA attainment; < defined escalation threshold",
        "timeframe": "Monthly",
        "scope": "All service workflows where agents assist with routing, resolution or handover",
        "included_entities": ["P1/P2 incidents", "customer-facing service cases"],
        "excluded_entities": ["cases handled entirely without agent involvement"],
        "tradeoffs": ["Stricter SLA targets may require more agent capacity"],
        "evidence_standard": "SLA compliance recorded in ServiceNow; agent involvement tagged",
        "risk_tolerance": "Low for SLA; Medium for escalation targets",
        "success_criteria": [
            ">= 95% SLA attainment",
            "Escalation rate below defined threshold",
            "Agent contribution to resolution documented",
        ],
        "confidence_score": 0.76,
    },
}


# ---------------------------------------------------------------------------
# Maturity classification
# ---------------------------------------------------------------------------

_VAGUE_KEYWORDS = {
    "improve", "better", "enhance", "increase", "decrease", "reduce",
    "optimize", "fix", "manage", "handle", "deal with",
}

_SPECIFIC_TERMS = {
    "unauthorized", "audit", "compliance", "cost", "uptime", "incident",
    "sla", "pipeline", "latency", "error rate", "coverage", "ownership",
    "token", "spend", "roi", "throughput", "vulnerability", "sign-in",
    "exposure", "resolution", "escalation", "reuse", "pattern", "%", "$", "x",
}


def _classify_maturity(kpi_text: str) -> KpiMaturityLevel:
    lower = kpi_text.lower().strip()
    words = set(lower.split())

    if len(lower) < 15:
        return KpiMaturityLevel.VAGUE

    vague_hit = bool(words & _VAGUE_KEYWORDS)
    has_specifics = any(t in lower for t in _SPECIFIC_TERMS)
    has_number = any(c.isdigit() for c in lower)
    has_time = any(t in lower for t in [
        "day", "week", "month", "quarter", "sprint", "q1", "q2", "q3", "q4",
    ])

    if vague_hit and not has_specifics:
        return KpiMaturityLevel.VAGUE
    if not has_number:
        return KpiMaturityLevel.USABLE
    if has_number and has_time:
        return KpiMaturityLevel.WELL_ARTICULATED
    return KpiMaturityLevel.USABLE


def _score_maturity(level: KpiMaturityLevel) -> float:
    return {
        KpiMaturityLevel.VAGUE: 0.2,
        KpiMaturityLevel.USABLE: 0.5,
        KpiMaturityLevel.WELL_ARTICULATED: 0.72,
        KpiMaturityLevel.CONTROL_READY: 0.90,
    }[level]


def _identify_missing_fields(kpi_text: str, answers: Dict[str, str]) -> List[str]:
    """Return fields that are not yet addressed in the KPI text or answers."""
    lower = kpi_text.lower()
    missing = []

    has_metric = any(c.isdigit() for c in lower) or "%" in lower or "$" in lower
    if not has_metric and "metric" not in answers and "target" not in answers:
        missing.append("metric")

    has_target = any(c.isdigit() for c in lower)
    if not has_target and "target" not in answers:
        missing.append("target")

    has_time = any(t in lower for t in ["day", "week", "month", "quarter", "sprint", "year", "q1", "q2", "q3", "q4"])
    if not has_time and "timeframe" not in answers:
        missing.append("timeframe")

    has_scope = any(t in lower for t in ["all", "production", "scope", "business unit", "platform", "agents", "initiatives"])
    if not has_scope and "scope" not in answers:
        missing.append("scope")

    if "evidence_standard" not in answers:
        missing.append("evidence_standard")

    return missing


# ---------------------------------------------------------------------------
# KPI Challenge Agent
# ---------------------------------------------------------------------------


class KpiChallengeAgent:
    """Challenges a draft KPI and produces a formalized version.

    When an ``LlmClient`` is provided and ``CONTROL_PLANE_KPI_LLM_ENABLED=true``,
    challenge questions and KPI formalization are generated by the LLM.  On any
    failure (unavailable endpoint, parse error, etc.) the agent falls back to the
    deterministic static templates transparently.
    """

    def __init__(self, llm_client: Optional["LlmClient"] = None) -> None:
        self._llm = llm_client

    def challenge(
        self,
        persona_id: str,
        draft_kpi: str,
    ) -> KpiChallengeSession:
        """Assess the draft KPI and return a challenge session.

        Evidence events written: kpi_challenge_started, kpi_questions_generated.
        """
        session_id = str(uuid.uuid4())
        maturity = _classify_maturity(draft_kpi)
        missing = _identify_missing_fields(draft_kpi, {})

        # ------------------------------------------------------------------
        # Try LLM-driven challenge (graceful fallback to static on any failure)
        # ------------------------------------------------------------------
        llm_result = self._try_llm_challenge(persona_id, draft_kpi, maturity, missing)

        if llm_result is not None:
            questions = llm_result.get("challenge_questions") or []
            suggested = llm_result.get("suggested_formalized_kpi") or {}
            missing = llm_result.get("missing_fields", missing)
            confidence = float(llm_result.get("confidence_score") or _score_maturity(maturity))
            logger.debug("KpiChallengeAgent.challenge: LLM path used for persona=%s", persona_id)
        else:
            questions = _CHALLENGE_QUESTIONS.get(persona_id, _DEFAULT_CHALLENGE_QUESTIONS)
            suggested = _SUGGESTED_KPI_TEMPLATES.get(persona_id, {})
            confidence = _score_maturity(maturity)

        evidence_store.add_event(
            "kpi_challenge_started",
            {
                "session_id": session_id,
                "persona_id": persona_id,
                "draft_kpi": draft_kpi,
                "maturity_level": maturity.value,
            },
            persona_id=persona_id,
        )
        evidence_store.add_event(
            "kpi_questions_generated",
            {
                "session_id": session_id,
                "question_count": len(questions),
                "missing_fields": missing,
            },
            persona_id=persona_id,
        )

        return KpiChallengeSession(
            id=session_id,
            persona_id=persona_id,
            draft_kpi=draft_kpi,
            maturity_level=maturity,
            challenge_questions=questions,
            suggested_formalized_kpi=suggested,
            missing_fields=missing,
            confidence_score=confidence,
            status=ChallengeSessionStatus.CHALLENGED,
        )

    def formalize(
        self,
        session_id: str,
        persona_id: str,
        draft_kpi: str,
        answers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Incorporate user answers and produce a FormalizedKpi.

        Evidence events written: kpi_formalized.
        """
        # Re-assess maturity with answers applied
        enriched_kpi = f"{draft_kpi} {' '.join(answers.values())}"
        maturity = _classify_maturity(enriched_kpi)
        if answers and maturity == KpiMaturityLevel.VAGUE:
            maturity = KpiMaturityLevel.USABLE

        remaining_missing = _identify_missing_fields(draft_kpi, answers)
        if not remaining_missing:
            maturity = KpiMaturityLevel.CONTROL_READY

        confidence = _score_maturity(maturity)
        if answers:
            confidence = min(0.95, confidence + 0.1 * len(answers))

        # ------------------------------------------------------------------
        # Try LLM-driven formalization (graceful fallback to static on any failure)
        # ------------------------------------------------------------------
        llm_result = self._try_llm_formalize(persona_id, draft_kpi, answers, maturity)

        if llm_result is not None:
            logger.debug("KpiChallengeAgent.formalize: LLM path used for persona=%s", persona_id)
            confidence = float(llm_result.get("confidence_score") or confidence)
            formalized = FormalizedKpi(
                id=str(uuid.uuid4()),
                persona_id=persona_id,
                title=llm_result.get("title", draft_kpi),
                outcome_statement=llm_result.get("outcome_statement", draft_kpi),
                metric=llm_result.get("metric", "Define a measurable metric"),
                target=llm_result.get("target", "Define a target value"),
                timeframe=llm_result.get("timeframe", "Not specified"),
                scope=llm_result.get("scope", "All relevant systems"),
                included_entities=llm_result.get("included_entities") or [],
                excluded_entities=llm_result.get("excluded_entities") or [],
                tradeoffs=llm_result.get("tradeoffs") or [],
                evidence_standard=llm_result.get("evidence_standard", "Evidence events required"),
                risk_tolerance=llm_result.get("risk_tolerance", "Medium"),
                success_criteria=llm_result.get("success_criteria") or [],
                confidence_score=round(confidence, 2),
            )
        else:
            template = _SUGGESTED_KPI_TEMPLATES.get(persona_id, {})
            outcome = answers.get("business_outcome", template.get("outcome_statement", draft_kpi))
            metric = answers.get("metric", template.get("metric", "Define a measurable metric"))
            target = answers.get("target", template.get("target", "Define a target value"))
            timeframe = answers.get("timeframe", template.get("timeframe", "Not specified"))
            scope = answers.get("scope", template.get("scope", "All relevant systems"))
            evidence_std = answers.get(
                "evidence_standard",
                template.get("evidence_standard", "Evidence events required for every relevant action"),
            )
            formalized = FormalizedKpi(
                id=str(uuid.uuid4()),
                persona_id=persona_id,
                title=template.get("title", draft_kpi),
                outcome_statement=outcome,
                metric=metric,
                target=target,
                timeframe=timeframe,
                scope=scope,
                included_entities=template.get("included_entities", []),
                excluded_entities=template.get("excluded_entities", []),
                tradeoffs=template.get("tradeoffs", []),
                evidence_standard=evidence_std,
                risk_tolerance=template.get("risk_tolerance", answers.get("risk_tolerance", "Medium")),
                success_criteria=template.get("success_criteria", [target]),
                confidence_score=round(confidence, 2),
            )

        evidence_store.add_event(
            "kpi_formalized",
            {
                "session_id": session_id,
                "formalized_kpi_id": formalized.id,
                "persona_id": persona_id,
                "confidence_score": formalized.confidence_score,
                "maturity_level": maturity.value,
            },
            persona_id=persona_id,
        )

        return {
            "formalized_kpi": formalized.to_dict(),
            "maturity_level": maturity.value,
            "confidence_score": round(confidence, 2),
            "remaining_questions": _CHALLENGE_QUESTIONS.get(persona_id, [])[:2] if remaining_missing else [],
        }

    # ------------------------------------------------------------------
    # Private LLM helpers
    # ------------------------------------------------------------------

    def _try_llm_challenge(
        self,
        persona_id: str,
        draft_kpi: str,
        maturity: KpiMaturityLevel,
        missing_fields: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Attempt an LLM-driven challenge.  Returns None on any failure."""
        if self._llm is None or not self._llm.is_available():
            return None
        messages = [
            {"role": "system", "content": _build_challenge_system_prompt(persona_id)},
            {"role": "user", "content": _build_challenge_user_prompt(
                draft_kpi, maturity.value, missing_fields
            )},
        ]
        result = self._llm.chat_complete(messages, json_schema=_CHALLENGE_RESPONSE_SCHEMA)
        if result is None:
            return None
        # Validate minimal required keys exist
        if "challenge_questions" not in result or "suggested_formalized_kpi" not in result:
            logger.warning("LLM challenge response missing required keys — falling back to static")
            return None
        return result

    def _try_llm_formalize(
        self,
        persona_id: str,
        draft_kpi: str,
        answers: Dict[str, str],
        maturity: KpiMaturityLevel,
    ) -> Optional[Dict[str, Any]]:
        """Attempt an LLM-driven formalization.  Returns None on any failure."""
        if self._llm is None or not self._llm.is_available():
            return None
        messages = [
            {"role": "system", "content": _build_formalize_system_prompt(persona_id)},
            {"role": "user", "content": _build_formalize_user_prompt(
                draft_kpi, answers, maturity.value
            )},
        ]
        result = self._llm.chat_complete(
            messages,
            json_schema=_FORMALIZE_RESPONSE_SCHEMA,
            max_tokens=1500,
        )
        if result is None:
            return None
        # Validate minimal required keys exist
        required = {"title", "outcome_statement", "metric", "target"}
        if not required.issubset(result.keys()):
            logger.warning("LLM formalize response missing required keys — falling back to static")
            return None
        return result
