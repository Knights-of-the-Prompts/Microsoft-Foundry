"""In-memory stores for agent requests and evidence events.

These are simple thread-safe stores that hold state for the duration of the
process lifetime.  They are intentionally NOT persistent — state is reset on
every restart.  This is appropriate for a local demo.

For production use, replace with a database or durable storage backend.

Usage::

    from control_plane.stores import evidence_store, request_store

    evidence_store.add(event)
    all_events = evidence_store.list()
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Callable, List, Optional

from control_plane.models.governance import (
    AgentIdea,
    AgentRequest,
    AgentRequestStatus,
    EvidenceEvent,
)


# ---------------------------------------------------------------------------
# Generic store base
# ---------------------------------------------------------------------------


class _Store:
    """Thread-safe in-memory list store."""

    def __init__(self) -> None:
        self._items: list = []
        self._lock = Lock()

    def _add(self, item: object) -> None:
        with self._lock:
            self._items.append(item)

    def _list(self, predicate: Optional[Callable] = None) -> list:
        with self._lock:
            if predicate is None:
                return list(self._items)
            return [i for i in self._items if predicate(i)]

    def _get(self, id_value: str, id_attr: str = "id") -> Optional[object]:
        with self._lock:
            for item in self._items:
                if getattr(item, id_attr, None) == id_value:
                    return item
        return None

    def clear(self) -> None:
        """Clear all items (useful for tests)."""
        with self._lock:
            self._items.clear()


# ---------------------------------------------------------------------------
# Evidence store
# ---------------------------------------------------------------------------


class EvidenceStore(_Store):
    """Immutable append-only evidence trail."""

    def add(self, event: EvidenceEvent) -> EvidenceEvent:
        self._add(event)
        return event

    def add_event(
        self,
        event_type: str,
        payload: dict,
        *,
        persona_id: Optional[str] = None,
        kpi_id: Optional[str] = None,
        source_mode: str = "mock",
    ) -> EvidenceEvent:
        event = EvidenceEvent(
            id=str(uuid.uuid4()),
            event_type=event_type,
            persona_id=persona_id,
            kpi_id=kpi_id,
            payload=payload,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source_mode=source_mode,
        )
        return self.add(event)

    def list(
        self,
        *,
        persona_id: Optional[str] = None,
        kpi_id: Optional[str] = None,
    ) -> List[EvidenceEvent]:
        def _pred(e: EvidenceEvent) -> bool:
            if persona_id and e.persona_id != persona_id:
                return False
            if kpi_id and e.kpi_id != kpi_id:
                return False
            return True

        return self._list(_pred)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Agent request store
# ---------------------------------------------------------------------------


class AgentRequestStore(_Store):
    """Mutable store for agent build requests."""

    def add(self, request: AgentRequest) -> AgentRequest:
        self._add(request)
        return request

    def get(self, request_id: str) -> Optional[AgentRequest]:
        return self._get(request_id)  # type: ignore[return-value]

    def list(self) -> List[AgentRequest]:
        return self._list()  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Singletons — used by FastAPI app and KPI Agent
# ---------------------------------------------------------------------------

evidence_store = EvidenceStore()
request_store = AgentRequestStore()
