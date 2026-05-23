@description('Name of the Log Analytics workspace')
param workspaceName string

@description('Location for the workspace')
param location string = resourceGroup().location

@description('Retention period in days (30–730)')
@minValue(30)
@maxValue(730)
param retentionDays int = 30

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: retentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
  }
}

output workspaceId   string = logAnalytics.id
output workspaceName string = logAnalytics.name
output customerId    string = logAnalytics.properties.customerId
