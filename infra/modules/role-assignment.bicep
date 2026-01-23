// Assigns Cognitive Services Contributor role to AI Project for accessing AI Services

@description('Principal ID to assign the role to')
param principalId string

@description('Role definition ID')
param roleDefinitionId string

@description('Name of the AI Services resource')
param aiServicesName string

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: aiServicesName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiServices
  name: guid(aiServices.id, principalId, roleDefinitionId)
  properties: {
    principalId: principalId
    roleDefinitionId: roleDefinitionId
    principalType: 'ServicePrincipal'
  }
}

output roleAssignmentId string = roleAssignment.id
