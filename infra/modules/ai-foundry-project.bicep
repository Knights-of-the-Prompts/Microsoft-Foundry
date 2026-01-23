// Creates a Microsoft Foundry Project resource (CognitiveServices child resource)

@description('Parent AI Foundry resource name')
param aiFoundryResourceName string

@description('Project name')
param projectName string

@description('Azure region of the deployment')
param location string

@description('Tags to add to the resources')
param tags object = {}

@description('Project display name')
param projectDisplayName string = projectName

@description('Project description')
param projectDescription string = 'Microsoft Foundry AI Project'

resource aiFoundryResource 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiFoundryResourceName
}

resource aiFoundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: aiFoundryResource
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectDisplayName
    description: projectDescription
  }
}

output projectId string = aiFoundryProject.id
output projectName string = aiFoundryProject.name
output projectPrincipalId string = aiFoundryProject.identity.principalId
output projectEndpoint string = 'https://${aiFoundryResource.properties.customSubDomainName}.services.ai.azure.com/api/projects/${aiFoundryProject.name}'
