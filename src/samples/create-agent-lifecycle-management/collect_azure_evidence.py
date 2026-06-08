"""
collect_azure_evidence.py

Collects live Azure evidence for an agent using Azure CLI.
Does not create resources. Does not use mock data.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from models import AgentProfile, AzureAdvisorFinding, AzureResourceEvidence, EvidenceBundle


def load_agent_profile(path: str) -> AgentProfile:
    """Load and parse agent_profile.yaml into an AgentProfile dataclass."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return AgentProfile(
        agent_id=data["agent_id"],
        display_name=data["display_name"],
        owner_email=data["owner_email"],
        sponsor_email=data["sponsor_email"],
        business_stream=data["business_stream"],
        expected_outcome=data["expected_outcome"],
        cost_center=data["cost_center"],
        environment=data["environment"],
        azure_resource_group=data["azure_resource_group"],
        required_resource_tags=data.get("required_resource_tags", []),
    )


def _run_az(args: list[str]) -> tuple[str, str, int]:
    """Run an Azure CLI command and return (stdout, stderr, returncode)."""
    result = subprocess.run(
        ["az"] + args,
        capture_output=True,
        text=True,
    )
    return result.stdout, result.stderr, result.returncode


def _check_az_available() -> None:
    """Raise SystemExit with a clear message if Azure CLI is not installed."""
    result = subprocess.run(["az", "--version"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: Azure CLI is not installed or not on PATH.")
        print("Install it from https://aka.ms/installazurecli")
        sys.exit(1)


def _check_az_logged_in() -> None:
    """Raise SystemExit with a clear message if the user is not logged in."""
    stdout, stderr, rc = _run_az(["account", "show", "--output", "json"])
    if rc != 0:
        print("ERROR: Not logged in to Azure CLI.")
        print("Run: az login")
        sys.exit(1)


def _is_agent_resource(resource: dict, profile: AgentProfile) -> bool:
    """Return True if this Azure resource is associated with the agent."""
    tags = resource.get("tags") or {}
    if tags.get("agent_id") == profile.agent_id:
        return True
    if tags.get("agentName") == profile.display_name:
        return True
    if str(tags.get("accountable_agents_demo", "")).lower() == "true":
        return True
    return False


def collect_azure_evidence(profile: AgentProfile) -> EvidenceBundle:
    """
    Collect live Azure evidence for the given agent profile.

    Uses Azure CLI to:
    1. List resources in the configured resource group.
    2. Filter resources related to the agent by tag match.
    3. Check required tags on matching resources.
    4. Collect Azure Advisor recommendations (best-effort).

    Does not create resources. Does not use mock data.
    """
    _check_az_available()
    _check_az_logged_in()

    bundle = EvidenceBundle(agent_id=profile.agent_id)

    # --- Verify resource group exists ---
    _, stderr, rc = _run_az([
        "group", "show",
        "--name", profile.azure_resource_group,
        "--output", "json",
    ])
    if rc != 0:
        print(
            f"ERROR: Resource group '{profile.azure_resource_group}' was not found "
            "or you do not have access to it."
        )
        print("Check azure_resource_group in agent_profile.yaml and your subscription context.")
        sys.exit(1)

    # --- List resources in the resource group ---
    stdout, stderr, rc = _run_az([
        "resource", "list",
        "--resource-group", profile.azure_resource_group,
        "--output", "json",
    ])

    if rc != 0:
        bundle.collection_warnings.append(
            f"az resource list failed: {stderr.strip()}"
        )
        return bundle

    try:
        all_resources: list[dict] = json.loads(stdout)
    except json.JSONDecodeError as exc:
        bundle.collection_warnings.append(f"Could not parse az resource list output: {exc}")
        return bundle

    # --- Filter to agent-related resources ---
    agent_resources = [r for r in all_resources if _is_agent_resource(r, profile)]

    if not agent_resources:
        bundle.collection_warnings.append(
            f"No resources found in '{profile.azure_resource_group}' that match "
            f"agent_id='{profile.agent_id}', agentName='{profile.display_name}', "
            "or tag accountable_agents_demo='true'. "
            "Tag at least one resource to associate it with this agent."
        )

    for res in agent_resources:
        tags: dict[str, str] = res.get("tags") or {}
        missing = [t for t in profile.required_resource_tags if t not in tags]
        bundle.resources.append(
            AzureResourceEvidence(
                resource_id=res.get("id", ""),
                name=res.get("name", ""),
                type=res.get("type", ""),
                location=res.get("location", ""),
                tags=tags,
                missing_required_tags=missing,
            )
        )

    # --- Collect Azure Advisor recommendations (best-effort) ---
    stdout, stderr, rc = _run_az([
        "advisor", "recommendation", "list",
        "--resource-group", profile.azure_resource_group,
        "--output", "json",
    ])

    if rc != 0:
        bundle.collection_warnings.append(
            "Azure Advisor recommendations could not be retrieved "
            f"(az advisor may not be available or returned an error): {stderr.strip()}"
        )
    else:
        try:
            advisor_items: list[dict] = json.loads(stdout)
            for item in advisor_items:
                props = item.get("properties") or item
                bundle.advisor_findings.append(
                    AzureAdvisorFinding(
                        recommendation_id=item.get("name", ""),
                        category=props.get("category", ""),
                        impact=props.get("impact", ""),
                        impacted_resource_id=props.get("resourceMetadata", {}).get("resourceId", ""),
                        short_description=props.get("shortDescription", {}).get("problem", ""),
                    )
                )
        except json.JSONDecodeError as exc:
            bundle.collection_warnings.append(
                f"Could not parse az advisor output: {exc}"
            )

    return bundle
