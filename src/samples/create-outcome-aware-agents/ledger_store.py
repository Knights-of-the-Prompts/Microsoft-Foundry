"""Pluggable storage backends for the value ledger.

Two implementations are provided:

* ``InMemoryLedgerStore`` -- a simple list, used by the local workshop demo.
* ``ConfidentialLedgerStore`` -- persists each entry to Azure Confidential
  Ledger, providing tamper-evident, append-only storage with cryptographic
  receipts. Authentication uses ``DefaultAzureCredential`` so the same code
  works locally (via ``az login``) and in Azure (via Managed Identity).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import List, Protocol


@dataclass
class ValueEntry:
    """Represents a single entry in the value ledger."""

    timestamp: str
    task_description: str
    hours_saved: float
    materialized_value: str
    agent_action: str


class LedgerStore(Protocol):
    """Storage protocol for value ledger entries."""

    def append(self, entry: ValueEntry) -> None: ...

    def list_entries(self) -> List[ValueEntry]: ...


class InMemoryLedgerStore:
    """Stores entries in a Python list. Lost when the process exits."""

    def __init__(self) -> None:
        self._entries: List[ValueEntry] = []

    def append(self, entry: ValueEntry) -> None:
        self._entries.append(entry)

    def list_entries(self) -> List[ValueEntry]:
        return list(self._entries)


class ConfidentialLedgerStore:
    """Persists value entries to Azure Confidential Ledger.

    Parameters
    ----------
    ledger_endpoint:
        The ``ledgerUri`` output by the Bicep template, e.g.
        ``https://my-ledger.confidential-ledger.azure.com``.
    """

    def __init__(self, ledger_endpoint: str) -> None:
        # Imports are local so the in-memory backend works without the SDK.
        from azure.identity import DefaultAzureCredential
        from azure.confidentialledger import ConfidentialLedgerClient
        from azure.confidentialledger.certificate import (
            ConfidentialLedgerCertificateClient,
        )

        credential = DefaultAzureCredential()
        ledger_id = ledger_endpoint.replace("https://", "").split(".")[0]

        # ACL uses a per-ledger TLS cert that must be fetched and pinned.
        identity_client = ConfidentialLedgerCertificateClient()
        identity = identity_client.get_ledger_identity(ledger_id=ledger_id)

        cert_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".pem", delete=False
        )
        cert_file.write(identity["ledgerTlsCertificate"])
        cert_file.close()
        self._cert_path = cert_file.name

        self._client = ConfidentialLedgerClient(
            endpoint=ledger_endpoint,
            credential=credential,
            ledger_certificate_path=self._cert_path,
        )

    def append(self, entry: ValueEntry) -> None:
        payload = json.dumps(asdict(entry))
        poller = self._client.begin_create_ledger_entry(
            entry={"contents": payload}
        )
        poller.result()

    def list_entries(self) -> List[ValueEntry]:
        entries: List[ValueEntry] = []
        for raw in self._client.list_ledger_entries():
            try:
                data = json.loads(raw["contents"])
                entries.append(ValueEntry(**data))
            except (KeyError, ValueError, TypeError):
                # Skip entries that don't match our schema (e.g. system events).
                continue
        return entries


def store_from_env() -> LedgerStore:
    """Build a ``LedgerStore`` based on environment variables.

    ``LEDGER_BACKEND=memory`` (default) returns ``InMemoryLedgerStore``.
    ``LEDGER_BACKEND=acl`` returns ``ConfidentialLedgerStore`` and requires
    ``ACL_ENDPOINT`` to be set.
    """

    backend = os.getenv("LEDGER_BACKEND", "memory").lower()
    if backend == "acl":
        endpoint = os.getenv("ACL_ENDPOINT")
        if not endpoint:
            raise RuntimeError(
                "LEDGER_BACKEND=acl requires ACL_ENDPOINT to be set "
                "(e.g. https://<name>.confidential-ledger.azure.com)."
            )
        return ConfidentialLedgerStore(endpoint)
    return InMemoryLedgerStore()
