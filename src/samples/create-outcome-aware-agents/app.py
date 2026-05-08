"""FastAPI UI for the Outcome-Aware Agent.

* ``GET /``         -- the chat / activity-feed / ledger page.
* ``POST /chat``    -- send a user message to the Foundry agent.
* ``GET /events``   -- Server-Sent-Events stream of tool-call activity.
* ``GET /api/ledger`` -- JSON snapshot of the current ledger.

The Foundry agent is created on startup and torn down on shutdown.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request

# Workshop-wide .env lives at src/workshop/.env (two directories up from here).
load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / "workshop" / ".env")

from agent import FoundryOutcomeAgent, ValueLedger  # noqa: E402
from event_bus import bus  # noqa: E402
from ledger_store import store_from_env  # noqa: E402

logger = logging.getLogger("outcome_aware_agent.app")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


_ledger = ValueLedger(store=store_from_env())
_agent = FoundryOutcomeAgent(ledger=_ledger)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _agent.is_configured:
        try:
            await _agent.start()
            logger.info("Foundry agent ready.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to start Foundry agent: %s", exc)
            # Continue serving the page so the user sees the error in the UI
            # rather than getting a 500 on every request.
    else:
        logger.warning(
            "PROJECT_ENDPOINT / AGENT_MODEL_DEPLOYMENT_NAME not set — "
            "agent disabled. Configure src/workshop/.env to enable chat."
        )
    try:
        yield
    finally:
        await _agent.stop()


app = FastAPI(title="Outcome-Aware Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "summary": _ledger.get_summary(),
            "agent_ready": _agent.is_configured,
        },
    )


@app.get("/api/ledger")
def api_ledger():
    return _ledger.get_summary()


@app.post("/api/chat")
async def chat(req: ChatRequest):
    if not _agent.is_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "Foundry agent not configured. Set PROJECT_ENDPOINT and "
                "AGENT_MODEL_DEPLOYMENT_NAME in src/workshop/.env."
            ),
        )
    try:
        reply = await _agent.chat(req.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("chat() failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"reply": reply, "summary": _ledger.get_summary()}


@app.get("/events")
async def events(request: Request):
    """Server-Sent-Events stream of tool-call activity."""

    async def event_stream():
        queue = await bus.subscribe()
        try:
            # Initial hello so the connection establishes immediately.
            yield "event: ready\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Keep-alive comment so proxies don't close the connection.
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(payload)}\n\n"
        finally:
            await bus.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
