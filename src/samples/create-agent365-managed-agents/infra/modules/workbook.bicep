@description('Name prefix for the workbook resource')
param workbookName string

@description('Display name shown in the Azure portal')
param workbookDisplayName string = 'ITHelpDeskAgent — Governance Dashboard'

@description('Location')
param location string = resourceGroup().location

var workbookContent = loadTextContent('../workbook.json')

resource workbook 'Microsoft.Insights/workbooks@2022-04-01' = {
  name: guid(workbookName, resourceGroup().id)
  location: location
  kind: 'shared'
  properties: {
    displayName:    workbookDisplayName
    serializedData: workbookContent
    version:        '1.0'
    sourceId:       'azure monitor'
    category:       'workbook'
  }
}

output workbookId  string = workbook.id
output workbookUrl string = 'https://portal.azure.com/#@${tenant().tenantId}/resource${workbook.id}/workbook'
