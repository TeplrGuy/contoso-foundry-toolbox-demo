@description('Name of the existing Microsoft Foundry account that owns the connection.')
param foundryAccountName string

@description('Name of the Foundry connection to create for Azure AI Search.')
param connectionName string

@description('Azure AI Search endpoint, for example https://mysearch.search.windows.net.')
param searchEndpoint string

@description('Resource ID of the Azure AI Search service.')
param searchResourceId string

@description('Location of the Azure AI Search service.')
param searchLocation string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-10-01-preview' existing = {
  name: foundryAccountName
}

// Keyless (Entra) connection. The Foundry account's system-assigned identity is granted
// Search data-plane roles in search.bicep, so no API key is stored in the connection.
resource searchConnection 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  name: connectionName
  parent: foundryAccount
  properties: {
    category: 'CognitiveSearch'
    target: searchEndpoint
    authType: 'AAD'
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: searchResourceId
      location: searchLocation
    }
  }
}

output connectionName string = searchConnection.name
output connectionId string = searchConnection.id
