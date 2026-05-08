"""Outcome-aware agent.

This module exposes two things:

* ``ValueLedger`` / ``OutcomeAwareAgent`` -- the lightweight, *offline* demo
  used by ``outcome-aware-agent-example.py`` and the smoke tests. No LLM, no
  Azure dependency.

* ``FoundryOutcomeAgent`` -- a *real* agent backed by Microsoft Foundry
  (``AIProjectClient`` + the Responses API). It wires the four mock CRM/ERP
  function tools defined in :mod:`tools`, dispatches them locally, and
  pipes every step through the shared event bus so the FastAPI UI can show
  a live activity feed.

The Foundry agent is created lazily inside an ``async with`` context so the
underlying Azure clients are properly closed at process shutdown.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import AsyncExitStack
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from ledger_store import InMemoryLedgerStore, LedgerStore, ValueEntry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ValueLedger / OutcomeAwareAgent (offline demo, kept for backward compat)
# ---------------------------------------------------------------------------


class ValueLedger:
    """Manages the ledger of value attribution.

    Storage is delegated to a pluggable ``LedgerStore`` so the same code can
    run against an in-memory list (local demo) or Azure Confidential Ledger
    (tamper-evident, durable persistence).
    """

    def __init__(self, store: Optional[LedgerStore] = None) -> None:
        self.store: LedgerStore = store or InMemoryLedgerStore()

    @property
    def entries(self):
        return self.store.list_entries()

    def add_entry(
        self,
        task_description: str,
        hours_saved: float,
        materialized_value: str,
        agent_action: str,
    ) -> None:
        entry = ValueEntry(
            timestamp=datetime.now().isoformat(),
            task_description=task_description,
            hours_saved=hours_saved,
            materialized_value=materialized_value,
            agent_action=agent_action,
        )
        self.store.append(entry)

    def get_summary(self) -> Dict[str, Any]:
        entries = self.store.list_entries()
        total_hours_saved = sum(entry.hours_saved for entry in entries)
        return {
            "total_entries": len(entries),
            "total_hours_saved": total_hours_saved,
            "entries": [asdict(entry) for entry in entries],
        }

    def print_ledger(self) -> None:
        print("\n" + "=" * 80)
        print("VALUE ATTRIBUTION LEDGER")
        print("=" * 80)
        for i, entry in enumerate(self.entries, 1):
            print(f"\nEntry {i}:")
            print(f"  Timestamp: {entry.timestamp}")
            print(f"  Task: {entry.task_description}")
            print(f"  Agent Action: {entry.agent_action}")
            print(f"  Hours Saved: {entry.hours_saved}")
            print(f"  Materialized Value: {entry.materialized_value}")

        summary = self.get_summary()
        print(f"\n{'-' * 80}")
        print(f"SUMMARY - Total Hours Saved: {summary['total_hours_saved']}")
        print("=" * 80 + "\n")


class OutcomeAwareAgent:
    """Simple offline agent that records hard-coded value entries.

    Kept for the pure-Python intro demo (``outcome-aware-agent-example.py``)
    so the lab is runnable without Azure credentials.
    """

    def __init__(self, ledger: Optional[ValueLedger] = None) -> None:
        self.ledger = ledger or ValueLedger()

    def process_customer_inquiry(self, inquiry: str) -> None:
        self.ledger.add_entry(
            task_description="Customer Inquiry Processing",
            hours_saved=2.5,
            materialized_value="Won a new customer contract",
            agent_action=f"Processed inquiry: {inquiry}",
        )

    def automate_report_generation(self, report_type: str) -> None:
        self.ledger.add_entry(
            task_description="Report Generation Automation",
            hours_saved=4.0,
            materialized_value="Improved reporting accuracy by 30%",
            agent_action=f"Generated automated {report_type} report",
        )

    def optimize_resource_allocation(self, resource_type: str) -> None:
        self.ledger.add_entry(
            task_description="Resource Allocation Optimization",
            hours_saved=1.5,
            materialized_value="Hired 2 new talents with optimized budget",
            agent_action=f"Optimized allocation of {resource_type}",
        )

    def run_tasks(self) -> None:
        self.process_customer_inquiry("Product pricing question")
        self.automate_report_generation("monthly sales")
        self.optimize_resource_allocation("engineering team budget")

    def get_value_report(self) -> Dict[str, Any]:
        return self.ledger.get_summary()


# ---------------------------------------------------------------------------
# Foundry-backed agent
# ---------------------------------------------------------------------------


class FoundryOutcomeAgent:
    """Outcome-aware agent powered by Microsoft Foundry.

    Reads connection details from the workshop env (``PROJECT_ENDPOINT``,
    ``AGENT_MODEL_DEPLOYMENT_NAME``). On ``start()`` it registers an agent
    version with the four CRM/ERP function tools from :mod:`tools`. On
    ``chat()`` it runs an agentic Responses-API loop, dispatching tool calls
    locally (which writes ledger entries and emits live UI events).
    """

    def __init__(self, ledger: ValueLedger) -> None:
        self.ledger = ledger
        self.endpoint = os.environ.get("PROJECT_ENDPOINT")
        self.model = os.environ.get("AGENT_MODEL_DEPLOYMENT_NAME")
        self._stack: Optional[AsyncExitStack] = None
        self._project_client = None
        self._openai_client = None
        self._agent = None
        self._agent_name = "OutcomeAwareAgent"

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.model)

    async def start(self) -> None:
        if not self.is_configured:
            raise RuntimeError(
                "FoundryOutcomeAgent requires PROJECT_ENDPOINT and "
                "AGENT_MODEL_DEPLOYMENT_NAME in src/workshop/.env."
            )

        # Imports are local so the lab still imports cleanly without the SDK.
        from azure.ai.projects import AIProjectClient
        from azure.ai.projects.models import FunctionTool, PromptAgentDefinition
        from azure.identity import DefaultAzureCredential

        from tools import AGENT_INSTRUCTIONS, TOOL_SCHEMAS

        self._stack = AsyncExitStack()
        credential = self._stack.enter_context(DefaultAzureCredential())
        self._project_client = self._stack.enter_context(
            AIProjectClient(endpoint=self.endpoint, credential=credential)
        )
        self._openai_client = self._stack.enter_context(
            self._project_client.get_openai_client()
        )

        function_tools = [
            FunctionTool(
                name=schema["name"],
                description=schema["description"],
                parameters=schema["parameters"],
                strict=False,
            )
            for schema in TOOL_SCHEMAS
        ]

        self._agent = self._project_client.agents.create_version(
            agent_name=self._agent_name,
            definition=PromptAgentDefinition(
                model=self.model,
                instructions=AGENT_INSTRUCTIONS,
                tools=function_tools,
                temperature=0.2,
            ),
        )
        logger.info(
            "Created Foundry agent %s (version %s)",
            self._agent.name,
            self._agent.version,
        )

    async def stop(self) -> None:
        # Best-effort cleanup of agent versions, then close clients.
        try:
            if self._agent and self._project_client is not None:
                versions = self._project_client.agents.list_versions(
                    agent_name=self._agent.name
                )
                for version in versions:
                    try:
                        self._project_client.agents.delete_version(
                            agent_name=self._agent.name,
                            agent_version=version.version,
                        )
                    except Exception:  # noqa: BLE001
                        continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("Agent cleanup encountered: %s", exc)
        finally:
            if self._stack is not None:
                await self._stack.aclose()
                self._stack = None

    async def chat(self, user_message: str) -> str:
        """Run one user turn against the agent. Returns the assistant text.

        Tool calls are dispatched locally; each emits start/end events on the
        shared event bus so the UI can render them in real time, and writes a
        ``ValueEntry`` to the ledger.
        """
        if self._agent is None or self._openai_client is None:
            raise RuntimeError("FoundryOutcomeAgent.start() has not been called.")

        from event_bus import bus
        from tools import dispatch

        await bus.publish(
            {
                "type": "user_message",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "label": user_message,
            }
        )

        agent_ref = {
            "agent_reference": {
                "type": "agent_reference",
                "name": self._agent.name,
                "version": self._agent.version,
            }
        }

        response = self._openai_client.responses.create(
            model=self.model,
            input=[{"role": "user", "content": user_message}],
            extra_body=agent_ref,
        )

        # Agentic loop: keep submitting tool outputs until the agent stops
        # asking for more function calls.
        while True:
            function_outputs: List[Dict[str, Any]] = []
            for item in response.output:
                if getattr(item, "type", None) == "function_call":
                    name = item.name
                    args = item.arguments
                    result_json = await dispatch(name, args, self.ledger)
                    function_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": item.call_id,
                            "output": result_json,
                        }
                    )

            if not function_outputs:
                break

            response = self._openai_client.responses.create(
                model=self.model,
                previous_response_id=response.id,
                input=function_outputs,
                extra_body=agent_ref,
            )

        # Collect the final assistant text.
        assistant_text_parts: List[str] = []
        for item in response.output:
            if getattr(item, "type", None) == "message":
                for content_item in (item.content or []):
                    text = getattr(content_item, "text", None)
                    if isinstance(text, str):
                        assistant_text_parts.append(text)
                    elif text is not None and hasattr(text, "value"):
                        assistant_text_parts.append(text.value)

        assistant_text = "\n".join(t for t in assistant_text_parts if t).strip()
        if not assistant_text:
            assistant_text = "(no response)"

        await bus.publish(
            {
                "type": "assistant_message",
                "ts": datetime.now().isoformat(timespec="seconds"),
                "label": assistant_text,
            }
        )
        return assistant_text
