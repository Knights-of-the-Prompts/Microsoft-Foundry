"""Pluggable ledger store for cost and value ledger entries.

This module provides a minimal in-memory `CostLedgerStore` used by the
workshop sample. It intentionally avoids any external dependencies and
keeps behavior simple: append entries and list them back.
"""

from __future__ import annotations

from typing import List

from models import CostLedgerEntry


class CostLedgerStore:
	"""In-memory store for `CostLedgerEntry` objects.

	Usage:
		store = CostLedgerStore()
		store.append(entry)
		entries = store.list_entries()
	"""

	def __init__(self) -> None:
		self._entries: List[CostLedgerEntry] = []

	def append(self, entry: CostLedgerEntry) -> None:
		self._entries.append(entry)

	def list_entries(self) -> List[CostLedgerEntry]:
		return list(self._entries)

