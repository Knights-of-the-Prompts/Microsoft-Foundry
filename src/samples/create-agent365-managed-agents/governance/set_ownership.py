"""
Set Owner and Sponsor for the ITHelpDeskAgent.

Primary path — Azure resource tags on the AI Services account:
    PATCH https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/
          providers/Microsoft.CognitiveServices/accounts/{name}/
          providers/Microsoft.Resources/tags/default?api-version=2021-04-01

Tags written:
    agent-ITHelpDeskAgent-owner   = <UPN or object ID>
    agent-ITHelpDeskAgent-sponsor = <UPN or object ID>

These tags are visible in the Azure portal, Azure Resource Graph, and Cost
Management — forming the governance audit trail for the agent.

Secondary path (future, when agent is published to M365):
    PATCH https://graph.microsoft.com/beta/copilot/agentRegistrations/{AGENT_GUID}

Prerequisites:
    AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP_NAME, AI_SERVICES_NAME in .env
    AGENT_OWNER, AGENT_SPONSOR in .env
    (Optional) GOVERNANCE_APP_CLIENT_ID + GOVERNANCE_APP_CLIENT_SECRET for the
    Graph path — run governance/bootstrap_consent.py once as Global Admin.

Usage:
    python governance/set_ownership.py
"""

import asyncio
import base64
import json
import os
import re
import subprocess

import httpx
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from dotenv import load_dotenv

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(dotenv_path=_ENV)

AGENT_GUID        = os.getenv("AGENT_GUID", "")
AGENT_OWNER       = os.getenv("AGENT_OWNER", "")
AGENT_SPONSOR     = os.getenv("AGENT_SPONSOR", "")
AGENT_NAME        = "ITHelpDeskAgent"

SUBSCRIPTION_ID   = os.getenv("AZURE_SUBSCRIPTION_ID", "")
RESOURCE_GROUP    = os.getenv("AZURE_RESOURCE_GROUP_NAME", "")
AI_SERVICES_NAME  = os.getenv("AI_SERVICES_NAME", "")

_GOVERNANCE_CLIENT_ID     = os.getenv("GOVERNANCE_APP_CLIENT_ID", "")
_GOVERNANCE_CLIENT_SECRET = os.getenv("GOVERNANCE_APP_CLIENT_SECRET", "")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _decode_jwt(token: str) -> dict:
    """Decode JWT payload for display purposes (no signature validation)."""
    try:
        part = token.split(".")[1]
        part += "=" * (4 - len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part))
    except Exception:
        return {}


