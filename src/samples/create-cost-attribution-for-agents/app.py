from __future__ import annotations

from pathlib import Path
from dataclasses import asdict
from datetime import datetime
from typing import List

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import jinja2

from loaders import load_cost_rows, load_runtime_events, load_value_entries
from classify_costs import classify_costs
from allocate_costs import allocate_costs, build_agent_economics_summary
from ledger_store import CostLedgerStore
import csv
import io


BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app = FastAPI(title="Cost Attribution for Accountable Agents")
# Ensure Jinja2 template cache is a plain dict and clear it to avoid
# unhashable-key issues when rendering with dynamic contexts in tests.
try:
    templates.env.cache = {}
except Exception:
    pass

# Mount static directory for CSS and assets
static_dir = BASE / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _load_rules() -> dict:
    path = BASE / "allocation_rules.yaml"
    if path.exists():
        try:
            import yaml

            with open(path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return data
        except Exception:
            return {}
    return {}


def _build_pipeline() -> dict:
    costs = load_cost_rows(BASE / "data" / "azure-cost-export-sample.csv")
    events = load_runtime_events(BASE / "data" / "agent-runtime-events.json")
    values = load_value_entries(BASE / "data" / "value-ledger-sample.json")
    rules = _load_rules()

    groups = classify_costs(costs)
    allocations = allocate_costs(costs, events, rules)

    ledger_store = CostLedgerStore()
    for e in allocations:
        ledger_store.append(e)
    cost_entries = ledger_store.list_entries()
    summaries = build_agent_economics_summary(cost_entries, values, events, rules)

    # convert summaries to dicts and augment with currency symbol
    def symbol_for(code: str) -> str:
        if not code:
            return ""
        mapping = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}
        return mapping.get(code.upper(), code + " ")

    summaries_dicts = []
    for s in summaries:
        d = asdict(s)
        d["currency_symbol"] = symbol_for(d.get("currency", ""))
        summaries_dicts.append(d)

    # Reporting context: determine selected period, currency, granularity and source
    months = sorted({(r.date[:7] if r.date else "") for r in costs})
    months = [m for m in months if m]
    period_rule = rules.get("period")
    if period_rule:
        selected_period = period_rule
        filtered_costs = [r for r in costs if (r.date or "").startswith(selected_period)]
        filtered_entries = [e for e in cost_entries if getattr(e, "period", "") == selected_period]
    else:
        if len(months) == 1:
            selected_period = months[0]
            filtered_costs = [r for r in costs if (r.date or "").startswith(selected_period)]
            filtered_entries = [e for e in cost_entries if getattr(e, "period", "") == selected_period]
        elif len(months) > 1:
            selected_period = f"{months[0]} - {months[-1]}"
            filtered_costs = costs
            filtered_entries = cost_entries
        else:
            selected_period = ""
            filtered_costs = costs
            filtered_entries = cost_entries

    total_source_cost = sum(float(r.cost_amount or 0.0) for r in filtered_costs)
    total_input_cost = sum(float(getattr(e, "allocated_cost_amount", 0.0) or 0.0) for e in filtered_entries)
    unallocated_visible_cost = sum(float(getattr(e, "allocated_cost_amount", 0.0) or 0.0) for e in filtered_entries if not getattr(e, "agent_id", None))
    attributed_agent_cost = total_input_cost - unallocated_visible_cost
    allocation_coverage_portfolio = (attributed_agent_cost / total_source_cost) if total_source_cost > 0 else 0.0

    # Determine currency for display
    currency = ""
    for d in summaries_dicts:
        if d.get("currency"):
            currency = d["currency"]
            break
    if not currency and filtered_costs:
        currency = filtered_costs[0].currency or ""

    reporting_context = {
        "reporting_period": selected_period,
        "cost_source": rules.get("source") or "demo CSV",
        "currency": currency,
        "currency_symbol": symbol_for(currency),
        "granularity": "monthly" if len(months) <= 1 else "multi-month",
        "cost_basis": "actual cost",
        "generated": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }

    # Augment summaries with presentation-friendly fields
    for d in summaries_dicts:
        alloc_frac = float(d.get("allocation_coverage_percentage", 0.0) or 0.0)
        d["allocation_share"] = alloc_frac
        d["allocation_share_percent"] = round(alloc_frac * 100.0, 1)
        ctr = float(d.get("cost_to_value_ratio", 0.0) or 0.0)
        d["cost_to_value_percent"] = round(ctr * 100.0, 2)
        d["cost_per_value_unit"] = ctr
        tac = float(d.get("total_attributed_cost", 0.0) or 0.0)
        tav = float(d.get("total_attributed_value", 0.0) or 0.0)
        if tac > 0:
            d["attributed_value_multiple"] = round((tav / tac), 1)
        else:
            d["attributed_value_multiple"] = None
        d["reporting_period"] = reporting_context["reporting_period"]

    return {
        "costs": costs,
        "events": events,
        "values": values,
        "groups": groups,
        "cost_entries": cost_entries,
        "summaries": summaries_dicts,
        "rules": rules,
        "reporting_context": reporting_context,
        "total_source_cost": total_source_cost,
        "attributed_agent_cost": attributed_agent_cost,
        "unallocated_visible_cost": unallocated_visible_cost,
        "allocation_coverage_portfolio": allocation_coverage_portfolio,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        data = _build_pipeline()
    except Exception as exc:
        return HTMLResponse(f"<h1>Unable to build sample pipeline</h1><pre>{exc}</pre>", status_code=500)

    # compute totals
    def _sum(rows: List) -> float:
        return sum(getattr(r, "cost_amount", getattr(r, "allocated_cost_amount", 0.0)) or 0.0 for r in rows)

    totals = {
        "direct": _sum(data["groups"]["direct"]),
        "indirect": _sum(data["groups"]["indirect"]),
        "platform": _sum(data["groups"]["platform"]),
        "unallocated": _sum(data["groups"]["unallocated"]),
    }

    # Render template without relying on Starlette's TemplateResponse cache keys,
    # which can raise on unhashable context items in some Jinja2 versions.
    try:
        context = {
            "concepts": [
                "Value attribution tells us what the agent contributed.",
                "Cost attribution tells us what it took to create that contribution.",
                "Accountable Agents need both.",
            ],
            "pipeline_text": [
                "Azure Cost Data",
                "+ Azure Tags",
                "+ Agent Runtime Events",
                "+ Distribution Keys",
                "→ Cost Ledger",
                "→ Agent Economics Summary",
            ],
            "totals": totals,
            "summaries": data["summaries"],
            "cost_entries": [asdict(e) for e in data["cost_entries"]],
            "source_costs": [asdict(c) for c in data["costs"]],
            "unallocated_visible": data.get("unallocated_visible_cost", totals["unallocated"]),
            "reporting_context": data.get("reporting_context", {}),
            "total_source_cost": data.get("total_source_cost", 0.0),
            "attributed_agent_cost": data.get("attributed_agent_cost", 0.0),
            "allocation_coverage_portfolio": data.get("allocation_coverage_portfolio", 0.0),
        }

        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(BASE / "templates")),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            cache_size=0,
        )
        template = env.get_template("index.html")
        html = template.render(context)
        return HTMLResponse(html)
    except Exception as exc:
        return HTMLResponse(f"<h1>Template rendering error</h1><pre>{exc}</pre>", status_code=500)


