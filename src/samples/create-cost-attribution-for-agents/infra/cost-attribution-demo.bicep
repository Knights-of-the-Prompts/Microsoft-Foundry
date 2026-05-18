@description('Location for all resources')
param location string = resourceGroup().location
param environment string = 'demo'
param namePrefix string = 'aacost'

// deterministic, short unique names per resource
var salesSaName = toLower(concat(namePrefix, 'sa', substring(uniqueString(resourceGroup().id, 'sales'), 0, 8)))
var supportSaName = toLower(concat(namePrefix, 'sa', substring(uniqueString(resourceGroup().id, 'support'), 0, 8)))
var platformSaName = toLower(concat(namePrefix, 'sa', substring(uniqueString(resourceGroup().id, 'platform'), 0, 8)))
var unallocatedSaName = toLower(concat(namePrefix, 'sa', substring(uniqueString(resourceGroup().id, 'unallocated'), 0, 8)))
var logWorkspaceName = toLower(concat(namePrefix, '-law-', substring(uniqueString(resourceGroup().id, 'law'), 0, 6)))

// Low-cost storage for direct costs (sales)
resource salesStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: salesSaName
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
    cost_category: 'direct'
    allocation_scope: 'direct'
    agent_id: 'sales-followup-agent'
    workload_id: 'crm-opportunity-followup'
    business_process: 'sales'
    value_stream: 'revenue-growth'
    owner: 'ai-platform-team'
    environment: environment
  }
}

// Low-cost storage for direct costs (support)
resource supportStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: supportSaName
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
    cost_category: 'direct'
    allocation_scope: 'direct'
    agent_id: 'support-resolution-agent'
    workload_id: 'incident-resolution'
    business_process: 'support'
    value_stream: 'customer-retention'
    owner: 'ai-platform-team'
    environment: environment
  }
}

// Indirect shared service: Log Analytics workspace (low-cost SKU)
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2020-08-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
  tags: {
    accountable_agents_demo: 'true'
    cost_category: 'indirect'
    allocation_scope: 'indirect'
    distribution_key: 'log_volume_gb'
    shared_service: 'true'
    owner: 'ai-platform-team'
    environment: environment
  }
}

// Platform shared storage
resource platformStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: platformSaName
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
    owner: 'ai-platform-team'
    environment: environment
  }
}

// Intentionally unallocated resource (missing attribution tags)
resource unallocatedStorage 'Microsoft.Storage/storageAccounts@2022-09-01' = {
  name: unallocatedSaName
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
    environment: environment
  }
}

output salesStorageName string = salesStorage.name
output salesStorageId string = salesStorage.id
output supportStorageName string = supportStorage.name
output supportStorageId string = supportStorage.id
output logAnalyticsName string = logAnalytics.name
output logAnalyticsId string = logAnalytics.id
output platformStorageName string = platformStorage.name
output platformStorageId string = platformStorage.id
output unallocatedStorageName string = unallocatedStorage.name
output unallocatedStorageId string = unallocatedStorage.id

output mapping object = {
  sales: 'direct'
  support: 'direct'
  logAnalytics: 'indirect'
  platformStorage: 'platform'
  unallocated: 'unallocated'
}
