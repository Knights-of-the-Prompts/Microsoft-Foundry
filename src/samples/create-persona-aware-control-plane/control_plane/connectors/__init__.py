"""Connector package — exports all connectors and ALL_CONNECTORS list.

Azure connector is factory-driven: AzureMockConnector is used unless
CONTROL_PLANE_AZURE_LIVE=true, in which case AzureLiveConnector is used.
"""
from __future__ import annotations

from control_plane.connectors.agent365 import Agent365MockConnector
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
    "AzureLiveConnector",
    "AzureMockConnector",
    "FoundryMockConnector",
    "KubernetesMockConnector",
    "Microsoft365MockConnector",
    "Agent365MockConnector",
    "ServiceNowMockConnector",
    "SalesforceMockConnector",
    "get_azure_connector",
]
