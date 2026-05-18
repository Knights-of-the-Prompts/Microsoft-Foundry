import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loaders import load_cost_rows_from_blob


def _sample_csv_bytes():
    return (
        "date,resourceId,resourceGroupName,serviceName,meterCategory,meterSubCategory,costInBillingCurrency,billingCurrency,tags\n"
        "2026-05-01,/subscriptions/xxx/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/s1,rg,Storage,Storage Transactions,Transactions,12.40,EUR,{\"agent_id\": \"sales-followup-agent\"}\n"
    ).encode("utf-8")


def test_load_cost_rows_from_blob_monkeypatched():
    # Build fake azure.storage.blob module with ContainerClient
    fake_azure = types.ModuleType("azure")
    fake_storage = types.ModuleType("azure.storage")
    fake_blob = types.ModuleType("azure.storage.blob")

    class FakeStream:
        def __init__(self, data: bytes):
            self._data = data

        def readall(self):
            return self._data

        def chunks(self):
            yield self._data

    class FakeBlobClient:
        def __init__(self, data: bytes):
            self._data = data

        def download_blob(self):
            return FakeStream(self._data)

    class FakeContainerClient:
        @classmethod
        def from_connection_string(cls, conn_str, container_name):
            return cls()

        def __init__(self):
            self._data = _sample_csv_bytes()

        def get_blob_client(self, blob_name):
            return FakeBlobClient(self._data)

    fake_blob.ContainerClient = FakeContainerClient

    sys.modules["azure"] = fake_azure
    sys.modules["azure.storage"] = fake_storage
    sys.modules["azure.storage.blob"] = fake_blob

    rows = load_cost_rows_from_blob(connection_string="fake", container_name="c", blob_name="b")
    assert len(rows) == 1
    r = rows[0]
    assert r.cost_amount == 12.40
    assert r.tags.get("agent_id") == "sales-followup-agent"
