#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Optionally load env vars from src/workshop/.env
ENV_FILE="$SCRIPT_DIR/../../workshop/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env from $ENV_FILE"
  # shellcheck disable=SC1090
  set -o allexport
  source "$ENV_FILE"
  set +o allexport
fi

AZ_RG_NAME="${AZURE_RESOURCE_GROUP_NAME:-rg-accountable-agents-cost-demo}"
LOCATION="${LOCATION:-westeurope}"
ENVIRONMENT="${ENVIRONMENT:-demo}"
NAME_PREFIX="${NAME_PREFIX:-aacost}"
DEPLOY_NAME="${NAME_PREFIX}-deploy"

echo "Resource group: $AZ_RG_NAME"
echo "Location: $LOCATION"

echo "Creating resource group (if needed)..."
az group create --name "$AZ_RG_NAME" --location "$LOCATION" >/dev/null

echo "Deploying cost-attribution-demo.bicep to resource group $AZ_RG_NAME"
az deployment group create \
  --resource-group "$AZ_RG_NAME" \
  --name "$DEPLOY_NAME" \
  --template-file "$SCRIPT_DIR/cost-attribution-demo.bicep" \
  --parameters namePrefix="$NAME_PREFIX" environment="$ENVIRONMENT" \
  --output json >/dev/null

echo "Deployment outputs:"
az deployment group show --resource-group "$AZ_RG_NAME" --name "$DEPLOY_NAME" --query "properties.outputs" -o json

if [[ "${1:-}" == "--with-export-storage" ]]; then
  echo "Deploying cost-export-storage.bicep"
  az deployment group create \
    --resource-group "$AZ_RG_NAME" \
    --name "${DEPLOY_NAME}-export" \
    --template-file "$SCRIPT_DIR/cost-export-storage.bicep" \
    --parameters namePrefix="$NAME_PREFIX" environment="$ENVIRONMENT" \
    --output json >/dev/null

  az deployment group show --resource-group "$AZ_RG_NAME" --name "${DEPLOY_NAME}-export" --query "properties.outputs" -o json
fi

cat <<EOF
Info:
- The Bicep templates create low-cost Storage Accounts and a Log Analytics workspace.
- Azure Cost Management usage/export data may be delayed (up to 24-48 hours).
- Tags are used to map resources to cost categories; no secrets are stored in tags.

To cleanup (delete the entire demo Resource Group):
  az group delete --name "$AZ_RG_NAME" --yes --no-wait

EOF
