"""Data loader utilities for the Cost Attribution sample.

Provides small, deterministic loaders used by the example script. These
functions return typed dataclasses defined in :mod:`models`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List
import io
import tempfile
import os
from pathlib import Path


def _parse_tags(raw: str) -> dict[str, str]:
	if not raw:
		return {}
	try:
		return json.loads(raw)
	except json.JSONDecodeError:
		# Try a best-effort fallback by replacing single quotes with
		# double-quotes (sometimes CSVs are written with single quotes).
		try:
			return json.loads(raw.replace("'", '"'))
		except Exception:
			return {}


def load_cost_rows(path: str | Path) -> List["AzureCostRow"]:
	"""Load Azure cost rows from a CSV and return list of AzureCostRow.

	The CSV is expected to have a `tags` column containing a JSON
	object (as a string). The function parses that JSON into a
	dictionary.
	"""

	from models import AzureCostRow  # local import to keep script flexible

	path = Path(path)
	if not path.exists():
		raise FileNotFoundError(f"Cost CSV file not found: {path}. Run the example from the sample folder or provide the correct path.")
	rows: List[AzureCostRow] = []
	try:
		fh = path.open(newline="", encoding="utf-8")
	except Exception as exc:
		raise FileNotFoundError(f"Unable to open cost CSV file: {path}: {exc}")
	with fh:
		reader = csv.DictReader(fh)
		for r in reader:
			tags_raw = r.get("tags", "") or r.get("Tags", "")
			tags = _parse_tags(tags_raw)
			try:
				cost = float(r.get("costInBillingCurrency", 0) or 0)
			except Exception:
				cost = 0.0
			row = AzureCostRow(
				date=r.get("date", ""),
				resource_id=r.get("resourceId", ""),
				resource_group=r.get("resourceGroupName", ""),
				service_name=r.get("serviceName", ""),
				meter_category=r.get("meterCategory", ""),
				meter_subcategory=r.get("meterSubCategory", ""),
				cost_amount=cost,
				currency=r.get("billingCurrency", ""),
				tags=tags,
			)
			rows.append(row)
	return rows


def load_cost_rows_from_blob(
	connection_string: str | None = None,
	container_name: str | None = None,
	blob_name: str | None = None,
	account_url: str | None = None,
	use_default_credential: bool = False,
	registry_path: str | Path | None = None,
) -> List["AzureCostRow"]:
	"""Load cost CSV from an Azure Blob and return list of AzureCostRow.

	Either `connection_string` (and `container_name`) OR `account_url` with
	`use_default_credential=True` (and `container_name`) must be provided.

	For simplicity this helper reads the blob fully into memory. For
	production workloads prefer streaming via `download_blob().chunks()`.
	"""

	from models import AzureCostRow  # local import

	# Simple file-based processed registry for idempotency in demos.
	class FileProcessedBlobRegistry:
		def __init__(self, path: str | Path):
			self.path = Path(path)
			if not self.path.exists():
				try:
					self.path.parent.mkdir(parents=True, exist_ok=True)
					self.path.write_text('[]', encoding='utf-8')
				except Exception:
					pass

		def _read(self) -> list:
			try:
				text = self.path.read_text(encoding='utf-8')
				return json.loads(text or '[]')
			except Exception:
				return []

		def exists(self, etag: str) -> bool:
			return etag in self._read()

		def save(self, etag: str) -> None:
			entries = self._read()
			if etag in entries:
				return
			entries.append(etag)
			try:
				self.path.write_text(json.dumps(entries), encoding='utf-8')
			except Exception:
				pass

	if not container_name or not blob_name:
		raise ValueError("container_name and blob_name are required")

	try:
		# Import inside function so tests may monkeypatch modules
		from azure.storage.blob import ContainerClient
	except Exception as exc:
		raise RuntimeError(
			"azure.storage.blob is required for blob loading; install azure-storage-blob"
		) from exc

	if connection_string:
		container = ContainerClient.from_connection_string(connection_string, container_name)
	else:
		if not account_url or not use_default_credential:
			raise ValueError("Either connection_string or (account_url and use_default_credential=True) must be provided")
		try:
			from azure.identity import DefaultAzureCredential

			cred = DefaultAzureCredential()
		except Exception:
			raise RuntimeError("azure.identity.DefaultAzureCredential is required for account_url auth")
		container = ContainerClient(account_url=account_url, container_name=container_name, credential=cred)

	blob_client = container.get_blob_client(blob_name)

	# Optional idempotency: if caller provides registry_path then
	# attempt to read blob properties ETag and short-circuit if already processed.
	registry = None
	etag = None
	if registry_path:
		try:
			props = None
			if hasattr(blob_client, 'get_blob_properties'):
				props = blob_client.get_blob_properties()
			if props is not None and hasattr(props, 'etag'):
				etag = props.etag
		except Exception:
			# unable to fetch properties; continue without etag
			etag = None
		if etag:
			registry = FileProcessedBlobRegistry(registry_path)
			if registry.exists(etag):
				# Already processed
				return []

	# Stream download into a temporary file to avoid loading entire blob into memory.
	stream = blob_client.download_blob()
	rows: List[AzureCostRow] = []
	with tempfile.NamedTemporaryFile(delete=False) as tmp:
		tmp_name = tmp.name
		try:
			# If stream has chunks() iterate, otherwise readall()
			if hasattr(stream, 'chunks'):
				for chunk in stream.chunks():
					if not chunk:
						continue
					tmp.write(chunk)
			else:
				data = stream.readall()
				tmp.write(data)

			# Ensure all bytes are flushed to disk before reading from the temp file
			tmp.flush()
			try:
				os.fsync(tmp.fileno())
			except Exception:
				pass
				
			# Parse CSV from temp file (text mode) to preserve CSV quoting/newlines
			with open(tmp_name, mode='r', encoding='utf-8', newline='') as fh:
				reader = csv.DictReader(fh)
				for r in reader:
					tags_raw = r.get('tags', '') or r.get('Tags', '')
					tags = _parse_tags(tags_raw)
					try:
						cost = float(r.get('costInBillingCurrency', 0) or 0)
					except Exception:
						cost = 0.0
					row = AzureCostRow(
						date=r.get('date', ''),
						resource_id=r.get('resourceId', ''),
						resource_group=r.get('resourceGroupName', ''),
						service_name=r.get('serviceName', ''),
						meter_category=r.get('meterCategory', ''),
						meter_subcategory=r.get('meterSubCategory', ''),
						cost_amount=cost,
						currency=r.get('billingCurrency', ''),
						tags=tags,
					)
					rows.append(row)
		finally:
			try:
				os.unlink(tmp_name)
			except Exception:
				pass

	# Persist processed etag if provided
	if registry and etag:
		try:
			registry.save(etag)
		except Exception:
			pass

	return rows


def load_runtime_events(path: str | Path) -> List["AgentRuntimeEvent"]:
	from models import AgentRuntimeEvent
	path = Path(path)
	if not path.exists():
		raise FileNotFoundError(f"Runtime events file not found: {path}. Ensure sample data is present.")
	try:
		text = path.read_text(encoding="utf-8")
		data = json.loads(text)
	except Exception as exc:
		raise ValueError(f"Failed to read/parse runtime events JSON at {path}: {exc}")
	events: List[AgentRuntimeEvent] = []
	for i, d in enumerate(data):
		event = AgentRuntimeEvent(
			event_id=d.get("event_id") or d.get("id") or f"evt-{i+1}",
			timestamp=d.get("timestamp", ""),
			agent_id=d.get("agent_id", ""),
			workload_id=d.get("workload_id", ""),
			business_process=d.get("business_process", ""),
			value_stream=d.get("value_stream", ""),
			token_count=float(d.get("token_count", 0) or 0),
			runtime_seconds=float(d.get("runtime_seconds", 0) or 0),
			tool_call_count=float(d.get("tool_call_count", 0) or 0),
			log_volume_gb=float(d.get("log_volume_gb", 0) or 0),
			request_count=float(d.get("request_count", 0) or 0),
			outcome_id=d.get("outcome_id", ""),
		)
		events.append(event)
	return events


def load_value_entries(path: str | Path) -> List["ValueLedgerEntry"]:
	from models import ValueLedgerEntry
	path = Path(path)
	if not path.exists():
		raise FileNotFoundError(f"Value ledger file not found: {path}. Ensure sample data is present.")
	try:
		text = path.read_text(encoding="utf-8")
		data = json.loads(text)
	except Exception as exc:
		raise ValueError(f"Failed to read/parse value ledger JSON at {path}: {exc}")
	entries: List[ValueLedgerEntry] = []
	for d in data:
		entry = ValueLedgerEntry(
			timestamp=d.get("timestamp", ""),
			agent_id=d.get("agent_id", ""),
			workload_id=d.get("workload_id", ""),
			outcome_id=d.get("outcome_id", ""),
			efficiency_value=float(d.get("efficiency_value", 0) or 0),
			outcome_value=float(d.get("outcome_value", 0) or 0),
			currency=d.get("currency", ""),
			description=d.get("description", ""),
		)
		entries.append(entry)
	return entries

