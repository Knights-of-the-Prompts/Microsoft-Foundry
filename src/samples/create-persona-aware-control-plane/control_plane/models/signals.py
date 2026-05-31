"""Signal model for the control plane.

Every signal gathered from a platform connector carries SignalSourceMetadata
so the KPI Agent and evidence trail always know:
- whether data is mock, live, or hybrid
- which connector and platform it came from
- when it was retrieved
- how confident we are in the data
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class SignalSourceMetadata:
    """Provenance metadata attached to every signal.

    Transparency principle: the KPI Agent must always be able to report
    *how* a signal was obtained and *how reliable* it is.
    """

    source_mode: str  # "mock" | "live" | "hybrid"
    connector_id: str
    platform_id: str
    retrieved_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # 0.0 = no confidence, 1.0 = fully verified live data
    confidence: float = 1.0
    # Original API response reference (e.g. API URL, query id)
    raw_reference: Optional[str] = None
    # Free-text notes about data quality or known gaps
    data_quality_notes: Optional[str] = None


@dataclass
class Signal:
    """A single observable measurement from a platform connector.

    Signals are the raw inputs to the KPI Agent.  The agent interprets
    them in the context of a KPI and generates digest insights.

    ``signal_type`` is a string identifier such as ``"security_events"``,
    ``"cost_data"``, or ``"agent_invocations"``.

    ``value`` is connector-specific and can be a scalar, a list, or a dict.
    Consumers should check ``signal_type`` before interpreting ``value``.
    """

    signal_type: str
    platform_id: str
    title: str
    value: Any
    source_metadata: SignalSourceMetadata
    tags: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Signal:
        """Construct a Signal from a raw connector response dict.

        The ``data`` dict must include ``"source_metadata"`` as a nested dict.
        """
        meta_raw = data.get("source_metadata", {})
        meta = SignalSourceMetadata(
            source_mode=meta_raw.get("source_mode", "mock"),
            connector_id=meta_raw.get("connector_id", ""),
            platform_id=meta_raw.get("platform_id", ""),
            retrieved_at=meta_raw.get("retrieved_at", datetime.now(timezone.utc).isoformat()),
            confidence=meta_raw.get("confidence", 1.0),
            raw_reference=meta_raw.get("raw_reference"),
            data_quality_notes=meta_raw.get("data_quality_notes"),
        )
        return cls(
            signal_type=data.get("signal_type", ""),
            platform_id=data.get("platform_id", meta.platform_id),
            title=data.get("title", ""),
            value=data.get("value"),
            source_metadata=meta,
            tags=data.get("tags", {}),
        )
