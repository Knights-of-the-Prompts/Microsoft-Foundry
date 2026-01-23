![alt text](../media/image-infra.png)
## Microsoft Foundry basic setup

This folder contains all the deployment templates and scripts needed to set up a basic Microsoft Foundry environment. For the Knights of the Prompts workshop, we will use a simplified configuration of Microsoft Foundry, which is suitable for learning and experimentation purposes.

### What's Deployed

This template deploys the following resources:

- **Microsoft Foundry Resource**: The main AI resource that serves as the workspace
- **Azure AI Project**: A project within the foundry for organizing AI assets
- **Azure OpenAI GPT-4o deployment**: Language model deployment for AI agents
- **Supporting resources**: Storage, Key Vault, Container Registry, Application Insights
- **03-Deep-Research**: Advanced research configuration for AI experimentation

> **IMPORTANT**  
> Before using this setup, please check with your instructor if environments need to be deployed as part of the workshop. For the Knights of the Prompts hackathon, all the team environments will be deployed by the instructor.

Open your browser and go to the [Azure Portal](https://portal.azure.com). Logon with the credentials provided by your instructor.

[![Deploy To Azure](https://raw.githubusercontent.com/Azure/azure-quickstart-templates/master/1-CONTRIBUTION-GUIDE/images/deploytoazure.svg?sanitize=true)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2FKnights-of-the-Prompts%2FMicrosoft-Foundry%2Fmain%2Finfra%2Fazuredeploy.json)

This set of templates demonstrates how to set up Microsoft Foundry with a basic configuration, meaning with public internet access enabled, Microsoft-managed keys for encryption and _Microsoft_-managed identity configuration for the AI hub resource.
