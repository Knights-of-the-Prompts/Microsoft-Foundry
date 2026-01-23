# Microsoft Foundry Repository - Detailed Changelog

## 🚧 January 2026 - Major Architecture Modernization (In Progress)

> **⚠️ BREAKING CHANGES**: This repository is undergoing a significant modernization to align with the latest Microsoft Foundry best practices and SDK patterns. The infrastructure and code are being updated to use the newest Azure CognitiveServices architecture.

### 📅 Timeline
- **Started**: January 23, 2026
- **Expected Completion**: February 2026
- **Status**: 🔄 Active Development - Repository may not function correctly during this period

---

## Infrastructure Changes

### 🔄 Architecture Migration: From Hub/Project to Modern Foundry

#### **OLD Architecture (Deprecated)**
```
Microsoft.MachineLearningServices/workspaces (kind: Hub)
├── Dependent Resources
│   ├── Azure Storage Account
│   ├── Azure Key Vault
│   ├── Application Insights
│   └── Container Registry
├── Microsoft.CognitiveServices/accounts (AI Services - separate)
└── Microsoft.MachineLearningServices/workspaces (kind: Project)
```

#### **NEW Architecture (Modern)**
```
Microsoft.CognitiveServices/accounts (kind: AIServices)
├── allowProjectManagement: true
└── Microsoft.CognitiveServices/accounts/projects
```

### 📁 Infrastructure Files Updated

#### New/Modified Files
- **`infra/main.bicep`** - Complete rewrite to use modern CognitiveServices architecture
  - Removed AI Hub module dependency
  - Removed dependent resources (Storage, KeyVault, AppInsights, Container Registry)
  - Simplified from 3 resource layers to 2
  - Reduced template size: 1246 lines → 823 lines (34% reduction)
  
- **`infra/modules/ai-foundry.bicep`** - NEW: Microsoft Foundry resource
  - Type: `Microsoft.CognitiveServices/accounts@2025-06-01`
  - Kind: `AIServices`
  - Property: `allowProjectManagement: true` (required for projects)
  - Outputs: `aiProjectEndpoint`, `aiInferenceEndpoint`

- **`infra/modules/ai-foundry-project.bicep`** - NEW: Project as child resource
  - Type: `Microsoft.CognitiveServices/accounts/projects@2025-06-01`
  - Parent: AI Foundry resource
  - Managed identity enabled
  - Direct project endpoint generation

- **`infra/modules/ai-services.bicep`** - Updated outputs
  - Added: `aiProjectEndpoint` (base path)
  - Added: `aiInferenceEndpoint` (models endpoint)
  - Pattern: `https://{subdomain}.services.ai.azure.com/api/projects`

- **`infra/modules/aoai-model-deployment.bicep`** - Compatible with both architectures
  - API version: `@2025-06-01`
  - Works with CognitiveServices accounts

- **`infra/main.parameters.json`** - Updated parameter structure
  - Added: `aiProjectName`
  - Added: `aiProjectDisplayName`
  - Added: `disableLocalAuth` (default: `true`)

#### Deprecated Files (Backed Up)
- **`infra/main-old-hub-architecture.bicep`** - Backup of old Hub-based architecture
- **`infra/modules/ai-hub.bicep`** - No longer used (MachineLearningServices Hub)
- **`infra/modules/ai-project.bicep`** - Replaced by `ai-foundry-project.bicep`
- **`infra/modules/dependent-resources.bicep`** - No longer required

### 🔐 Security & Authentication Changes

#### Keyless Authentication (Entra ID)
- **Default**: API keys disabled (`disableLocalAuth: true`)
- **Authentication**: Azure DefaultAzureCredential (Managed Identity, Azure CLI, etc.)
- **RBAC**: Cognitive Services Contributor role assigned to project identity
- **Benefits**:
  - No API keys to manage or rotate
  - Follows Azure security best practices
  - Simplified credential management

