![alt text](../media/image-infra.png)

> **🚧 INFRASTRUCTURE UPDATED | January 2026**
> 
> **⚠️ NOTICE**: The infrastructure templates have been modernized to use the latest Microsoft Foundry architecture (CognitiveServices-based). The old Hub/Project architecture is deprecated.
> 
> - ✨ New simplified architecture (2 core resources vs 6+)
> - 🔐 Keyless authentication by default (Entra ID)
> - ❌ o3-deep-research deployment removed (under revision)
> 
> See [CHANGELOG.md](../CHANGELOG.md) for details.

## Microsoft Foundry Basic Setup

This folder contains all the deployment templates and scripts needed to set up a basic Microsoft Foundry environment. For the Knights of the Prompts workshop, we will use a simplified configuration of Microsoft Foundry, which is suitable for learning and experimentation purposes.

### What's Deployed

This template deploys the following resources:

- **Microsoft Foundry Resource**: CognitiveServices AIServices account with project management enabled
- **Microsoft Foundry Project**: A project within the foundry for organizing AI assets  
- **Azure OpenAI GPT-4o deployment**: Language model deployment for AI agents
- **RBAC Role Assignment**: Managed identity access for the project to the foundry resource
- **Budget Alert** (optional): Cost management and budget monitoring

> **IMPORTANT**  
> Before using this setup, please check with your instructor if environments need to be deployed as part of the workshop. For the Knights of the Prompts hackathon, all the team environments will be deployed by the instructor.

Open your browser and go to the [Azure Portal](https://portal.azure.com). Logon with the credentials provided by your instructor.

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FKnights-of-the-Prompts%2FMicrosoft-Foundry%2Fmain%2Finfra%2Fazuredeploy.json)

This template demonstrates how to set up Microsoft Foundry with the modern CognitiveServices architecture, featuring:
- **Keyless authentication** using Entra ID (DefaultAzureCredential)
- **Simplified infrastructure** - no dependent resources (Storage, KeyVault, etc.)
- **Public internet access** enabled for workshop scenarios
- **Modern endpoint patterns** for azure-ai-projects SDK compatibility
