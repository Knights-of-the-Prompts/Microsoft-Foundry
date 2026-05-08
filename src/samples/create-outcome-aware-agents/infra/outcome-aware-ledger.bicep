// Standalone deployment for the Outcome-Aware Agent workshop.
// Provisions an Azure Confidential Ledger for tamper-evident, append-only
// storage of value-attribution entries, and grants the supplied principal
// the Administrator role on it.
//
// Uses ledgerType 'Public' to keep the workshop lightweight: no consortium
// certificate management is required, and access is governed by AAD role
// assignments via the ledger's built-in role model.
//
// Deploy with:
//   az group create -n rg-outcome-aware -l swedencentral
//   az deployment group create \
//     -g rg-outcome-aware \
//     -n outcome-aware-ledger \
//     -f outcome-aware-ledger.bicep \
//     -p principalId=$(az ad signed-in-user show --query id -o tsv)

targetScope = 'resourceGroup'

@description('Azure region for the ledger. ACL is only available in a subset of regions.')
@allowed([
  'swedencentral'
  'eastus'
  'westeurope'
  'australiaeast'
  'southeastasia'
])
param location string = 'swedencentral'

@description('Name of the Confidential Ledger (3-24 chars, lowercase letters and numbers). Must be globally unique.')
@minLength(3)
@maxLength(24)
param ledgerName string = 'oaa-${uniqueString(resourceGroup().id)}'

@description('AAD object ID of the workshop user or app identity that will read/write entries.')
param principalId string

@description('Tags to apply to the ledger resource.')
param tags object = {
  workshop: 'outcome-aware-agents'
}

resource ledger 'Microsoft.ConfidentialLedger/ledgers@2023-06-28-preview' = {
  name: ledgerName
  location: location
  tags: tags
  properties: {
    ledgerType: 'Public'
    aadBasedSecurityPrincipals: [
      {
        principalId: principalId
        tenantId: subscription().tenantId
        ledgerRoleName: 'Administrator'
      }
    ]
  }
}

output ledgerName string = ledger.name
output ledgerUri string = ledger.properties.ledgerUri
output ledgerId string = ledger.id
