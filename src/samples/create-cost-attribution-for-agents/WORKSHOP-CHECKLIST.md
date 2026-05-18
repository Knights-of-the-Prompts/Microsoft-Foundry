# Workshop checklist — tagging, policy, and pipeline

Use this short checklist during the workshop to configure tagging, enforce governance, and wire a robust export → allocate pipeline.

- [ ] Tagging
  - [ ] Define stable `agent_id` and `workload_id` identifier list (keep in source control).
  - [ ] Add required tags to IaC templates (Bicep/ARM/Terraform): `agent_id`, `cost_category`, `distribution_key`.
  - [ ] Run: `az group update --name <rg> --set tags.agent_id=agent-A` for quick demo resources.

- [ ] Azure Policy
  - [ ] Create a policy to require `cost_category` and `agent_id` on resource creation (deny or append mode).
  - [ ] Assign policy to demo subscription/resource group before onboarding sample workloads.

- [ ] Cost export
  - [ ] Configure Azure Cost Management scheduled export to write CSVs to a Storage Account container.
  - [ ] Name blobs with a predictable key: `exports/daily/2026-05-01.csv`.

- [ ] Processing pipeline
  - [ ] Create an Event Grid subscription on the storage container for `BlobCreated` events.
  - [ ] Implement an Azure Function (Python/.NET/JS) triggered by Event Grid.
  - [ ] Within handler:
    - Check a processed‑blob registry for the blob ETag (Table Storage / Cosmos / durable store).
    - Stream the CSV into the loader (avoid loading whole blob into memory).
    - Run classify → allocate → commit ledger (atomic commit pattern).
    - Persist processed ETag after successful commit.

- [ ] Operational
  - [ ] Configure monitoring/alerts for failed allocations / high unallocated cost %.
  - [ ] Periodic reconciliation: sample checks between allocated costs and engineering estimates.

Quick commands (demo)

```bash
# Example: run the sample against a blob and record processed state locally
export AZ_BLOB_CONNECTION_STRING="<conn>"
export AZ_BLOB_CONTAINER="cost-exports"
export AZ_BLOB_BLOBNAME="daily/2026-05-01.csv"
python -c "from loaders import load_cost_rows_from_blob; print(len(load_cost_rows_from_blob(connection_string=\"$AZ_BLOB_CONNECTION_STRING\", container_name=\"$AZ_BLOB_CONTAINER\", blob_name=\"$AZ_BLOB_BLOBNAME\", registry_path='processed_blobs.json')) )"
```
