"""Core abstractions for the Persona-Aware Control Plane.

This module defines the shared contract that every platform connector must
implement, plus the data models used throughout the control plane.

Design principles:
- Mock adapters and live adapters implement the same PlatformConnector interface.
- Every signal returned by any connector carries SignalSourceMetadata so
  consumers always know whether data is mock, live, or hybrid.
- No connector implementation detail leaks through the interface boundary.

Connector status lifecycle:
    not_configured → configured → connected
                               └─ error
                               └─ unavailable
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ConnectorMode(str, Enum):
    """Runtime mode for a connector."""

    MOCK = "mock"
    LIVE = "live"
    HYBRID = "hybrid"


class ConnectorStatus(str, Enum):
    """Lifecycle status of a connector."""

    NOT_CONFIGURED = "not_configured"
    CONFIGURED = "configured"
    CONNECTED = "connected"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class AuthType(str, Enum):
    """Authentication mechanism required by a connector."""

    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    ENTRA_CLIENT_CREDENTIALS = "entra_client_credentials"
    ENTRA_DELEGATED = "entra_delegated"
    WORKLOAD_IDENTITY = "workload_identity"
    AZURE_DEFAULT_CREDENTIAL = "azure_default_credential"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ConnectorDefinition:
    """Static metadata describing a platform connector.

    Stored in the Tool Registry and used by the KPI Agent for capability
    discovery.  Mode and status fields reflect the current runtime state.
    """

    id: str
    platform_id: str
    name: str
    description: str
    mode: ConnectorMode
    status: ConnectorStatus
    auth_type: AuthType
    base_url: str
    required_scopes: List[str]
    supported_signal_types: List[str]
    supported_tools: List[str]
    health_check_endpoint: str = ""
    last_checked_at: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ConnectorConfig:
    """Runtime configuration for a platform connector.

    All sensitive values (secrets, tokens) are referenced by name via
    ``secret_ref`` — never stored inline.  Resolve them from Azure Key Vault
    or environment variables at runtime.
    """

    connector_id: str
    platform_id: str
    mode: ConnectorMode = ConnectorMode.MOCK
    base_url: str = ""
    tenant_id: Optional[str] = None
    subscription_id: Optional[str] = None
    client_id: Optional[str] = None
    scopes: List[str] = field(default_factory=list)
    auth_type: AuthType = AuthType.NONE
    # Reference to a secret in Key Vault or environment variable name.
    # Never store the actual secret value here.
    secret_ref: Optional[str] = None
    enabled: bool = True
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ControlPlaneTool:
    """A named capability exposed by a connector into the Tool Registry.

    The KPI Agent discovers tools via the registry and uses them to gather
    signals.  ``source_mode`` indicates whether the tool is backed by mock
    or live data, making it visible in audit trails.

    Access metadata (required_scopes, required_roles, required_permissions,
    supported_actions, sensitive_data_level, access_justification_template)
    is used by the Access Readiness Agent to check whether the selected
    persona can actually retrieve the signals required by their KPI.
    All access fields default to safe values so existing connectors are
    unaffected.
    """

    id: str
    connector_id: str
    platform_id: str
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_permissions: List[str]
    signal_types_returned: List[str]
    enabled: bool = True
    source_mode: ConnectorMode = ConnectorMode.MOCK
    # --- Access metadata (Phase 3 addition) ---
    required_scopes: List[str] = field(default_factory=list)
    required_roles: List[str] = field(default_factory=list)
    supported_actions: List[str] = field(default_factory=list)
    sensitive_data_level: str = "low"  # none | low | medium | high | restricted
    access_justification_template: str = ""


# ---------------------------------------------------------------------------
# Abstract connector interface
# ---------------------------------------------------------------------------


class PlatformConnector(ABC):
    """Abstract base class for all platform connectors.

    Every connector — mock or live — implements this interface.  The only
    difference is the underlying implementation: mock connectors return
    deterministic demo data; live connectors call real platform APIs.

    Mock connectors are demo adapters, not permanent shortcuts.  When a live
    connector is configured, it replaces the mock connector in the ToolRegistry
    without requiring any changes to the KPI Agent or control plane core.

    Implementors must guarantee:
    - ``get_health()`` never raises; errors are returned inside the dict.
    - ``get_signals()`` always returns a list (empty on failure, not an exception).
    - Every signal dict includes a ``"source_metadata"`` key.
    """

    def __init__(self) -> None:
        self._mode: ConnectorMode = ConnectorMode.MOCK

    def set_mode(self, mode: ConnectorMode) -> None:
        """Update the runtime mode of this connector."""
        self._mode = mode

    @abstractmethod
    def get_definition(self) -> ConnectorDefinition:
        """Return the static metadata for this connector."""
        ...

    @abstractmethod
    def validate_config(self, config: ConnectorConfig) -> List[str]:
        """Validate a config against connector-specific requirements.

        Returns a list of human-readable validation error strings.
        An empty list means the config is valid.
        """
        ...

    @abstractmethod
    def get_health(self) -> Dict[str, Any]:
        """Return a health status dict.  Must not raise.

        Expected keys: ``status`` (str), ``latency_ms`` (float|None),
        ``message`` (str|None), ``checked_at`` (ISO timestamp str).
        """
        ...

    @abstractmethod
    def get_available_tools(self) -> List[ControlPlaneTool]:
        """Return all tools this connector exposes to the Tool Registry."""
        ...

    @abstractmethod
    def get_signals(
        self,
        signal_requirements: List[str],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Fetch signals matching the given signal type requirements.

        Each returned dict must include a ``"source_metadata"`` key whose
        value is a dict with at minimum:
            source_mode, connector_id, platform_id, retrieved_at,
            confidence, raw_reference, data_quality_notes
        """
        ...

    @abstractmethod
    def execute_tool(self, tool_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named tool exposed by this connector.

        Returns a result dict.  On error, returns a dict with key ``"error"``.
        """
        ...

    # ------------------------------------------------------------------
    # Helpers available to all connectors
    # ------------------------------------------------------------------

    def _source_metadata(
        self,
        *,
        source_mode: ConnectorMode,
        connector_id: str,
        platform_id: str,
        confidence: float = 1.0,
        raw_reference: Optional[str] = None,
        data_quality_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a standard source_metadata dict for a signal."""
        return {
            "source_mode": source_mode.value,
            "connector_id": connector_id,
            "platform_id": platform_id,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "confidence": confidence,
            "raw_reference": raw_reference,
            "data_quality_notes": data_quality_notes,
        }