@app.get("/api/economics")
async def api_economics():
    try:
        data = _build_pipeline()
        return JSONResponse(data["summaries"])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/cost-ledger")
async def api_cost_ledger():
    try:
        data = _build_pipeline()
        return JSONResponse([asdict(e) for e in data["cost_entries"]])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/source-costs")
async def api_source_costs():
    try:
        data = _build_pipeline()
        return JSONResponse([asdict(c) for c in data["costs"]])
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


def _dicts_to_csv_bytes(dicts: list[dict]) -> bytes:
    if not dicts:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(dicts[0].keys()))
    writer.writeheader()
    for d in dicts:
        writer.writerow(d)
    return output.getvalue().encode("utf-8")


@app.get("/api/economics.csv")
async def api_economics_csv():
    try:
        data = _build_pipeline()
        csv_bytes = _dicts_to_csv_bytes(data["summaries"])
        return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=agent_economics.csv"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/cost-ledger.csv")
async def api_cost_ledger_csv():
    try:
        data = _build_pipeline()
        dicts = [asdict(e) for e in data["cost_entries"]]
        csv_bytes = _dicts_to_csv_bytes(dicts)
        return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=cost_ledger.csv"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/source-costs.csv")
async def api_source_costs_csv():
    try:
        data = _build_pipeline()
        dicts = [asdict(c) for c in data["costs"]]
        csv_bytes = _dicts_to_csv_bytes(dicts)
        return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=source_costs.csv"})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
