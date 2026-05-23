@description('Name of the Application Insights instance')
param appInsightsName string

@description('Resource ID of the Log Analytics workspace to link to')
param logAnalyticsWorkspaceId string

@description('Location')
param location string = resourceGroup().location

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspaceId
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output appInsightsId        string = appInsights.id
output instrumentationKey   string = appInsights.properties.InstrumentationKey
output connectionString     string = appInsights.properties.ConnectionString
