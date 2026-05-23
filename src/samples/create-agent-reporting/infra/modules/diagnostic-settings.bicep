@description('Name of the existing Azure AI Services / Cognitive Services resource')
param aiServicesName string

@description('Resource ID of the Log Analytics workspace to send diagnostics to')
param logAnalyticsWorkspaceId string

// Reference the existing AI Services resource by name
resource aiServices 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: aiServicesName
}

resource diagnosticSettings 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'a365agent-diag'
  scope: aiServices
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
        retentionPolicy: {
          enabled: false
          days: 0
        }
      }
    ]
  }
}

output diagnosticSettingsId string = diagnosticSettings.id
