"""Mock CRM/ERP tools the outcome-aware agent can call.

Each tool follows the same pattern:

1. Declares a JSON schema (used to register it with Azure AI Foundry as a
   ``FunctionTool``).
2. Has a Python implementation that:

   * emits a *start* and *end* activity event on the shared :data:`event_bus.bus`,
     so the UI can render a live feed of "what the agent is doing right now",
   * appends a :class:`ValueEntry` to the supplied :class:`ValueLedger` so the
     business outcome is captured the moment value materializes,
   * returns a plausible JSON-serializable result the model can reason over.

The tools deliberately do **not** call any real CRM/ERP system — they return
hard-coded but realistic-looking responses. The point of the lab is the
*value-attribution mechanic*; swapping these for real Salesforce/SAP/Dynamics
calls is left as an exercise.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, TYPE_CHECKING

from event_bus import bus

if TYPE_CHECKING:  # pragma: no cover
    from agent import ValueLedger


# ---------------------------------------------------------------------------
# Tool schemas (registered with Foundry)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "create_crm_lead",
        "description": (
            "Create a new sales lead in the CRM (Salesforce-style). "
            "Use when the user describes a prospective customer or wants to "
            "open a new opportunity."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company": {"type": "string", "description": "Prospect company name."},
                "contact_name": {"type": "string", "description": "Primary contact at the prospect."},
                "estimated_value_usd": {
                    "type": "number",
                    "description": "Best-guess deal size in USD.",
                },
                "source": {
                    "type": "string",
                    "description": "Lead source (e.g. 'inbound email', 'event', 'referral').",
                },
            },
            "required": ["company", "contact_name", "estimated_value_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_erp_invoice",
        "description": (
            "Issue an invoice in the ERP (SAP/Dynamics-style) for an existing "
            "customer. Use when a deal is closed-won and revenue should be "
            "recognized."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "customer": {"type": "string"},
                "amount_usd": {"type": "number"},
                "due_in_days": {"type": "integer", "default": 30},
                "memo": {"type": "string"},
            },
            "required": ["customer", "amount_usd"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_inventory_level",
        "description": (
            "Adjust the on-hand inventory for a SKU in the ERP. Positive "
            "delta_units = restock, negative = consumption. Use for stock "
            "rebalancing or month-end true-ups."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Stock-keeping unit identifier."},
                "delta_units": {"type": "integer"},
                "warehouse": {"type": "string", "default": "DC-01"},
            },
            "required": ["sku", "delta_units"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_finance_report",
        "description": (
            "Generate a finance report (monthly close, weekly flash, etc.) "
            "and file it in the document management system."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "description": "Period to report on, e.g. '2026-04', 'Q2-2026', 'week of 2026-05-05'.",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["monthly_close", "weekly_flash", "ad_hoc"],
                    "default": "monthly_close",
                },
            },
            "required": ["period"],
            "additionalProperties": False,
        },
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _publish(event_type: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {
        "type": event_type,
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(fields)
    await bus.publish(payload)


def _short_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


async def _create_crm_lead(args: Dict[str, Any], ledger: "ValueLedger") -> Dict[str, Any]:
    company = args.get("company", "Unknown Co")
    contact = args.get("contact_name", "Unknown")
    value = float(args.get("estimated_value_usd", 0))
    source = args.get("source", "inbound")

    await _publish(
        "tool_call_start",
        tool="create_crm_lead",
        icon="👤",
        label=f"Creating lead '{company}' ({contact}) in CRM…",
    )
    await asyncio.sleep(0.6)  # mimic an API hop

    lead_id = _short_id("LEAD")
    result = {
        "lead_id": lead_id,
        "company": company,
        "contact": contact,
        "estimated_value_usd": value,
        "stage": "Qualifying",
        "source": source,
    }

    ledger.add_entry(
        task_description="CRM Lead Creation",
        hours_saved=1.5,
        materialized_value=(
            f"Lead {lead_id} for {company} (~${value:,.0f}) opened in CRM"
        ),
        agent_action=f"create_crm_lead(company={company!r}, value={value})",
    )
    await _publish(
        "tool_call_end",
        tool="create_crm_lead",
        icon="✅",
        label=f"Lead {lead_id} created — pipeline +${value:,.0f}",
        result=result,
    )
    return result


async def _create_erp_invoice(args: Dict[str, Any], ledger: "ValueLedger") -> Dict[str, Any]:
    customer = args.get("customer", "Unknown Customer")
    amount = float(args.get("amount_usd", 0))
    due = int(args.get("due_in_days", 30))
    memo = args.get("memo", "")

    await _publish(
        "tool_call_start",
        tool="create_erp_invoice",
        icon="🧾",
        label=f"Issuing invoice to {customer} for ${amount:,.0f}…",
    )
    await asyncio.sleep(0.5)

    invoice_id = _short_id("INV")
    result = {
        "invoice_id": invoice_id,
        "customer": customer,
        "amount_usd": amount,
        "due_in_days": due,
        "status": "Sent",
        "memo": memo,
    }

    ledger.add_entry(
        task_description="ERP Invoice Issued",
        hours_saved=2.0,
        materialized_value=f"Invoice {invoice_id} sent to {customer} for ${amount:,.0f}",
        agent_action=f"create_erp_invoice(customer={customer!r}, amount={amount})",
    )
    await _publish(
        "tool_call_end",
        tool="create_erp_invoice",
        icon="💰",
        label=f"Invoice {invoice_id} issued — ${amount:,.0f} recognized",
        result=result,
    )
    return result


async def _update_inventory_level(args: Dict[str, Any], ledger: "ValueLedger") -> Dict[str, Any]:
    sku = args.get("sku", "SKU-UNKNOWN")
    delta = int(args.get("delta_units", 0))
    warehouse = args.get("warehouse", "DC-01")

    await _publish(
        "tool_call_start",
        tool="update_inventory_level",
        icon="📦",
        label=f"Adjusting {sku} by {delta:+d} units in {warehouse}…",
    )
    await asyncio.sleep(0.4)

    new_qty = max(0, random.randint(50, 500) + delta)
    result = {
        "sku": sku,
        "warehouse": warehouse,
        "delta_units": delta,
        "on_hand_after": new_qty,
    }

    ledger.add_entry(
        task_description="ERP Inventory Adjustment",
        hours_saved=0.75,
        materialized_value=f"{sku} rebalanced ({delta:+d}) — on-hand now {new_qty}",
        agent_action=f"update_inventory_level(sku={sku!r}, delta={delta})",
    )
    await _publish(
        "tool_call_end",
        tool="update_inventory_level",
        icon="✅",
        label=f"{sku} updated — on-hand {new_qty}",
        result=result,
    )
    return result


async def _generate_finance_report(args: Dict[str, Any], ledger: "ValueLedger") -> Dict[str, Any]:
    period = args.get("period", "current")
    report_type = args.get("report_type", "monthly_close")

    await _publish(
        "tool_call_start",
        tool="generate_finance_report",
        icon="📊",
        label=f"Generating {report_type.replace('_', ' ')} for {period}…",
    )
    await asyncio.sleep(0.8)

    report_id = _short_id("RPT")
    result = {
        "report_id": report_id,
        "period": period,
        "report_type": report_type,
        "url": f"https://docs.contoso.example/reports/{report_id}.pdf",
        "kpis": {
            "revenue_usd": round(random.uniform(800_000, 1_400_000), 2),
            "gross_margin_pct": round(random.uniform(38, 52), 1),
        },
    }

    ledger.add_entry(
        task_description="Finance Report Generation",
        hours_saved=4.0,
        materialized_value=f"{report_type.replace('_', ' ').title()} for {period} filed ({report_id})",
        agent_action=f"generate_finance_report(period={period!r})",
    )
    await _publish(
        "tool_call_end",
        tool="generate_finance_report",
        icon="📄",
        label=f"Report {report_id} filed for {period}",
        result=result,
    )
    return result


TOOL_IMPLS: Dict[str, Callable[[Dict[str, Any], "ValueLedger"], Awaitable[Dict[str, Any]]]] = {
    "create_crm_lead": _create_crm_lead,
    "create_erp_invoice": _create_erp_invoice,
    "update_inventory_level": _update_inventory_level,
    "generate_finance_report": _generate_finance_report,
}


async def dispatch(name: str, raw_args: Any, ledger: "ValueLedger") -> str:
    """Execute a tool by name. Returns a JSON string for the model."""
    impl = TOOL_IMPLS.get(name)
    if impl is None:
        return json.dumps({"error": f"unknown tool {name}"})

    if isinstance(raw_args, str):
        try:
            args = json.loads(raw_args)
        except json.JSONDecodeError:
            args = {}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        args = {}

    try:
        result = await impl(args, ledger)
        return json.dumps(result)
    except Exception as exc:  # pragma: no cover - surface to the model
        return json.dumps({"error": str(exc)})


AGENT_INSTRUCTIONS = """\
You are an outcome-aware operations agent for a fictional company "Contoso".
You help business stakeholders move work forward by calling the available
CRM and ERP tools. Always:

* Pick the smallest set of tools that satisfies the user's intent.
* Invoke tools when concrete business work needs to happen — do not just
  describe what *should* be done.
* When the user describes a closed-won deal, both create the lead and issue
  the invoice.
* When the user asks for a month-end close, generate the finance report
  and adjust any obviously stale inventory items they mention.
* After the tool calls complete, summarize what was done in 2-3 sentences,
  including the IDs returned by the tools so the user can audit the work.

Do not ask clarifying questions for trivial defaults — make a reasonable
assumption and proceed.
"""
