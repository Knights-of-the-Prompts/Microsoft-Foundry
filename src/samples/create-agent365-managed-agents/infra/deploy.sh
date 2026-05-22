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

# Build override parameters
OVERRIDE_PARAMS="namePrefix=$NAME_PREFIX aiServicesName=$AI_SERVICES_NAME"
[[ -n "$LOCATION" ]] && OVERRIDE_PARAMS="$OVERRIDE_PARAMS location=$LOCATION"

az deployment group create \
  --name                 "$DEPLOYMENT_NAME" \
  --resource-group       "$AZURE_RESOURCE_GROUP_NAME" \
  --template-file        "$SCRIPT_DIR/main.bicep" \
  --parameters           "$SCRIPT_DIR/main.parameters.json" \
  --parameters           $OVERRIDE_PARAMS \
  --output               table

echo ""
echo "✅  Deployment complete."
echo ""

# Print workbook URL from outputs
WORKBOOK_URL=$(
  az deployment group show \
    --name           "$DEPLOYMENT_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP_NAME" \
    --query          "properties.outputs.workbookUrl.value" \
    --output         tsv 2>/dev/null || true
)
if [[ -n "$WORKBOOK_URL" ]]; then
  echo "  Azure Monitor Workbook:"
  echo "  $WORKBOOK_URL"
  echo ""
fi
