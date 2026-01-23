// Execute this main file to deploy Microsoft Foundry resources in the basic security configuration

// Parameters
@minLength(2)
@maxLength(12)
@description('Name for the AI resource and used to derive name of dependent resources.')
param aiFoundryName string = 'aiagents'

@description('Friendly name for your Microsoft Foundry resource')
param aiFoundryFriendlyName string = 'Agent Workshop AI Foundry resource'

@description('Description of your Microsoft Foundry resource displayed in AI Foundry')
param aiFoundryDescription string = 'This is an example AI Foundry resource for use in Microsoft Foundry.'

@description('Azure region used for the deployment of all resources.')
param location string = resourceGroup().location

@description('Set of tags to apply to all resources.')
param tags object = {}

@description('Project name')
param aiProjectName string = 'workshop-project'

@description('Project display name')
param aiProjectDisplayName string = 'Agent Workshop Project'

@description('Project description')
param aiProjectDescription string = 'Agent Workshop'

@description('Budget amount in USD for the resource group')
param budgetAmount int = 500

@description('Email addresses to receive budget alerts (optional)')
param budgetAlertEmails array = ['douwe.vande.ruit@capgemini.com']

@description('Whether to deploy the budget alert (requires subscription-level permissions)')
param deployBudgetAlert bool = false

@description('Whether to disable local authentication (API keys) in favor of keyless auth (Entra ID)')
param disableLocalAuth bool = true

// Variables
var name = toLower('${aiFoundryName}')

// Create a short, unique suffix, that will be unique to each resource group
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)

// Dependent resources for the Azure AI Hub
module aiDependencies 'modules/dependent-resources.bicep' = {
  name: 'dependencies-${name}-${uniqueSuffix}-deployment'
  params: {
    location: location
    storageName: 'st${name}${uniqueSuffix}'
    keyvaultName: 'kv-${name}-${uniqueSuffix}'
    applicationInsightsName: 'appi-${name}-${uniqueSuffix}'
    containerRegistryName: 'cr${name}${uniqueSuffix}'
    tags: tags
  }
}

// AI Services resource for AI models
module aiServices 'modules/ai-services.bicep' = {
  name: 'aiservices-${name}-${uniqueSuffix}-deployment'
  params: {
    aiServicesName: 'ais-${name}-${uniqueSuffix}'
    aiServicesFriendlyName: aiFoundryFriendlyName
    aiServicesDescription: aiFoundryDescription
    location: location
    tags: tags
    customSubDomainName: 'ais-${name}-${uniqueSuffix}'
    disableLocalAuth: disableLocalAuth
  }
}

// AI Foundry resource (Machine Learning Services workspace)
module aiHub 'modules/ai-hub.bicep' = {
  name: 'hub-${name}-${uniqueSuffix}-deployment'
  params: {
    aiHubName: 'aih-${name}-${uniqueSuffix}'
    aiHubFriendlyName: aiFoundryFriendlyName
    aiHubDescription: aiFoundryDescription
    location: location
    tags: tags
    applicationInsightsId: aiDependencies.outputs.applicationInsightsId
    containerRegistryId: aiDependencies.outputs.containerRegistryId
    keyVaultId: aiDependencies.outputs.keyvaultId
    storageAccountId: aiDependencies.outputs.storageId
    aiServicesId: aiServices.outputs.aiServicesId
    aiServicesTarget: aiServices.outputs.aiServicesEndpoint
  }
}

// AI Project resource (Machine Learning Services workspace with kind: Project)
module aiProject 'modules/ai-project.bicep' = {
  name: 'project-${name}-${uniqueSuffix}-deployment'
  params: {
    location: location
    tags: tags
    aiProjectName: 'aip-${name}-${uniqueSuffix}'
    aiProjectFriendlyName: 'Agent Workshop Project'
    aiProjectDescription: aiProjectDescription
    aiHubId: aiHub.outputs.aiHubId
  }
}

module gpt4oDeployment 'modules/aoai-model-deployment.bicep' = {
  name: 'gpt4o-${name}-${uniqueSuffix}-deployment'
  params: {
    openAIAccountId: aiServices.outputs.aiServicesId
    deploymentName: 'gpt4o'
    modelName: 'gpt-4o'
    capacity: 30
  }
  dependsOn: [
    aiProject
  ]
}

// module o3DeepResearchDeployment 'modules/aoai-model-deployment.bicep' = {
//   name: 'o3-deep-research-${name}-${uniqueSuffix}-deployment'
//   params: {
//     openAIAccountId: aiFoundry.outputs.aiFoundryId
//     deploymentName: 'o3-deep-research'
//     modelName: 'o3-deep-research'
//     modelVersion: '2025-06-26'
//     capacity: 250
//     versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
//     raiPolicyName: 'Microsoft.DefaultV2'
//   }
//   dependsOn: [
//     gpt4oDeployment
//   ]
// }

module budgetAlert 'modules/budget-alert.bicep' = if (deployBudgetAlert) {
  name: 'budget-${name}-${uniqueSuffix}-deployment'
  params: {
    budgetName: 'budget-${name}-${uniqueSuffix}'
    budgetAmount: budgetAmount
    alertEmails: budgetAlertEmails
  }
}

// Role assignment for AI Project to access AI Services
resource cognitiveServicesContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'
  scope: subscription()
}

module aiServiceRoleAssignment 'modules/role-assignment.bicep' = {
  name: 'role-${name}-${uniqueSuffix}-deployment'
  params: {
    principalId: aiProject.outputs.aiProjectPrincipalId
    roleDefinitionId: cognitiveServicesContributorRole.id
    aiServicesName: aiServices.outputs.aiServicesName
  }
}

// Outputs
output aiHubName string = aiHub.outputs.aiHubName
output aiProjectName string = aiProject.outputs.aiProjectName
output aiProjectWorkspaceId string = aiProject.outputs.aiProjectWorkspaceId
output aiServicesName string = aiServices.outputs.aiServicesName
output aiServicesEndpoint string = aiServices.outputs.aiServicesEndpoint
output aiProjectEndpoint string = aiServices.outputs.aiProjectEndpoint
output aiInferenceEndpoint string = aiServices.outputs.aiInferenceEndpoint
output location string = location
output resourceGroupName string = resourceGroup().name
