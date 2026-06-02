"""Signal provenance models for the Persona-Aware Control Plane.

These models capture the full execution trail for every signal retrieval
attempt — whether live, mock, cached or error.  They are attached to the
ControlPackage so the UI can show per-signal source evidence.

Design:
- SignalExecution records one tool call (live or mock).
- SignalProvenance summarises the full provenance for one named signal.
- SourceSummary aggregates counts across the whole control package.

Every live connector call must produce a SignalExecution with
sourceMode="live".  Every mock fallback must produce sourceMode="mock".
Access failures produce sourceMode="error" and create an evidence event.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SignalExecution:
    """The result of one tool invocation during control package composition.

    Captures enough detail for the provenance drawer in the UI.
    """

    signal_name: str          # e.g. "recent_failed_operations"
    platform_id: str          # e.g. "azure"
    tool_name: str            # e.g. "azure.get_activity_log_summary"
    source_mode: str          # "live" | "mock" | "cache" | "error"
    retrieved_at: str = field(default_factory=_now)
    used_in_composition: bool = False
    confidence: float = 0.0
    query_summary: Optional[str] = None
    endpoint: Optional[str] = None
    identity_summary: Optional[str] = None
    raw_preview: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    evidence_ref: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_name": self.signal_name,
            "platform_id": self.platform_id,
            "tool_name": self.tool_name,
            "source_mode": self.source_mode,
            "retrieved_at": self.retrieved_at,
            "used_in_composition": self.used_in_composition,
            "confidence": self.confidence,
            "query_summary": self.query_summary,
            "endpoint": self.endpoint,
            "identity_summary": self.identity_summary,
            "raw_preview": self.raw_preview,
            "error": self.error,
            "evidence_ref": self.evidence_ref,
        }


@dataclass
class SourceSummary:
    """Aggregate counts across all signal executions in a control package."""

    live_signals: int = 0
    mock_signals: int = 0
    error_signals: int = 0
    cache_signals: int = 0
    used_live_signals: int = 0
    used_mock_signals: int = 0

    @property
    def readiness(self) -> str:
        """Readiness based on signal availability."""
        if self.live_signals > 0 and self.error_signals == 0:
            return "ready"
        if self.live_signals > 0 and self.error_signals > 0:
            return "partially_ready"
        return "not_ready"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "live_signals": self.live_signals,
            "mock_signals": self.mock_signals,
            "error_signals": self.error_signals,
            "cache_signals": self.cache_signals,
            "used_live_signals": self.used_live_signals,
            "used_mock_signals": self.used_mock_signals,
            "readiness": self.readiness,
        }

    @classmethod
    def from_executions(cls, executions: List[SignalExecution]) -> "SourceSummary":
        s = cls()
        for e in executions:
            if e.source_mode == "live":
                s.live_signals += 1
                if e.used_in_composition:
                    s.used_live_signals += 1
            elif e.source_mode == "mock":
                s.mock_signals += 1
                if e.used_in_composition:
                    s.used_mock_signals += 1
            elif e.source_mode == "error":
                s.error_signals += 1
            elif e.source_mode == "cache":
                s.cache_signals += 1
        return s
