// Creates an Azure AI Services resource for AI models and deployments

@description('Azure region of the deployment')
param location string

@description('Tags to add to the resources')
param tags object

@description('AI Services resource name')
param aiServicesName string

@description('AI Services display name')
param aiServicesFriendlyName string = aiServicesName

@description('AI Services description')
param aiServicesDescription string

@description('The SKU name for the AI Services resource')
@allowed(['S0'])
param skuName string = 'S0'

@description('Whether public network access is allowed')
@allowed(['Enabled', 'Disabled'])
param publicNetworkAccess string = 'Enabled'

@description('Custom subdomain name for the AI Services resource')
param customSubDomainName string = ''

@description('Whether to disable local authentication')
param disableLocalAuth bool = false

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiServicesName
  location: location
  tags: union(tags, {
    displayName: aiServicesFriendlyName
    description: aiServicesDescription
  })
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: skuName
  }
  properties: {
    customSubDomainName: !empty(customSubDomainName) ? customSubDomainName : aiServicesName
    publicNetworkAccess: publicNetworkAccess
    disableLocalAuth: disableLocalAuth
    apiProperties: {
      statisticsEnabled: false
    }
    networkAcls: {
      defaultAction: 'Allow'
      ipRules: []
      virtualNetworkRules: []
    }
  }
}

output aiServicesId string = aiServices.id
output aiServicesName string = aiServices.name
output aiServicesEndpoint string = aiServices.properties.endpoint
output aiServicesPrincipalId string = aiServices.identity.principalId
output aiProjectEndpoint string = 'https://${aiServices.properties.customSubDomainName}.services.ai.azure.com/api/projects'
output aiInferenceEndpoint string = 'https://${aiServices.properties.customSubDomainName}.services.ai.azure.com/models'
