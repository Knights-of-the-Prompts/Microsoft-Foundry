# Lifecycle Decision Package

*Generated: 2026-06-08 13:09 UTC*

## Agent

- **Name:** Contoso Sales Agent
- **Agent ID:** contoso-sales-agent-v1
- **Owner:** douwe@capgeminilanding.onmicrosoft.com
- **Sponsor:** admin@capgeminilanding.onmicrosoft.com

## Decision

- **Current state:** operating
- **Recommended action:** Review
- **Recommended state:** under_review

## Gate Results

| Gate | Status | Message |
|---|---|---|
| metadata_gate | pass | All required profile fields are present. |
| azure_resource_gate | fail | No Azure resources were found that are associated with this agent. Tag at least one resource with agent_id, agentName, or accountable_agents_demo='true'. |
| risk_gate | warning | 2 medium-impact Azure Advisor finding(s) noted. |

## Required Actions

- Associate at least one Azure resource with this agent by adding a matching tag (agent_id, agentName, or accountable_agents_demo='true')
- Review medium-risk Advisor recommendation: Microsoft Foundry resources should use Azure Private Link
- Review medium-risk Advisor recommendation: Microsoft Foundry resources should restrict network access

## Explanation

No Azure resources were found that are associated with this agent. Tag at least one resource with agent_id, agentName, or accountable_agents_demo='true'. 2 medium-impact Azure Advisor finding(s) noted. 1 Azure evidence collection warning(s) noted.
