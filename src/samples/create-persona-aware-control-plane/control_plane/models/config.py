"""Configuration model for the control plane.

ControlPlaneConfig is the single top-level configuration object.
In local development it is populated from environment variables.
In production it should be backed by Azure Key Vault or a config service.

Security notes:
- Secret values must never appear inline in this model.
- ``secret_ref`` fields hold a reference name (e.g. Key Vault secret name
  or environment variable name) — not the actual secret.
- Resolve secrets at runtime using AzureKeyVaultSecretClient or os.environ.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from control_plane.connectors.base import AuthType, ConnectorConfig, ConnectorMode

_GLOBAL_MODE_ENV = "CONTROL_PLANE_MODE"


@dataclass
class PlatformModeConfig:
    """Per-platform mode override.

    Allows individual platforms to run in live mode while the rest use mock.
    Used in ``hybrid`` global mode.
    """

    platform_id: str
    mode: ConnectorMode
    enabled: bool = True


@dataclass
class ControlPlaneConfig:
    """Top-level configuration for the control plane.

    ``global_mode`` sets the default mode for all connectors.
    ``platform_overrides`` lets individual connectors diverge.

    Example:
        config = ControlPlaneConfig.from_env()
        # global_mode=hybrid, azure override to live if credentials present
    """

    global_mode: ConnectorMode = ConnectorMode.MOCK
    platform_overrides: Dict[str, PlatformModeConfig] = field(default_factory=dict)
    connector_configs: Dict[str, ConnectorConfig] = field(default_factory=dict)

    def mode_for(self, platform_id: str) -> ConnectorMode:
        """Effective mode for a given platform."""
        if platform_id in self.platform_overrides:
            return self.platform_overrides[platform_id].mode
        return self.global_mode

    @classmethod
    def from_env(cls) -> ControlPlaneConfig:
        """Build a ControlPlaneConfig from environment variables.

        All values default to mock mode so the control plane runs locally
        without any credentials.
        """
        raw_mode = os.getenv(_GLOBAL_MODE_ENV, "mock").lower()
        try:
            global_mode = ConnectorMode(raw_mode)
        except ValueError:
            global_mode = ConnectorMode.MOCK

        connector_configs: Dict[str, ConnectorConfig] = {
            "microsoft365": ConnectorConfig(
                connector_id="microsoft365",
                platform_id="microsoft365",
                mode=global_mode,
                tenant_id=os.getenv("M365_TENANT_ID"),
                client_id=os.getenv("M365_CLIENT_ID"),
                auth_type=AuthType.ENTRA_CLIENT_CREDENTIALS,
                secret_ref=os.getenv("M365_CLIENT_SECRET_REF", "m365-client-secret"),
                scopes=["https://graph.microsoft.com/.default"],
            ),
            "azure": ConnectorConfig(
                connector_id="azure",
                platform_id="azure",
                mode=global_mode,
                tenant_id=os.getenv("AZURE_TENANT_ID"),
                subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID"),
                client_id=os.getenv("AZURE_CLIENT_ID"),
                auth_type=AuthType.AZURE_DEFAULT_CREDENTIAL,
                secret_ref=os.getenv("AZURE_CLIENT_SECRET_REF", "azure-client-secret"),
            ),
            "kubernetes": ConnectorConfig(
                connector_id="kubernetes",
                platform_id="kubernetes",
                mode=global_mode,
                auth_type=AuthType.NONE,
            ),
            "foundry": ConnectorConfig(
                connector_id="foundry",
                platform_id="foundry",
                mode=global_mode,
                base_url=os.getenv("FOUNDRY_PROJECT_ENDPOINT", ""),
                subscription_id=os.getenv("FOUNDRY_SUBSCRIPTION_ID"),
                auth_type=AuthType.AZURE_DEFAULT_CREDENTIAL,
            ),
            "agent365": ConnectorConfig(
                connector_id="agent365",
                platform_id="agent365",
                mode=global_mode,
                tenant_id=os.getenv("AGENT365_TENANT_ID"),
                client_id=os.getenv("AGENT365_CLIENT_ID"),
                auth_type=AuthType.ENTRA_CLIENT_CREDENTIALS,
                secret_ref=os.getenv("AGENT365_CLIENT_SECRET_REF", "agent365-client-secret"),
                scopes=["https://graph.microsoft.com/.default"],
            ),
            "servicenow": ConnectorConfig(
                connector_id="servicenow",
                platform_id="servicenow",
                mode=global_mode,
                base_url=os.getenv("SERVICENOW_BASE_URL", ""),
                auth_type=AuthType.API_KEY,
                secret_ref=os.getenv("SERVICENOW_API_KEY_REF", "servicenow-api-key"),
            ),
            "salesforce": ConnectorConfig(
                connector_id="salesforce",
                platform_id="salesforce",
                mode=global_mode,
                base_url=os.getenv("SALESFORCE_BASE_URL", ""),
                client_id=os.getenv("SALESFORCE_CLIENT_ID"),
                auth_type=AuthType.OAUTH,
                secret_ref=os.getenv("SALESFORCE_CLIENT_SECRET_REF", "salesforce-client-secret"),
            ),
        }

        return cls(global_mode=global_mode, connector_configs=connector_configs)
