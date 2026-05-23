#!/usr/bin/env bash
# Deploy the Agent 365 monitoring infrastructure
# (Log Analytics, App Insights, Diagnostic Settings, Azure Monitor Workbook)
#
# Prerequisites:
#   az login   (or set AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID)
#
# Required environment variables (set in .env or export manually):
#   AZURE_SUBSCRIPTION_ID      — target subscription
#   AZURE_RESOURCE_GROUP_NAME  — resource group where AI Services already lives
#   AI_SERVICES_NAME           — name of the existing Cognitive Services / AI Services resource
#
# Optional:
#   AZURE_LOCATION             — Azure region (default: resource group location)
#   NAME_PREFIX                — resource name prefix  (default: a365agent)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Ensure bicep is available ──────────────────────────────────────────────────
# Azure CLI 2.20+ ships with 'az bicep'; older installs need the standalone binary.
if az bicep version &>/dev/null 2>&1; then
  BICEP_CMD="az bicep build --file"
  _compile_bicep() { az bicep build --file "$1" --outfile "$2"; }
elif command -v bicep &>/dev/null; then
  _compile_bicep() { bicep build "$1" --outfile "$2"; }
else
  echo "bicep CLI not found — downloading standalone binary to /tmp/bicep ..."
  curl -sSfLo /tmp/bicep \
    "https://github.com/Azure/bicep/releases/latest/download/bicep-linux-x64"
  chmod +x /tmp/bicep
  _compile_bicep() { /tmp/bicep build "$1" --outfile "$2"; }
fi

# Load .env from the sample root if present
ENV_FILE="$(dirname "$SCRIPT_DIR")/.env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

# Validate required vars
for var in AZURE_SUBSCRIPTION_ID AZURE_RESOURCE_GROUP_NAME AI_SERVICES_NAME; do
  if [[ -z "${!var:-}" ]]; then
    echo "Error: '$var' is not set. Add it to .env or export it before running this script."
    exit 1
  fi
done

LOCATION="${AZURE_LOCATION:-}"
NAME_PREFIX="${NAME_PREFIX:-a365agent}"
DEPLOYMENT_NAME="a365agent-monitoring-$(date +%Y%m%d%H%M%S)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Deploying Agent 365 monitoring infrastructure"
echo "  Subscription : $AZURE_SUBSCRIPTION_ID"
echo "  Resource group: $AZURE_RESOURCE_GROUP_NAME"
echo "  AI Services  : $AI_SERVICES_NAME"
echo "  Name prefix  : $NAME_PREFIX"
[[ -n "$LOCATION" ]] && echo "  Location     : $LOCATION"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"

# Compile Bicep → ARM JSON (handles old Azure CLI that lacks native Bicep support)
COMPILED_TEMPLATE="$(mktemp /tmp/a365agent-main.XXXXXX.json)"
DEPLOY_BODY="$(mktemp /tmp/a365agent-body.XXXXXX.json)"
trap 'rm -f "$COMPILED_TEMPLATE" "$DEPLOY_BODY"' EXIT
echo "Compiling Bicep template ..."
_compile_bicep "$SCRIPT_DIR/main.bicep" "$COMPILED_TEMPLATE"

# Build deployment body (az deployment group create is broken on Azure CLI <2.20)
python3 - <<PYEOF
import json, os

with open("$COMPILED_TEMPLATE") as f:
    template = json.load(f)

params = {
    "namePrefix":     {"value": os.environ.get("NAME_PREFIX", "a365agent")},
    "aiServicesName": {"value": os.environ["AI_SERVICES_NAME"]},
}
loc = os.environ.get("AZURE_LOCATION", "")
if loc:
    params["location"] = {"value": loc}

# Merge values from main.parameters.json (lower priority than overrides above)
params_file = "$SCRIPT_DIR/main.parameters.json"
try:
    with open(params_file) as f:
        file_params = json.load(f).get("parameters", {})
    for k, v in file_params.items():
        # Skip blank values from the parameters file — let the template default apply
        if k not in params and v.get("value", None) not in ("", None):
            params[k] = v
except Exception:
    pass

body = {"properties": {"mode": "Incremental", "template": template, "parameters": params}}
with open("$DEPLOY_BODY", "w") as f:
    json.dump(body, f)
PYEOF

DEPLOY_URL="https://management.azure.com/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${AZURE_RESOURCE_GROUP_NAME}/providers/Microsoft.Resources/deployments/${DEPLOYMENT_NAME}?api-version=2021-04-01"

echo "Submitting deployment ..."
az rest --method PUT --url "$DEPLOY_URL" --body "@$DEPLOY_BODY" --output none

# Poll until the deployment finishes
echo "Waiting for deployment to complete ..."
while true; do
  STATE=$(az rest --method GET --url "$DEPLOY_URL" --output json 2>/dev/null \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['properties']['provisioningState'])" 2>/dev/null)
  echo "  State: $STATE"
  case "$STATE" in
    Succeeded)  break ;;
    Failed|Canceled)
      echo "Deployment $STATE."
      az rest --method GET --url "$DEPLOY_URL" --output json 2>/dev/null \
        | python3 -c "import json,sys; d=json.load(sys.stdin); [print(e) for e in d.get('properties',{}).get('error',{}).get('details',[])]" 2>/dev/null
      exit 1 ;;
    *) sleep 10 ;;
  esac
done

echo ""
echo "✅  Deployment complete."
echo ""

# Print workbook URL from outputs
WORKBOOK_URL=$(
  az rest --method GET --url "$DEPLOY_URL" --output json 2>/dev/null \
    | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('properties', {}).get('outputs', {}).get('workbookUrl', {}).get('value', ''))
" 2>/dev/null || true
)
if [[ -n "$WORKBOOK_URL" ]]; then
  echo "  Azure Monitor Workbook:"
  echo "  $WORKBOOK_URL"
  echo ""
fi
