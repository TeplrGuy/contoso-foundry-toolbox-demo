param name string
param location string = resourceGroup().location
param tags object = {}

@description('Principal IDs granted data-plane read access to the search indexes (Function App identity and Foundry project identity).')
param readerPrincipalIds array = []

var searchIndexDataReaderRoleId = '1407120a-92aa-4202-b7e9-c0e197c71c8f'
var searchServiceContributorRoleId = '7ca78c08-252a-4471-8644-bb5ff32d4ba0'

resource searchService 'Microsoft.Search/searchServices@2025-05-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    publicNetworkAccess: 'Enabled'
    semanticSearch: 'standard'
    hostingMode: 'Default'
    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

resource searchDataReaderRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in readerPrincipalIds: {
  name: guid(searchService.id, principalId, searchIndexDataReaderRoleId)
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchIndexDataReaderRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}]

resource searchServiceContributorRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in readerPrincipalIds: {
  name: guid(searchService.id, principalId, searchServiceContributorRoleId)
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', searchServiceContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}]

output name string = searchService.name
output endpoint string = 'https://${searchService.name}.search.windows.net'
output resourceId string = searchService.id
