// Creates an Azure AI Project resource (Microsoft.MachineLearningServices workspace)

@description('Azure region of the deployment')
param location string

@description('Tags to add to the resources')
param tags object = {}

@description('Project name')
param aiProjectName string

@description('Project display name')
param aiProjectFriendlyName string = aiProjectName

@description('Project description')
param aiProjectDescription string = 'Microsoft Foundry project'

@description('Resource ID of the parent AI Hub resource')
param aiHubId string

resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-10-01-preview' = {
  name: aiProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
  kind: 'Project'
  properties: {
    friendlyName: aiProjectFriendlyName
    description: aiProjectDescription
    hubResourceId: aiHubId
  }
}

output aiProjectId string = aiProject.id
output aiProjectName string = aiProject.name
output aiProjectPrincipalId string = aiProject.identity.principalId
output aiProjectWorkspaceId string = aiProject.properties.workspaceId
