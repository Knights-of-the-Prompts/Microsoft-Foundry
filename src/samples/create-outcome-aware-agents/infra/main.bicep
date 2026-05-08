// Standalone deployment entry point for the Outcome-Aware Agent workshop.
// Provisions only the Azure Confidential Ledger needed by the value-ledger UI.
//
// Deploy with:
//   az group create -n rg-outcome-aware -l eastus
//   az deployment group create \
//     -g rg-outcome-aware \
//     -f main.bicep \
//     -p principalId=$(az ad signed-in-user show --query id -o tsv)

targetScope = 'resourceGroup'

@description('Azure region for the ledger.')
@allowed([
  'eastus'
  'westeurope'
  'australiaeast'
  'southeastasia'
])
param location string = 'eastus'

@description('Name of the Confidential Ledger. Must be globally unique.')
param ledgerName string = 'oaa-${uniqueString(resourceGroup().id)}'

@description('AAD object ID of the workshop user or app identity that will read/write entries.')
param principalId string

module ledger 'confidential-ledger.bicep' = {
  name: 'outcome-aware-ledger'
  params: {
    location: location
    ledgerName: ledgerName
    principalId: principalId
    tags: {
      workshop: 'outcome-aware-agents'
    }
  }
}

output ledgerName string = ledger.outputs.ledgerName
output ledgerUri string = ledger.outputs.ledgerUri
