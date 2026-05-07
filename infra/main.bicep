// Execute this main file to deploy Microsoft Foundry resources with the modern CognitiveServices architecture

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
param aiProjectDescription string = 'Agent Workshop for Microsoft Foundry'

@description('Budget amount in USD for the resource group')
param budgetAmount int = 500

@description('Email addresses to receive budget alerts (optional)')
param budgetAlertEmails array = []

@description('Whether to deploy the budget alert (requires subscription-level permissions)')
param deployBudgetAlert bool = false

@description('Whether to disable local authentication (API keys) in favor of keyless auth (Entra ID)')
param disableLocalAuth bool = true

// Variables
var name = toLower('${aiFoundryName}')

// Create a short, unique suffix, that will be unique to each resource group
var uniqueSuffix = substring(uniqueString(resourceGroup().id), 0, 4)

// Build the AI Foundry account name once and reuse it for the resource
// name and custom subdomain to keep naming consistent.
var aiFoundryResourceName = 'aif-${name}-${uniqueSuffix}'

// Microsoft Foundry resource (CognitiveServices AIServices account)
module aiFoundry 'modules/ai-foundry.bicep' = {
  name: 'foundry-${name}-${uniqueSuffix}-deployment'
  params: {
    aiFoundryName: aiFoundryResourceName
    aiFoundryFriendlyName: aiFoundryFriendlyName
    aiFoundryDescription: aiFoundryDescription
    location: location
    tags: tags
    customSubDomainName: aiFoundryResourceName
    disableLocalAuth: disableLocalAuth
  }
}

// Microsoft Foundry Project (CognitiveServices child resource)
module aiProject 'modules/ai-foundry-project.bicep' = {
  name: 'project-${name}-${uniqueSuffix}-deployment'
  params: {
    aiFoundryResourceName: aiFoundry.outputs.aiFoundryName
    projectName: aiProjectName
    projectDisplayName: aiProjectDisplayName
    projectDescription: aiProjectDescription
    location: location
    tags: tags
  }
}

// GPT-4o model deployment
module gpt4oDeployment 'modules/aoai-model-deployment.bicep' = {
  name: 'gpt4o-${name}-${uniqueSuffix}-deployment'
  params: {
    openAIAccountId: aiFoundry.outputs.aiFoundryId
    deploymentName: 'gpt4o'
    modelName: 'gpt-4o'
    capacity: 30
  }
}

// Optional: Budget alert
module budgetAlert 'modules/budget-alert.bicep' = if (deployBudgetAlert) {
  name: 'budget-${name}-${uniqueSuffix}-deployment'
  params: {
    budgetName: 'budget-${name}-${uniqueSuffix}'
    budgetAmount: budgetAmount
    alertEmails: budgetAlertEmails
  }
}

// Role assignment for AI Project to access AI Foundry
resource cognitiveServicesContributorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' existing = {
  name: '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68'
  scope: subscription()
}

module aiProjectRoleAssignment 'modules/role-assignment.bicep' = {
  name: 'role-${name}-${uniqueSuffix}-deployment'
  params: {
    principalId: aiProject.outputs.projectPrincipalId
    roleDefinitionId: cognitiveServicesContributorRole.id
    aiServicesName: aiFoundry.outputs.aiFoundryName
  }
}

// Outputs
output location string = location
output resourceGroupName string = resourceGroup().name
output aiFoundryName string = aiFoundry.outputs.aiFoundryName
output aiFoundryId string = aiFoundry.outputs.aiFoundryId
output aiFoundryEndpoint string = aiFoundry.outputs.aiFoundryEndpoint
output aiProjectName string = aiProject.outputs.projectName
output aiProjectId string = aiProject.outputs.projectId
output aiProjectEndpoint string = aiProject.outputs.projectEndpoint
output aiInferenceEndpoint string = aiFoundry.outputs.aiInferenceEndpoint
output gpt4oDeploymentName string = gpt4oDeployment.outputs.deploymentName
