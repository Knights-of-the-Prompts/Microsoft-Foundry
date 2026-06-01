"""FastAPI backend for the Persona-Aware Control Plane demo.

Run locally (mock mode — no credentials required)::

    cd src/samples/create-persona-aware-control-plane
    uvicorn app:app --reload --port 8000

Environment variables (all optional for mock mode):
    CONTROL_PLANE_MODE=mock|live|hybrid   (default: mock)
    See .env.example for platform-specific credentials.

API overview
------------
GET  /api/personas                         List all personas
GET  /api/personas/{persona_id}            Persona detail with default KPIs

GET  /api/connectors                       List all connectors + health
GET  /api/connectors/{connector_id}        Single connector detail
POST /api/connectors/{connector_id}/configure   Save config (mock)
POST /api/connectors/{connector_id}/test        Run health check
POST /api/connectors/{connector_id}/enable      Enable connector
POST /api/connectors/{connector_id}/disable     Disable connector

GET  /api/tools                            List all enabled tools

POST /api/kpi-agent/interpret              Run KPI Agent for a persona
GET  /api/agent-requests                   List submitted agent requests
POST /api/agent-requests                   Submit a new agent request
GET  /api/evidence                         Query evidence trail

GET  /api/access/personas/{persona_id}/grants  Current access grants for a persona
POST /api/access/check                         Run access readiness check
POST /api/access/requests                      Submit an access request
GET  /api/access/requests                      List access requests
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from control_plane.access_readiness import AccessReadinessAgent
from control_plane.connectors import ALL_CONNECTORS
from control_plane.connectors.registry import ToolRegistry
from control_plane.kpi_agent.agent import KPIAgent
from control_plane.kpi_agent.challenge_agent import KpiChallengeAgent
from control_plane.kpi_agent.control_composition_agent import ControlCompositionAgent
from control_plane.models.access import AccessRequest as AccessReq, AccessRequestStatus
from control_plane.models.config import ControlPlaneConfig
from control_plane.models.governance import AgentRequest, AgentRequestStatus as AgentReqStatus
from control_plane.models.personas import PERSONA_CATALOGUE
from control_plane.stores import evidence_store, request_store

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

BASE = Path(__file__).parent

app = FastAPI(
    title="Persona-Aware Control Plane",
    description=(
        "Local control plane backend for the Accountable Agents blog series. "
        "Part 4: Persona-Aware Control Plane. "
        "All endpoints work in mock mode without credentials."
    ),
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

# ---------------------------------------------------------------------------
# UI route
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_ui(request: Request) -> HTMLResponse:
    """Serve the single-page control plane UI."""
    return templates.TemplateResponse(request=request, name="index.html", context={"v": int(time.time())})


# ---------------------------------------------------------------------------
# Bootstrap: initialise registry and agent at startup
# ---------------------------------------------------------------------------

registry = ToolRegistry()
config = ControlPlaneConfig.from_env()

for connector_cls in ALL_CONNECTORS:
    registry.register(connector_cls())

kpi_agent = KPIAgent(registry)
access_agent = AccessReadinessAgent(registry)
kpi_challenge_agent = KpiChallengeAgent()
control_composition_agent = ControlCompositionAgent(kpi_agent, registry, access_agent)

# In-memory store for access requests (similar pattern to agent request_store)
_access_requests: List[Dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class KPIInterpretRequest(BaseModel):
    persona_id: str
    kpi: Optional[str] = None
    mode: Optional[str] = "mock"


class KPIChallengeRequest(BaseModel):
    persona_id: str
    draft_kpi: str


class KPIFormalizeRequest(BaseModel):
    session_id: str
    persona_id: str
    draft_kpi: str
    answers: Dict[str, str] = {}


class KPIControlPackageRequest(BaseModel):
    persona_id: str
    formalized_kpi: Dict[str, Any]
    mode: Optional[str] = "mock"


class AgentRequestCreate(BaseModel):
    agent_idea_id: str
    requested_by_persona: str
    linked_kpi_id: str
    rationale: str


class ConnectorConfigRequest(BaseModel):
    base_url: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    mode: Optional[str] = "mock"


# ---------------------------------------------------------------------------
# Helper: connector lookup
# ---------------------------------------------------------------------------

def _get_connector(connector_id: str):
    """Return the registered connector instance or raise 404."""
    for pid, connector in registry._connectors.items():
        if pid == connector_id:
            return connector
    raise HTTPException(status_code=404, detail=f"Connector '{connector_id}' not found.")


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------


@app.get("/api/personas", tags=["Personas"], summary="List all personas")
def list_personas() -> List[Dict[str, Any]]:
    """Return all personas with their default KPIs and relevant platforms."""
    result = []
    for persona_id, persona in PERSONA_CATALOGUE.items():
        result.append({
            "id": persona.persona_id,
            "name": persona.name,
            "description": persona.description,
            "relevant_platforms": persona.relevant_platforms,
            "default_kpis": [
                {
                    "kpi_id": k.kpi_id,
                    "title": k.title,
                    "description": k.description,
                    "signal_types": k.signal_types,
                    "target": k.target,
                    "notes": k.notes,
                }
                for k in persona.default_kpis
            ],
        })
    return result


@app.get("/api/personas/{persona_id}", tags=["Personas"], summary="Persona detail")
def get_persona(persona_id: str) -> Dict[str, Any]:
    """Return a single persona by ID."""
    persona = PERSONA_CATALOGUE.get(persona_id)
    if persona is None:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{persona_id}' not found. "
            f"Available: {list(PERSONA_CATALOGUE.keys())}",
        )
    return {
        "id": persona.persona_id,
        "name": persona.name,
        "description": persona.description,
        "relevant_platforms": persona.relevant_platforms,
        "default_kpis": [
            {
                "kpi_id": k.kpi_id,
                "title": k.title,
                "description": k.description,
                "signal_types": k.signal_types,
                "target": k.target,
                "notes": k.notes,
            }
            for k in persona.default_kpis
        ],
    }


# ---------------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------------


@app.get("/api/connectors", tags=["Connectors"], summary="List all connectors with health")
def list_connectors() -> List[Dict[str, Any]]:
    """Return all registered connectors with definition and current health."""
    result = []
    for connector in registry._connectors.values():
        defn = connector.get_definition()
        health = connector.get_health()
        result.append({
            "id": defn.id,
            "platform_id": defn.platform_id,
            "name": defn.name,
            "description": defn.description,
            "mode": defn.mode.value,
            "status": defn.status.value,
            "auth_type": defn.auth_type.value,
            "supported_signal_types": defn.supported_signal_types,
            "supported_tools": defn.supported_tools,
            "health": {
                "status": health.get("status", "unknown"),
                "latency_ms": health.get("latency_ms"),
                "checked_at": health.get("checked_at"),
                "error": health.get("error"),
            },
        })
    return result


@app.get("/api/connectors/{connector_id}", tags=["Connectors"], summary="Connector detail")
def get_connector(connector_id: str) -> Dict[str, Any]:
    """Return a single connector with its tools."""
    connector = _get_connector(connector_id)
    defn = connector.get_definition()
    tools = connector.get_available_tools()
    return {
        "id": defn.id,
        "platform_id": defn.platform_id,
        "name": defn.name,
        "description": defn.description,
        "mode": defn.mode.value,
        "status": defn.status.value,
        "auth_type": defn.auth_type.value,
        "base_url": defn.base_url,
        "required_scopes": defn.required_scopes,
        "supported_signal_types": defn.supported_signal_types,
        "tools": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "signal_types": t.signal_types_returned,
                "enabled": t.enabled,
                "source_mode": t.source_mode.value,
            }
            for t in tools
        ],
    }


@app.post("/api/connectors/{connector_id}/configure", tags=["Connectors"], summary="Save connector config")
def configure_connector(connector_id: str, body: ConnectorConfigRequest) -> Dict[str, Any]:
    """Accept a configuration payload.

    In mock mode this is a no-op — the connector is always available.
    In a real implementation this would persist the config and re-initialise
    the connector with the new credentials.
    """
    from control_plane.connectors.base import ConnectorMode
    connector = _get_connector(connector_id)
    if body.mode:
        try:
            connector.set_mode(ConnectorMode(body.mode))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid mode '{body.mode}'. Use mock, live, or hybrid.")
    defn = connector.get_definition()
    evidence_store.add_event(
        "connector_configured",
        {"connector_id": connector_id, "mode": defn.mode.value},
        source_mode=defn.mode.value,
    )
    return {
        "connector_id": connector_id,
        "name": defn.name,
        "status": "configured",
        "mode": defn.mode.value,
        "message": f"Mode updated to '{defn.mode.value}'.",
    }


@app.post("/api/connectors/{connector_id}/test", tags=["Connectors"], summary="Test connector health")
def test_connector(connector_id: str) -> Dict[str, Any]:
    """Run a health check against the connector."""
    connector = _get_connector(connector_id)
    health = connector.get_health()
    evidence_store.add_event(
        "connector_health_check",
        {"connector_id": connector_id, "health": health},
        source_mode=connector.get_definition().mode.value,
    )
    return {"connector_id": connector_id, "health": health}


@app.post("/api/connectors/{connector_id}/enable", tags=["Connectors"], summary="Enable connector")
def enable_connector(connector_id: str) -> Dict[str, Any]:
    """Mark a connector as enabled.  In mock mode this is a no-op."""
    connector = _get_connector(connector_id)
    defn = connector.get_definition()
    evidence_store.add_event(
        "connector_enabled", {"connector_id": connector_id},
        source_mode=defn.mode.value,
    )
    return {"connector_id": connector_id, "enabled": True}


@app.post("/api/connectors/{connector_id}/disable", tags=["Connectors"], summary="Disable connector")
def disable_connector(connector_id: str) -> Dict[str, Any]:
    """Mark a connector as disabled.  In mock mode this is a no-op."""
    connector = _get_connector(connector_id)
    defn = connector.get_definition()
    evidence_store.add_event(
        "connector_disabled", {"connector_id": connector_id},
        source_mode=defn.mode.value,
    )
    return {"connector_id": connector_id, "enabled": False}


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@app.get("/api/tools", tags=["Tools"], summary="List all enabled tools")
def list_tools(platform_id: Optional[str] = Query(default=None)) -> List[Dict[str, Any]]:
    """Return all enabled tools, optionally filtered by platform_id."""
    tools = registry.list_tools(platform_id=platform_id)
    return [
        {
            "id": t.id,
            "connector_id": t.connector_id,
            "platform_id": t.platform_id,
            "name": t.name,
            "description": t.description,
            "signal_types": t.signal_types_returned,
            "enabled": t.enabled,
            "source_mode": t.source_mode.value,
        }
        for t in tools
    ]


# ---------------------------------------------------------------------------
# KPI Agent
# ---------------------------------------------------------------------------


@app.post("/api/kpi-agent/interpret", tags=["KPI Agent"], summary="Run KPI Agent for a persona")
def interpret_kpi(body: KPIInterpretRequest) -> Dict[str, Any]:
    """Interpret a KPI for a persona and return a full control plane response.

    If ``kpi`` is omitted the persona's default KPI is used.
    If ``kpi`` is vague (e.g. "Improve compliance.") the response will
    include ``clarification_questions`` and ``maturity_level: "vague"``.
    """
    result = kpi_agent.run(
        persona_id=body.persona_id,
        kpi=body.kpi,
        mode=body.mode or "mock",
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/api/kpi-agent/challenge", tags=["KPI Agent"], summary="Challenge a draft KPI")
def challenge_kpi(body: KPIChallengeRequest) -> Dict[str, Any]:
    """Challenge a draft KPI with persona-specific governance questions.

    Returns a KpiChallengeSession including:
    - maturity assessment
    - missing fields
    - persona-specific challenge questions
    - suggested formalized KPI
    - confidence score

    The persona must be selected before calling this endpoint.
    Only call /api/kpi-agent/control-package after formalization.
    """
    if body.persona_id not in PERSONA_CATALOGUE:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{body.persona_id}' not found.",
        )
    session = kpi_challenge_agent.challenge(
        persona_id=body.persona_id,
        draft_kpi=body.draft_kpi,
    )
    return session.to_dict()


@app.post("/api/kpi-agent/formalize", tags=["KPI Agent"], summary="Formalize a KPI from challenge answers")
def formalize_kpi(body: KPIFormalizeRequest) -> Dict[str, Any]:
    """Accept challenge answers and produce a FormalizedKpi.

    Returns:
    - formalized_kpi: the governance-grade KPI record
    - maturity_level: updated after incorporating answers
    - confidence_score
    - remaining_questions: any questions still unanswered

    The FormalizedKpi is required as input to /api/kpi-agent/control-package.
    """
    if body.persona_id not in PERSONA_CATALOGUE:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{body.persona_id}' not found.",
        )
    return kpi_challenge_agent.formalize(
        session_id=body.session_id,
        persona_id=body.persona_id,
        draft_kpi=body.draft_kpi,
        answers=body.answers,
    )


@app.post("/api/kpi-agent/control-package", tags=["KPI Agent"], summary="Compose a Control Package from a formalized KPI")
def compose_control_package(body: KPIControlPackageRequest) -> Dict[str, Any]:
    """Compose a Control Package from a FormalizedKpi.

    Orchestrates KPIAgent + ToolRegistry + AccessReadinessAgent.
    Returns a structured ControlPackage with:
    - what_you_get: control-plane outputs the persona will receive
    - what_you_need: signals, connectors, tools, access and evidence required
    - access_readiness_summary
    - connector_readiness_summary
    - recommended_actions
    - agent_ideas
    - evidence trail events

    This endpoint must only be called after /api/kpi-agent/formalize.
    """
    if body.persona_id not in PERSONA_CATALOGUE:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{body.persona_id}' not found.",
        )
    return control_composition_agent.compose(
        persona_id=body.persona_id,
        formalized_kpi=body.formalized_kpi,
        mode=body.mode or "mock",
    )


# ---------------------------------------------------------------------------
# Agent Requests
# ---------------------------------------------------------------------------


@app.get("/api/agent-requests", tags=["Agent Requests"], summary="List all agent requests")
def list_agent_requests() -> List[Dict[str, Any]]:
    """Return all submitted agent build requests."""
    return [r.to_dict() for r in request_store.list()]


@app.post("/api/agent-requests", tags=["Agent Requests"], summary="Submit an agent request")
def create_agent_request(body: AgentRequestCreate) -> Dict[str, Any]:
    """Submit a request to build an agent from an agent idea.

    Every submission writes an evidence event so the governance trail
    captures the intent.
    """
    request = AgentRequest(
        id=str(uuid.uuid4()),
        agent_idea_id=body.agent_idea_id,
        requested_by_persona=body.requested_by_persona,
        linked_kpi_id=body.linked_kpi_id,
        status=AgentReqStatus.SUBMITTED,
        rationale=body.rationale,
    )
    request_store.add(request)
    evidence_store.add_event(
        "agent_request_submitted",
        {
            "request_id": request.id,
            "agent_idea_id": body.agent_idea_id,
            "rationale": body.rationale,
        },
        persona_id=body.requested_by_persona,
        kpi_id=body.linked_kpi_id,
    )
    return request.to_dict()


# ---------------------------------------------------------------------------
# Evidence Trail
# ---------------------------------------------------------------------------


@app.get("/api/evidence", tags=["Evidence"], summary="Query evidence trail")
def get_evidence(
    persona_id: Optional[str] = Query(default=None),
    kpi_id: Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    """Return evidence events, optionally filtered by persona_id or kpi_id."""
    events = evidence_store.list(persona_id=persona_id, kpi_id=kpi_id)
    return [e.to_dict() for e in events]


# ---------------------------------------------------------------------------
# Access Readiness
# ---------------------------------------------------------------------------


class AccessCheckRequest(BaseModel):
    persona_id: str
    kpi_agent_result: Dict[str, Any]
    mode: Optional[str] = "mock"


class AccessRequestCreate(BaseModel):
    persona_id: str
    kpi_id: str
    connector_id: str
    platform_id: str
    requested_scope: str
    requested_role: str
    requested_permission: str
    requested_actions: List[str]
    justification: str
    business_outcome: str
    recommended_approver: str


@app.get(
    "/api/access/personas/{persona_id}/grants",
    tags=["Access Readiness"],
    summary="Current access grants for a persona",
)
def get_access_grants(persona_id: str) -> List[Dict[str, Any]]:
    """Return mock access grants for a persona.

    In live mode these would be fetched from Microsoft Entra ID / RBAC.
    In mock mode they reflect the deterministic grants defined in the
    Access Readiness Agent.
    """
    if persona_id not in PERSONA_CATALOGUE:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{persona_id}' not found.",
        )
    return access_agent.get_grants(persona_id)


@app.post(
    "/api/access/check",
    tags=["Access Readiness"],
    summary="Run access readiness check for a persona + KPI Agent result",
)
def check_access(body: AccessCheckRequest) -> Dict[str, Any]:
    """Determine whether the persona has the access required by their KPI.

    Input: persona_id + the KPI Agent result (required_signals, selected_platforms,
    available_tools_used).

    Output: overall_status, access_check_results, access_gaps,
    recommended_access_requests, evidence_events.

    No access is auto-granted. The response contains only assessments and
    least-privilege request recommendations.
    """
    if body.persona_id not in PERSONA_CATALOGUE:
        raise HTTPException(
            status_code=404,
            detail=f"Persona '{body.persona_id}' not found.",
        )
    return access_agent.check(
        persona_id=body.persona_id,
        kpi_agent_result=body.kpi_agent_result,
        mode=body.mode or "mock",
    )


@app.post(
    "/api/access/requests",
    tags=["Access Readiness"],
    summary="Submit an access request",
)
def create_access_request(body: AccessRequestCreate) -> Dict[str, Any]:
    """Submit an access request for a persona.

    Creates the request with status 'submitted' and writes an evidence event.
    No access is granted — this is a request for human approval.
    """
    req = AccessReq(
        id=str(uuid.uuid4()),
        persona_id=body.persona_id,
        kpi_id=body.kpi_id,
        connector_id=body.connector_id,
        platform_id=body.platform_id,
        requested_scope=body.requested_scope,
        requested_role=body.requested_role,
        requested_permission=body.requested_permission,
        requested_actions=body.requested_actions,
        justification=body.justification,
        business_outcome=body.business_outcome,
        status=AccessRequestStatus.SUBMITTED,
        recommended_approver=body.recommended_approver,
    )
    _access_requests.append(req.to_dict())
    evidence_store.add_event(
        "access_request_submitted",
        {
            "request_id": req.id,
            "connector_id": body.connector_id,
            "requested_scope": body.requested_scope,
            "justification": body.justification,
        },
        persona_id=body.persona_id,
        kpi_id=body.kpi_id,
    )
    return req.to_dict()


@app.get(
    "/api/access/requests",
    tags=["Access Readiness"],
    summary="List all access requests",
)
def list_access_requests() -> List[Dict[str, Any]]:
    """Return all submitted access requests."""
    return list(_access_requests)