#### Updated Files for Keyless Auth
- `infra/modules/ai-foundry.bicep`: `disableLocalAuth` parameter
- `infra/main.bicep`: RBAC role assignment module
- Documentation updates for `az login` with subscription ID

---

## SDK & API Changes

### 📦 Microsoft Foundry Positioning Updates

#### New SDK Patterns (azure-ai-projects)
The new architecture aligns with Microsoft Foundry's unified SDK approach:

**Python**: `azure-ai-projects`
**JavaScript/TypeScript**: `@azure/ai-projects`
**.NET**: `Azure.AI.Projects`

#### Project Endpoint Pattern
- **NEW First-Class Concept**: Project Endpoint URL
  ```
  https://{account}.services.ai.azure.com/api/projects/{project}
  ```
- **Replaces**: Multiple endpoint patterns (OpenAI endpoint, resource endpoint, etc.)
- **SDK Usage**: Unified client that fans out to agents, deployments, connections, datasets, evals

#### Inference Endpoint Standardization
- **NEW Format**: `https://{resource-name}.services.ai.azure.com/models`
- **Routes by**: Deployment name in requests
- **Replaces**: Various older endpoint formats

### 🔧 Code Updates Required

#### Environment Variables
**OLD Pattern**:
```bash
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com/
AZURE_OPENAI_API_KEY=xxxxx
PROJECT_WORKSPACE_ID=xxxxx
```

**NEW Pattern**:
```bash
PROJECT_ENDPOINT=https://{resource}.services.ai.azure.com/api/projects/{project}
INFERENCE_ENDPOINT=https://{resource}.services.ai.azure.com/models
# No API keys - use Azure CLI login or Managed Identity
```

#### Documentation Updates
- `docs/docs/getting-started.md`: Updated az login commands
  - Changed: `az login --use-device-code` 
  - To: `az login --use-device-code` + `az account set --subscription <ID>`
- Updated PROJECT_ENDPOINT examples throughout documentation
- Added keyless authentication guidance

---

## Breaking Changes & Migration Guide

### ⚠️ What's Breaking

1. **Infrastructure Deployment**
   - Existing deployments using Hub/Project architecture will not automatically migrate
   - Fresh deployment required with new template
   - Different resource types: MachineLearningServices → CognitiveServices

2. **Environment Configuration**
   - `.env` file format changed
   - New endpoint patterns required
   - API keys no longer supported (by default)

3. **Resource Outputs**
   - Old: `aiHubName`, `aiProjectWorkspaceId`, `aiServicesEndpoint`
   - New: `aiFoundryName`, `aiProjectId`, `aiProjectEndpoint`, `aiInferenceEndpoint`

4. **Dependencies Removed**
   - No longer deploys: Storage Account, Key Vault, App Insights, Container Registry
   - These were ML-specific and not required for Foundry AI Projects

### 🔄 Migration Steps

#### For New Deployments
1. Use updated `infra/main.bicep`
2. Deploy with `az deployment group create`
3. Use new output values for `.env` configuration
4. Authenticate via `az login` (no API keys)

#### For Existing Deployments
1. **Backup Current Resources**
   - Export `.env` file
   - Document resource names
   - Note any custom configurations

2. **Clean Deployment** (Recommended)
   ```bash
   # Delete old resource group (or resources)
   az group delete --name <resource-group> --yes
   
   # Create new deployment
   az group create --name <resource-group> --location <location>
   az deployment group create \
     --resource-group <resource-group> \
     --template-file infra/main.bicep \
     --parameters infra/main.parameters.json
   ```

3. **Update Configuration**
   - Run `python src/workshop/setup_env.py` to generate new `.env`
   - Update any hardcoded endpoints in code
   - Test with updated authentication flow

4. **Validate**
   - Test agent creation
   - Verify model deployments
   - Confirm RBAC permissions

### 🛠️ Compatibility Notes

