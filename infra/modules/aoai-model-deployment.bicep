@description('Resource ID of a Microsoft Foundry resource (kind=AIServices) or Azure OpenAI account (kind=OpenAI).')
param openAIAccountId string

@description('Deployment name.')
param deploymentName string = 'gpt-4o'

@description('Model name.')
param modelName string = 'gpt-4o'

@description('Model version.')
param modelVersion string = ''

@description('Version upgrade option.')
@allowed(['OnceNewDefaultVersionAvailable', 'OnceCurrentVersionExpired', 'NoAutoUpgrade'])
param versionUpgradeOption string = 'OnceNewDefaultVersionAvailable'

@description('RAI policy name.')
param raiPolicyName string = 'Microsoft.DefaultV2'

@minValue(1)
param capacity int = 30

var openAIAccountName = last(split(openAIAccountId, '/'))

resource openAI 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAIAccountName
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  name: deploymentName
  parent: openAI
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      name: modelName
      format: 'OpenAI'
      version: !empty(modelVersion) ? modelVersion : null
    }
    versionUpgradeOption: versionUpgradeOption
    currentCapacity: capacity
    raiPolicyName: raiPolicyName
  }
}

output deploymentName string = deploymentName
output modelNameOut string = modelName
output endpoint string = openAI.properties.endpoint