async def _resolve_user(upn_or_id: str, bearer: str) -> str:
    """Return Entra object ID for a UPN. Returns unchanged if already a GUID."""
    if re.match(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", upn_or_id, re.IGNORECASE):
        return upn_or_id
    async with httpx.AsyncClient() as http:
        resp = await http.get(
            f"https://graph.microsoft.com/v1.0/users/{upn_or_id}",
            headers={"Authorization": f"Bearer {bearer}"},
        )
        if resp.status_code == 200:
            return resp.json()["id"]
    return upn_or_id


async def _set_azure_tags(owner: str, sponsor: str) -> bool:
    """
    Merge owner/sponsor tags onto the AI Services resource.
    Returns True on success.
    """
    if not all([SUBSCRIPTION_ID, RESOURCE_GROUP, AI_SERVICES_NAME]):
        print("  Skipping Azure tags — AZURE_SUBSCRIPTION_ID / AZURE_RESOURCE_GROUP_NAME"
              " / AI_SERVICES_NAME not set in .env")
        return False

    credential = DefaultAzureCredential()
    token = credential.get_token("https://management.azure.com/.default")
    bearer = token.token

    url = (
        f"https://management.azure.com"
        f"/subscriptions/{SUBSCRIPTION_ID}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{AI_SERVICES_NAME}"
        f"/providers/Microsoft.Resources/tags/default"
        f"?api-version=2021-04-01"
    )
    tags: dict = {}
    if owner:
        tags[f"agent-{AGENT_NAME}-owner"] = owner
    if sponsor:
        tags[f"agent-{AGENT_NAME}-sponsor"] = sponsor

    body = {"operation": "Merge", "properties": {"tags": tags}}
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as http:
        resp = await http.patch(url, headers=headers, json=body)

    if resp.status_code in (200, 201):
        print("  Azure resource tags updated successfully.")
        print(f"    Subscription : {SUBSCRIPTION_ID}")
        print(f"    Resource     : {AI_SERVICES_NAME}  ({RESOURCE_GROUP})")
        for k, v in tags.items():
            print(f"    Tag          : {k} = {v}")
        print()
        print("  View in Azure portal:")
        print(f"  https://portal.azure.com/#resource/subscriptions/{SUBSCRIPTION_ID}"
              f"/resourceGroups/{RESOURCE_GROUP}"
              f"/providers/Microsoft.CognitiveServices/accounts/{AI_SERVICES_NAME}/tags")
        return True
    else:
        print(f"  Azure tags PATCH returned HTTP {resp.status_code}: {resp.text[:300]}")
        return False


def _get_graph_bearer() -> str | None:
    """Acquire a Graph token using client_credentials. Returns None if not configured."""
    if not _GOVERNANCE_CLIENT_ID or not _GOVERNANCE_CLIENT_SECRET:
        return None
    result = subprocess.run(
        ["az", "account", "show", "--query", "tenantId", "--output", "tsv"],
        capture_output=True, text=True,
    )
    tenant_id = result.stdout.strip()
    if not tenant_id:
        return None
    credential = ClientSecretCredential(tenant_id, _GOVERNANCE_CLIENT_ID, _GOVERNANCE_CLIENT_SECRET)
    return credential.get_token("https://graph.microsoft.com/.default").token


async def _try_graph_patch(owner_oid: str | None, sponsor_oid: str | None,
                            bearer: str) -> None:
    """
    Best-effort PATCH to Graph agentRegistrations.
    Only works when the agent has been published to the M365 Copilot registry.
    """
    if not AGENT_GUID:
        return

    payload: dict = {}
    if owner_oid:
        payload["ownerUserId"] = owner_oid
    if sponsor_oid:
        payload["sponsorUserId"] = sponsor_oid

    url = f"https://graph.microsoft.com/beta/copilot/agentRegistrations/{AGENT_GUID}"
    headers = {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as http:
        resp = await http.patch(url, headers=headers, json=payload)

    if resp.status_code in (200, 204):
        print("  M365 agentRegistrations also updated (agent is published to M365 registry).")
    elif resp.status_code == 500:
        print("  M365 agentRegistrations: agent not yet in M365 registry (HTTP 500 — expected"
              " for SDK-created agents not published via M365 publishing flow).")
    else:
        print(f"  M365 agentRegistrations: HTTP {resp.status_code} — {resp.text[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def set_ownership() -> None:
    if not AGENT_OWNER and not AGENT_SPONSOR:
        print("Nothing to set: both AGENT_OWNER and AGENT_SPONSOR are empty in .env.")
        return

    print(f"Setting governance for agent: {AGENT_NAME}")
    if AGENT_OWNER:
        print(f"  Owner   : {AGENT_OWNER}")
    if AGENT_SPONSOR:
        print(f"  Sponsor : {AGENT_SPONSOR}")
    print()

    # ── Primary: Azure resource tags ──────────────────────────────────────────
    print("── Primary: Azure resource tags ─────────────────────────────────────")
    success = await _set_azure_tags(AGENT_OWNER, AGENT_SPONSOR)
    if not success:
        print("  Azure tag update failed. Check credentials and .env values above.")

    # ── Secondary: M365 Graph agentRegistrations (best-effort) ────────────────
    print()
    print("── Secondary: M365 agentRegistrations (best-effort) ─────────────────")
    graph_bearer = _get_graph_bearer()
    if not graph_bearer:
        print("  Skipping — GOVERNANCE_APP_CLIENT_ID / GOVERNANCE_APP_CLIENT_SECRET not"
              " set. Run governance/bootstrap_consent.py to enable this path.")
    else:
        # Resolve UPNs to object IDs for the Graph payload
        owner_oid   = await _resolve_user(AGENT_OWNER,   graph_bearer) if AGENT_OWNER   else None
        sponsor_oid = await _resolve_user(AGENT_SPONSOR, graph_bearer) if AGENT_SPONSOR else None
        await _try_graph_patch(owner_oid, sponsor_oid, graph_bearer)


if __name__ == "__main__":
    asyncio.run(set_ownership())

