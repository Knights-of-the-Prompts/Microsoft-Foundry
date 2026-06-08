# Agent Lifecycle Management for Accountable Agents

**Governed lifecycle gates for operating, remediating, scaling and retiring enterprise agents**

---

## Series context

This is **Part 5** in the Accountable Agents sample series:

| Part | Sample | Focus |
|------|--------|-------|
| 1 | [Outcome-Aware Agents](../create-outcome-aware-agents/) | Value attribution |
| 2 | [Cost Attribution for Agents](../create-cost-attribution-for-agents/) | Cost attribution |
| 3 | [Agent Reporting](../create-agent-reporting/) | Consolidated agent reporting |
| 4 | [Persona-Aware Control Plane](../create-persona-aware-control-plane/) | Role-based governance |
| **5** | **Agent Lifecycle Management** | **Lifecycle gates and decisions** |

---

## Core idea

> A control plane becomes useful when its decisions change the lifecycle of the agents it governs.

An agent that is approved to operate, consuming Azure resources, and influencing business outcomes should be subject to structured lifecycle governance — not just monitored.

This sample implements that governance as a **decision function**: given an agent profile, live Azure evidence, and a lifecycle policy, determine the agent's lifecycle state and the recommended action.

---

## What this sample demonstrates

The sample evaluates whether an agent should:

- **Operate** — continue running as-is; all gates pass
- **Remediate** — required metadata or resource tags are missing
- **Scale** — usage and value signals justify expansion *(not yet implemented; requires real usage evidence)*
- **Restrict** — high-risk Azure Advisor findings warrant action
- **Retire** — agent is no longer needed or compliant *(manual decision outside this sample)*

The lifecycle decision is produced as a structured **Lifecycle Decision Package** — a Markdown and JSON artefact that can be used in governance reviews or audit trails.

---

## What this sample does NOT do

This sample is intentionally minimal:

- **No dashboard** — output is Markdown and JSON files
- **No workflow engine** — decision logic is plain Python
- **No synthetic Azure resources** — evidence comes from real Azure CLI output
- **No fake runtime telemetry** — if no Azure data is available, the sample warns honestly
- **No automatic remediation** — the sample only recommends; it does not act
- **No production lifecycle system** — this is a decision pattern demonstration

---

## Lifecycle Decision Package

After evaluation, the sample writes two files to `outputs/`:

- `outputs/lifecycle-decision-package.md` — human-readable summary for governance reviews
- `outputs/lifecycle-decision-package.json` — structured data for integration with reporting tools

---

## Run locally

```bash
cd src/samples/create-agent-lifecycle-management
pip install -r requirements.txt
python agent-lifecycle-example.py
```

---

## How to configure `agent_profile.yaml`

Before running the sample, open `agent_profile.yaml` and update:

- `agent_id` — unique identifier for the agent
- `owner_email` / `sponsor_email` — accountability contacts
- `azure_resource_group` — the Azure resource group that contains the agent's resources
- `required_resource_tags` — the tags your organisation requires on all AI agent resources

The sample uses these values to query live Azure resources and evaluate compliance gates.

---

## What live Azure data is used

| Data source | Azure CLI command | Purpose |
|-------------|------------------|---------|
| Resource list | `az resource list --resource-group ...` | Find agent-related Azure resources |
| Resource tags | Included in resource list output | Check required tag compliance |
| Advisor recommendations | `az advisor recommendation list ...` | Identify risk findings |

---

## What to do when no resources are found

If no Azure resources are found for the configured resource group:

1. Confirm `azure_resource_group` in `agent_profile.yaml` is correct.
2. Confirm you are logged in: `az login`
3. Confirm the resource group exists: `az group show --name <resource-group>`
4. Add the tag `accountable_agents_demo: "true"` to at least one resource to associate it with this agent.

The sample will not invent resources. It will report `under_review` and list warnings.

---

## Limitations

- This is **not a production lifecycle management platform**.
- It does **not automatically change agent state** in Agent 365, Azure AI Foundry, or any orchestration platform.
- It does **not automatically remediate** Azure resources (add tags, update policies, etc.).
- It **only demonstrates the lifecycle decision pattern** using real Azure evidence.
- It **intentionally avoids mock runtime data**. If Azure data is unavailable, the sample reports warnings rather than fabricating results.

---

## Tests

```bash
pytest tests/
```

Tests use in-memory data only and do not call Azure.
