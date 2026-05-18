@description('Location for the export storage account')
param location string = resourceGroup().location
param environment string = 'demo'
param namePrefix string = 'aacost'

var exportSaName = toLower(concat(namePrefix, 'export', substring(uniqueString(resourceGroup().id, 'export'), 0, 8)))

resource exportStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: exportSaName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Enabled'
  }
  tags: {
    accountable_agents_demo: 'true'
    cost_category: 'platform'
    allocation_scope: 'platform'
    distribution_key: 'weighted_agent_usage'
    shared_service: 'true'
    purpose: 'cost-export-destination'
    owner: 'ai-platform-team'
    environment: environment
  }
}

// Blob container for cost exports
resource exportContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2021-09-01' = {
  parent: exportStorage
  name: 'default/cost-exports'
  properties: {}
}

output exportStorageName string = exportStorage.name
output exportStorageId string = exportStorage.id
output exportContainerName string = exportContainer.name
