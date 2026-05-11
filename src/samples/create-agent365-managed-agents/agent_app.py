"""Pro-code Microsoft Foundry agent used by the Agent 365 lab.

Keeps the agent definition + tool implementations out of the notebook so the
notebook can stay focused on the *flow* (register → build → bind → publish →
govern). Imported from
``lab-create-agent365-managed-foundry-agent.ipynb``.

Two function tools are registered with the agent:

* ``lookup_policy`` -- returns a canned HR/IT policy snippet (deterministic,
  used by the tool-allow-list governance test).
* ``summarize_ticket`` -- summarizes a fake support ticket payload (used by
  the DLP governance test -- participants paste a fake credit-card number
  into a ticket body and confirm Purview blocks the response).

Both tools are pure-Python and have no external dependencies, so the lab
remains reproducible inside the workshop devcontainer.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition

logger = logging.getLogger(__name__)

AGENT_NAME = "foundry-lab-agent"
AGENT_DESCRIPTION = (
    "Pro-code Foundry lab agent registered with an Entra Agent ID and "
    "published to Agent 365 for governance."
)
AGENT_INSTRUCTIONS = (
    "You are an internal assistant for Contoso. "
    "Use the `lookup_policy` tool to answer questions about company policies. "
    "Use the `summarize_ticket` tool to produce a one-paragraph summary of a "
    "support ticket. Never invent policy text -- if the tool returns no "
    "match, say so."
)


# ---------------------------------------------------------------------------
# Tool definitions (schema the model sees)
# ---------------------------------------------------------------------------

lookup_policy_tool = FunctionTool(
    name="lookup_policy",
    description="Return the company policy snippet for the given topic.",
    parameters={
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "Policy topic, e.g. 'remote work', 'expenses'.",
            }
        },
        "required": ["topic"],
        "additionalProperties": False,
    },
    strict=True,
)

summarize_ticket_tool = FunctionTool(
    name="summarize_ticket",
    description="Summarize the body of a customer support ticket.",
    parameters={
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "body": {"type": "string"},
        },
        "required": ["ticket_id", "body"],
        "additionalProperties": False,
    },
    strict=True,
)


# ---------------------------------------------------------------------------
# Tool implementations (what the host runs when the model calls a tool)
# ---------------------------------------------------------------------------

_POLICY_SNIPPETS: Dict[str, str] = {
    "remote work": (
        "Employees may work remotely up to 3 days per week with manager approval."
    ),
    "expenses": (
        "Expenses must be submitted within 30 days and require a receipt for "
        "any item over USD 25."
    ),
    "data handling": (
        "Customer PII must never be copied into chat tools, email, or shared "
        "drives outside the approved Purview-labelled containers."
    ),
}


def lookup_policy(topic: str) -> str:
    snippet = _POLICY_SNIPPETS.get(topic.lower().strip())
    return json.dumps({"topic": topic, "snippet": snippet or "NO_MATCH"})


def summarize_ticket(ticket_id: str, body: str) -> str:
    # Deliberately naive -- the lab is about governance, not summarization.
    summary = (body[:160] + "…") if len(body) > 160 else body
    return json.dumps({"ticket_id": ticket_id, "summary": summary})


TOOL_DISPATCH: Dict[str, Callable[..., str]] = {
    "lookup_policy": lookup_policy,
    "summarize_ticket": summarize_ticket,
}


# ---------------------------------------------------------------------------
# Agent build / detect-reuse helper
# ---------------------------------------------------------------------------


@dataclass
class AgentHandle:
    name: str
    version: str
    model: str
    created: bool


def build_or_get_agent(
    project_client: AIProjectClient,
    model_deployment_name: str,
) -> AgentHandle:
    """Detect-and-reuse the ``foundry-lab-agent``.

    The Foundry SDK identifies agents by ``agent_name``. Each call to
    ``create_version`` produces a new immutable ``AgentVersionDetails``. We
    detect the agent by name; if it already exists we reuse the latest
    version, otherwise we create v1. Idempotent so the notebook can be
    re-run safely.
    """

    existing = next(
        (a for a in project_client.agents.list() if a.name == AGENT_NAME),
        None,
    )
    if existing is not None:
        versions = list(project_client.agents.list_versions(agent_name=AGENT_NAME))
        latest = max(versions, key=lambda v: int(v.version)) if versions else None
        if latest is not None:
            logger.info("Reusing %s v%s", AGENT_NAME, latest.version)
            return AgentHandle(
                name=AGENT_NAME,
                version=str(latest.version),
                model=getattr(latest.definition, "model", model_deployment_name),
                created=False,
            )

    definition = PromptAgentDefinition(
        model=model_deployment_name,
        instructions=AGENT_INSTRUCTIONS,
        tools=[lookup_policy_tool, summarize_ticket_tool],
    )
    version = project_client.agents.create_version(
        agent_name=AGENT_NAME,
        definition=definition,
        description=AGENT_DESCRIPTION,
    )
    logger.info("Created %s v%s", AGENT_NAME, version.version)
    return AgentHandle(
        name=AGENT_NAME,
        version=str(version.version),
        model=model_deployment_name,
        created=True,
    )


def agent_reference(handle: AgentHandle) -> Dict[str, Any]:
    """Build the ``extra_body`` payload to route a Responses API call to the
    Foundry-hosted agent identified by ``handle``.
    """
    return {
        "agent_reference": {
            "type": "agent_reference",
            "name": handle.name,
            "version": handle.version,
        }
    }


def dispatch_tool_call(name: str, arguments: str | Dict[str, Any]) -> str:
    """Run a tool call locally and return the JSON string the model expects."""
    args = json.loads(arguments) if isinstance(arguments, str) else arguments
    impl = TOOL_DISPATCH.get(name)
    if impl is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        return impl(**args)
    except Exception as exc:  # surface tool errors to the model
        return json.dumps({"error": str(exc)})


def run_turn(
    openai_client,
    model_deployment_name: str,
    handle: AgentHandle,
    user_input: str,
    tool_filter: Callable[[str], bool] | None = None,
) -> Any:
    """Send a user message to the agent and resolve the function-call loop.

    ``tool_filter`` is an optional predicate ``(tool_name) -> bool``. When it
    returns ``False`` the call is short-circuited locally with a
    ``BlockedByAgent365`` error -- used by the tool-allow-list policy test.

    Returns the final ``responses.create`` response object once the agent
    stops emitting ``function_call`` items.
    """
    extra = agent_reference(handle)
    response = openai_client.responses.create(
        model=model_deployment_name,
        input=[{"role": "user", "content": user_input}],
        extra_body=extra,
    )

    while True:
        outputs = []
        for item in response.output:
            if getattr(item, "type", None) == "function_call":
                if tool_filter is not None and not tool_filter(item.name):
                    result = json.dumps(
                        {"error": f"BlockedByAgent365: {item.name} not in allow-list"}
                    )
                else:
                    result = dispatch_tool_call(item.name, item.arguments)
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": result,
                    }
                )
        if not outputs:
            return response
        response = openai_client.responses.create(
            model=model_deployment_name,
            previous_response_id=response.id,
            input=outputs,
            extra_body=extra,
        )


def final_text(response) -> str:
    """Extract the agent's final assistant text from a Responses API result."""
    chunks = []
    for item in response.output:
        if getattr(item, "type", None) == "message":
            for c in (item.content or []):
                text = getattr(c, "text", None)
                if text:
                    chunks.append(text)
    return "\n".join(chunks)
