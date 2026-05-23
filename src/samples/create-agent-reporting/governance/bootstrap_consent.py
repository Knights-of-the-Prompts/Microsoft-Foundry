"""
One-time admin consent bootstrap for set_ownership.py.

Run this ONCE as a Global Admin to:
  1. Create a custom Entra app registration (public client, device-code flow)
  2. Add the AgentRegistration.ReadWrite.All delegated Graph permission
  3. Create its service principal
  4. Grant tenant-wide admin consent

The resulting client ID is written to .env as GOVERNANCE_APP_CLIENT_ID.
After this, any user can run set_ownership.py with a one-time device-code login.

Usage:
    python governance/bootstrap_consent.py
"""

import json
import os
import subprocess
import sys
import time

_GRAPH_APP_ID   = "00000003-0000-0000-c000-000000000000"   # Microsoft Graph
_SCOPE_ID       = "20f263bf-7d50-4e66-912c-16b4b4194fd4"   # AgentRegistration.ReadWrite.All scope GUID
_SCOPE_VALUE    = "AgentRegistration.ReadWrite.All"
_APP_NAME       = "A365AgentGovernanceTool"
_ENV_VAR        = "GOVERNANCE_APP_CLIENT_ID"
_ENV_PATH       = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")


def _az(*args) -> dict | list | str:
    result = subprocess.run(
        ["az"] + list(args) + ["--output", "json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def _update_env(client_id: str) -> None:
    """Write or update GOVERNANCE_APP_CLIENT_ID in .env."""
    if not os.path.exists(_ENV_PATH):
        print(f"  Warning: .env not found at {_ENV_PATH}")
        print(f"  Add manually:  {_ENV_VAR}={client_id}")
        return
    with open(_ENV_PATH) as f:
        lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{_ENV_VAR}=") or line.startswith(f"# {_ENV_VAR}="):
            lines[i] = f"{_ENV_VAR}={client_id}\n"
            found = True
            break
    if not found:
        lines.append(f"{_ENV_VAR}={client_id}\n")
    with open(_ENV_PATH, "w") as f:
        f.writelines(lines)
    print(f"  Written to .env: {_ENV_VAR}={client_id}")


def main() -> None:
    print("Agent 365 consent bootstrap")
    print()

    # ── 1. Check for existing app ─────────────────────────────────────────────
    print(f"[1/4] Checking for existing '{_APP_NAME}' app registration …")
    existing = _az(
        "rest", "--method", "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/applications"
        f"?$filter=displayName+eq+'{_APP_NAME}'&$select=appId,id",
    )
    apps = existing.get("value", [])

    if apps:
        client_id   = apps[0]["appId"]
        app_obj_id  = apps[0]["id"]
        print(f"     Already exists (clientId: {client_id}) — reusing.")
    else:
        print(f"     Creating '{_APP_NAME}' via Graph REST …")
        app = _az(
            "rest", "--method", "POST",
            "--url", "https://graph.microsoft.com/v1.0/applications",
            "--headers", "Content-Type=application/json",
            "--body", json.dumps({
                "displayName": _APP_NAME,
                "publicClient": {
                    "redirectUris": [
                        "https://login.microsoftonline.com/common/oauth2/nativeclient"
                    ]
                },
                "isFallbackPublicClient": True,
            }),
        )
        client_id   = app["appId"]
        app_obj_id  = app["id"]
        print(f"     Created (clientId: {client_id})")

    # ── 2. Add Graph permission ───────────────────────────────────────────────
    print(f"\n[2/4] Adding {_SCOPE_VALUE} permission …")
    # Check if already added
    app_detail = _az(
        "rest", "--method", "GET",
        "--url", f"https://graph.microsoft.com/v1.0/applications/{app_obj_id}?$select=requiredResourceAccess",
    )
    already_has = any(
        any(p["id"] == _SCOPE_ID for p in rra.get("resourceAccess", []))
        for rra in app_detail.get("requiredResourceAccess", [])
    )
    if already_has:
        print("     Already configured.")
    else:
        _az(
            "ad", "app", "permission", "add",
            "--id", client_id,
            "--api", _GRAPH_APP_ID,
            "--api-permissions", f"{_SCOPE_ID}=Scope",
        )
        print("     Added.")

    # ── 3. Ensure service principal exists ────────────────────────────────────
    print(f"\n[3/4] Ensuring service principal exists …")
    sp_resp = _az(
        "rest", "--method", "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/servicePrincipals"
        f"?$filter=appId+eq+'{client_id}'&$select=id",
    )
    if sp_resp.get("value"):
        print(f"     Already exists.")
    else:
        _az("ad", "sp", "create", "--id", client_id)
        print("     Created.")
        time.sleep(5)  # brief wait for SP propagation

    # ── 4. Grant admin consent ────────────────────────────────────────────────
    print(f"\n[4/4] Granting admin consent …")
    try:
        _az("ad", "app", "permission", "admin-consent", "--id", client_id)
        print("     Granted.")
    except RuntimeError as exc:
        if "Insufficient privileges" in str(exc):
            print("     ✗ Insufficient privileges — a Global Admin must run this script.")
            sys.exit(1)
        raise

    # ── Done ──────────────────────────────────────────────────────────────────
    print()
    _update_env(client_id)
    print()
    print("✅  Bootstrap complete.")
    print("    Run:  python governance/set_ownership.py")


if __name__ == "__main__":
    main()


import subprocess
import json
import sys

_AZURE_CLI_APP_ID  = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_GRAPH_APP_ID      = "00000003-0000-0000-c000-000000000000"
_REQUIRED_SCOPE    = "AgentRegistration.ReadWrite.All"


def _az(args: list[str]) -> dict | list | str:
    result = subprocess.run(
        ["az"] + args + ["--output", "json"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return result.stdout.strip()


def main() -> None:
    print("Agent 365 consent bootstrap")
    print()

    # ── 1. Ensure Azure CLI SP exists in tenant ───────────────────────────────
    print(f"[1/3] Checking for Azure CLI SP ({_AZURE_CLI_APP_ID}) …")
    existing = _az([
        "rest", "--method", "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/servicePrincipals"
        f"?$filter=appId+eq+'{_AZURE_CLI_APP_ID}'&$select=id,displayName",
    ])
    sps = existing.get("value", [])
    if sps:
        cli_sp_id = sps[0]["id"]
        print(f"     Already exists (id: {cli_sp_id})")
    else:
        print("     Not found — creating …")
        sp = _az(["ad", "sp", "create", "--id", _AZURE_CLI_APP_ID])
        cli_sp_id = sp["id"]
        print(f"     Created (id: {cli_sp_id})")

    # ── 2. Get Microsoft Graph SP id ──────────────────────────────────────────
    print(f"\n[2/3] Resolving Microsoft Graph SP ({_GRAPH_APP_ID}) …")
    graph_resp = _az([
        "rest", "--method", "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/servicePrincipals"
        f"?$filter=appId+eq+'{_GRAPH_APP_ID}'&$select=id",
    ])
    graph_sp_id = graph_resp["value"][0]["id"]
    print(f"     id: {graph_sp_id}")

    # ── 3. Grant admin consent (idempotent) ───────────────────────────────────
    print(f"\n[3/3] Granting admin consent for '{_REQUIRED_SCOPE}' …")

    # Check if a grant already exists
    grants = _az([
        "rest", "--method", "GET",
        "--url",
        f"https://graph.microsoft.com/v1.0/oauth2PermissionGrants"
        f"?$filter=clientId+eq+'{cli_sp_id}'+and+resourceId+eq+'{graph_sp_id}'",
    ])
    for g in grants.get("value", []):
        if _REQUIRED_SCOPE in g.get("scope", "").split():
            print("     Admin consent already granted — nothing to do.")
            print()
            print("✅  Bootstrap complete.")
            return

    # Create the grant
    _az([
        "rest", "--method", "POST",
        "--url", "https://graph.microsoft.com/v1.0/oauth2PermissionGrants",
        "--headers", "Content-Type=application/json",
        "--body",
        json.dumps({
            "clientId":    cli_sp_id,
            "consentType": "AllPrincipals",
            "resourceId":  graph_sp_id,
            "scope":       _REQUIRED_SCOPE,
        }),
    ])
    print("     Granted.")
    print()
    print("✅  Bootstrap complete.")
    print("    Any user can now run  python governance/set_ownership.py")
    print("    using the device-code login prompt.")


if __name__ == "__main__":
    main()
