@description('Name prefix for all deployed resources')
param namePrefix string = 'a365agent'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Name of the existing Azure AI Services resource (used for diagnostic settings)')
param aiServicesName string

@description('Retention days for the Log Analytics workspace')
param retentionDays int = 30

// ── Log Analytics ─────────────────────────────────────────────────────────────
module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'logAnalyticsDeploy'
  params: {
    workspaceName: '${namePrefix}-logs'
    location:      location
    retentionDays: retentionDays
  }
}

// ── Application Insights ──────────────────────────────────────────────────────
module appInsights 'modules/app-insights.bicep' = {
  name: 'appInsightsDeploy'
  params: {
    appInsightsName:          '${namePrefix}-appinsights'
    logAnalyticsWorkspaceId:  logAnalytics.outputs.workspaceId
    location:                 location
  }
}

// ── Diagnostic Settings (routes AI Services metrics to Log Analytics) ─────────
module diagnosticSettings 'modules/diagnostic-settings.bicep' = {
  name: 'diagnosticSettingsDeploy'
  params: {
    aiServicesName:          aiServicesName
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
  }
}

// ── Azure Monitor Workbook ────────────────────────────────────────────────────
module workbook 'modules/workbook.bicep' = {
  name: 'workbookDeploy'
  params: {
    workbookName: '${namePrefix}-governance-workbook'
    location:     location
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────
output logAnalyticsWorkspaceId    string = logAnalytics.outputs.workspaceId
output appInsightsConnectionString string = appInsights.outputs.connectionString
output workbookId                 string = workbook.outputs.workbookId
output workbookUrl                string = workbook.outputs.workbookUrl
