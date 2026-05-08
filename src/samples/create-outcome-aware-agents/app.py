"""FastAPI UI for the Outcome-Aware Agent value ledger.

Run locally:
    uvicorn app:app --reload

Switch to Azure Confidential Ledger by setting:
    LEDGER_BACKEND=acl
    ACL_ENDPOINT=https://<name>.confidential-ledger.azure.com
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from agent import OutcomeAwareAgent, ValueLedger
from ledger_store import store_from_env

load_dotenv()
# Workshop-wide .env lives in src/workshop/.env (two directories up).
load_dotenv(Path(__file__).resolve().parents[2] / "workshop" / ".env")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Outcome-Aware Agent — Value Ledger")

_agent = OutcomeAwareAgent(ledger=ValueLedger(store=store_from_env()))

ACTIONS = {
    "customer": lambda: _agent.process_customer_inquiry("Product pricing question"),
    "report": lambda: _agent.automate_report_generation("monthly sales"),
    "optimize": lambda: _agent.optimize_resource_allocation("engineering team budget"),
}


@app.get("/")
def index(request: Request):
    summary = _agent.get_value_report()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"summary": summary},
    )


@app.get("/api/ledger")
def api_ledger():
    return _agent.get_value_report()


@app.post("/actions/{name}")
def run_action(name: str):
    action = ACTIONS.get(name)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Unknown action: {name}")
    action()
    return RedirectResponse(url="/", status_code=303)