#### What Still Works
- ✅ Model deployments (GPT-4o, etc.)
- ✅ Agent creation and execution
- ✅ File search, code interpreter tools
- ✅ Budget alerts (if enabled)
- ✅ RBAC role assignments

#### What Changed
- 🔄 Resource types (CognitiveServices vs MachineLearningServices)
- 🔄 Endpoint patterns (services.ai.azure.com/api/projects)
- 🔄 Authentication (keyless by default)
- 🔄 Infrastructure dependencies (simplified)

#### What's Removed
- ❌ AI Hub resources
- ❌ Dependent resources module
- ❌ API key authentication (by default)
- ❌ Old endpoint patterns

---

## Testing & Validation

### ✅ Validated Components

#### Bicep Templates
- **main.bicep**: ✓ Compiles without errors
- **ai-foundry.bicep**: ✓ Validated with Bicep CLI
- **ai-foundry-project.bicep**: ✓ Validated with Bicep CLI
- **aoai-model-deployment.bicep**: ✓ Compatible with new architecture
- **All 8 module files**: ✓ Validated successfully

#### Generated Outputs
- **main.json**: ✓ ARM template generated (823 lines)
- **Parameters**: ✓ Updated with new structure
- **Outputs**: ✓ 10 outputs including new endpoint patterns

#### Resource Types
- `Microsoft.CognitiveServices/accounts`: ✓ API version @2025-06-01
- `Microsoft.CognitiveServices/accounts/projects`: ✓ API version @2025-06-01
- `Microsoft.CognitiveServices/accounts/deployments`: ✓ API version @2025-06-01

---

## Known Issues & Limitations

### 🚧 Work in Progress

1. **Sample Code Updates** (Pending)
   - Workshop samples need updating for new endpoints
   - Notebook samples require authentication updates
   - Some samples may still reference old patterns

2. **Documentation** (Partial)
   - Getting started guide updated
   - Sample READMEs need review
   - API reference updates in progress

3. **Testing** (Ongoing)
   - Bicep validation: ✓ Complete
   - Deployment testing: 🔄 In progress
   - End-to-end scenarios: 🔄 Pending
   - Sample validation: 🔄 Pending

### ⚠️ Temporary Limitations

- Repository may not function correctly during migration period
- Some samples may fail until updated
- Documentation may contain outdated patterns
- Example `.env` files may need manual adjustment

---

## Future Enhancements (Planned)

### 🎯 Coming Soon

1. **Complete Sample Updates**
   - Update all Jupyter notebooks
   - Refresh all markdown tutorials
   - Add new SDK pattern examples

2. **Enhanced Documentation**
   - Migration guide with screenshots
   - Troubleshooting common issues
   - FAQ section

3. **Additional Features**
   - Network security configurations
   - Private endpoint support
   - Multi-region deployments
   - Advanced RBAC scenarios

4. **Developer Experience**
   - Automated migration scripts
   - Validation tools
   - Development container updates

---

## References & Resources

### 📚 Microsoft Documentation
- [Azure AI Foundry Documentation](https://learn.microsoft.com/azure/ai-services/agents/)
- [Azure AI Projects SDK](https://learn.microsoft.com/python/api/overview/azure/ai-projects-readme)
- [Bicep Best Practices](https://learn.microsoft.com/azure/azure-resource-manager/bicep/best-practices)
- [Keyless Authentication](https://learn.microsoft.com/azure/ai-services/authentication)

### 🔗 Related Changes
- Issue: Modern Foundry Architecture Migration
- PR: Infrastructure Modernization
- Docs: Updated Getting Started Guide

---

## Support & Feedback

### 🤝 Get Help
- **Issues**: Report problems via GitHub Issues
- **Questions**: Use GitHub Discussions
- **Updates**: Watch this changelog for progress

### 📧 Contact
For urgent issues or questions during the migration period, please open a GitHub issue with the label `migration-support`.

---

**Last Updated**: January 23, 2026  
**Version**: 2.0.0-beta (Migration in Progress)
