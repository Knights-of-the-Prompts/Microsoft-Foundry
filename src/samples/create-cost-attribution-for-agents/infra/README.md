Cost attribution demo infra

This folder contains small, low-cost Bicep templates used by the sample
to demonstrate a tagging strategy for cost attribution. The templates
create inexpensive resources intended for workshop demonstrations only.

Files
-----
- `cost-attribution-demo.bicep` — group-scope template that creates:
	- Storage Accounts tagged as `direct` for sample agents
	- A Log Analytics workspace tagged as `indirect`
	- A shared Storage Account tagged as `platform`
	- An intentionally incomplete Storage Account (unallocated)
- `cost-export-storage.bicep` — storage account + `cost-exports` container
	intended as a destination for Cost Management exports.
- `deploy.sh` — helper script to create the resource group and deploy
	the templates (see below).

Why these resources exist
------------------------
The resources demonstrate how Azure resource tags can be used to map
costs into categories useful for attribution and allocation. Tags used
by the sample include `agent_id`, `workload_id`, `cost_category`,
`allocation_scope`, `distribution_key`, and `shared_service`.

Tag mapping summary
-------------------
- Direct: resources with `agent_id` / `workload_id` or `cost_category=direct`.
- Indirect: shared services with `cost_category=indirect` and
	`distribution_key=log_volume_gb`.
- Platform: shared infra with `cost_category=platform` and
	`distribution_key=weighted_agent_usage`.
- Unallocated: intentionally missing attribution tags; kept visible.

Distribution keys
-----------------
- `log_volume_gb`: allocate indirect costs by agent log-volume.
- `weighted_agent_usage`: weighted allocation across token/runtime/tool-call
	shares. Weights are configured in `allocation_rules.yaml`.

Inspecting resources
--------------------
Use the Azure CLI or portal to inspect the deployed resources and tags.
Example (Azure CLI):

```bash
az resource list --resource-group rg-accountable-agents-cost-demo --query "[].{name:name, type:type, tags:tags}"
```

Notes about Cost Management data
--------------------------------
- Azure Cost Management and Usage exports are not real-time. Exports and
	billing data can be delayed (often several hours up to 24-48 hours).
- This sample provides deterministic offline data so the workshop can
	proceed without waiting for production billing exports.

Cleanup
-------
Only delete the demo resource group if you are sure it contains no
other workloads. Example:

```bash
az group delete --name "$AZURE_RESOURCE_GROUP_NAME" --yes --no-wait
```

