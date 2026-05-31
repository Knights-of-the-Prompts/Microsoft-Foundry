"""Connector package — exports all mock connectors and ALL_CONNECTORS list."""
from __future__ import annotations

from control_plane.connectors.agent365 import Agent365MockConnector
from control_plane.connectors.azure import AzureMockConnector
from control_plane.connectors.foundry import FoundryMockConnector
from control_plane.connectors.kubernetes import KubernetesMockConnector
from control_plane.connectors.microsoft365 import Microsoft365MockConnector
from control_plane.connectors.salesforce import SalesforceMockConnector
from control_plane.connectors.servicenow import ServiceNowMockConnector

# Ordered list of all mock connectors.
# Import this list to register all connectors in the ToolRegistry.
ALL_CONNECTORS = [
    Microsoft365MockConnector,
    AzureMockConnector,
    KubernetesMockConnector,
    FoundryMockConnector,
    Agent365MockConnector,
    ServiceNowMockConnector,
    SalesforceMockConnector,
]

__all__ = [
    "ALL_CONNECTORS",
    "Microsoft365MockConnector",
    "AzureMockConnector",
    "KubernetesMockConnector",
    "FoundryMockConnector",
    "Agent365MockConnector",
    "ServiceNowMockConnector",
    "SalesforceMockConnector",
]
