from __future__ import annotations

from control_plane.connectors.a365 import A365MockConnector
from control_plane.connectors.a365_live import A365LiveConnector, get_a365_connector
from control_plane.connectors.agent365 import Agent365MockConnector
from control_plane.connectors.agent365_live import Agent365LiveConnector, get_agent365_connector
from control_plane.connectors.azure import AzureMockConnector
from control_plane.connectors.azure_live import AzureLiveConnector, get_azure_connector
from control_plane.connectors.foundry import FoundryMockConnector
from control_plane.connectors.kubernetes import KubernetesMockConnector
from control_plane.connectors.microsoft365 import Microsoft365MockConnector
from control_plane.connectors.salesforce import SalesforceMockConnector
from control_plane.connectors.servicenow import ServiceNowMockConnector

# Ordered list of connector classes (instantiated at startup).
# AzureMockConnector is included for tests; app.py overrides it via
# get_azure_connector() which picks live vs mock based on CONTROL_PLANE_AZURE_LIVE.
# Agent365MockConnector is similarly overridden by get_agent365_connector().
# A365MockConnector is similarly overridden by get_a365_connector().
ALL_CONNECTORS = [
    Microsoft365MockConnector,
    AzureMockConnector,
    KubernetesMockConnector,
    FoundryMockConnector,
    Agent365MockConnector,
    A365MockConnector,
    ServiceNowMockConnector,
    SalesforceMockConnector,
]

__all__ = [
    "ALL_CONNECTORS",
    "A365LiveConnector",
    "A365MockConnector",
    "AzureLiveConnector",
    "AzureMockConnector",
    "FoundryMockConnector",
    "KubernetesMockConnector",
    "Microsoft365MockConnector",
    "Agent365LiveConnector",
    "Agent365MockConnector",
    "ServiceNowMockConnector",
    "SalesforceMockConnector",
    "get_a365_connector",
    "get_azure_connector",
    "get_agent365_connector",
]

