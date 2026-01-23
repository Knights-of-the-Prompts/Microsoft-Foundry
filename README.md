<div align="center">
    <img src="media/image-1.png" width="100%" alt="Azure AI Foundry">
</div>

> **📢 Repository Updated | January 2026**  
> This repository has been updated to align with the latest Azure AI Foundry best practices, including migration to `Microsoft.MachineLearningServices` resource provider, Azure AI Projects SDK 2.0, and identity-based authentication (AAD) replacing API keys.

# **Welcome to the "Build Agents with Azure AI Foundry" workshop repo!** 🎉

Dive into the world of intelligent conversational agents with Azure AI Foundry & AI Agent Service, a seamless blend of service and SDK that simplifies the development of robust AI-driven solutions. In this hands-on workshop, you’ll learn to create a powerful agent capable of answering sales-related queries, performing data analysis, generating visualizations, and integrating external data sources to deliver enhanced business insights. 🚀
## 🌟 **Beyond Chatbots: Unlock the Future of AI Applications** 🌟

> **💡 Think Bigger, Build Smarter!**  
> Traditional chatbots and Copilots like ChatGPT have revolutionized how we interact with AI. But why stop there? This workshop challenges you to **think beyond chatbots** and explore the next frontier: **Agentic Applications**.


### 🚀 **What Are Agentic Applications?**
Agentic applications are **AI systems with superpowers**:
- 🗣️ **Conversational Intelligence**: Engage users naturally.
- 🤖 **Action-Oriented Capabilities**: Automate workflows and execute meaningful actions.
- 📊 **Proactive Insights**: Deliver transformative solutions to complex business challenges.

### 🔑 **Why Go Beyond Chatbots?**
By embracing Agentic applications, you’ll:
- **Unlock New Possibilities**: Tackle advanced use cases that traditional chatbots can’t handle.
- **Drive Innovation**: Build solutions tailored to your unique business needs.
- **Empower Decision-Making**: Enable smarter, faster, and more impactful decisions.

### 🌐 **Your Journey Starts Here**
This workshop is your gateway to creating **intelligent, action-driven AI solutions**. Let’s redefine what’s possible with Azure AI Foundry and take your AI development to the next level! 💼✨

### ⏱️ Duration
🕒 45 - 60 minutes

### 🎥 Watch a Recent Workshop Execution Video

Catch a glimpse of the workshop in action! Watch the latest execution of this workshop to see how to build intelligent agents step-by-step. Click the thumbnail below to view the video:

<div align="left">
    <a href="https://youtu.be/z2mReVIfYI0" target="_blank">
        <img src="media/kotp-lab1-2.png" alt="Workshop Video Thumbnail" width="50%">
    </a>
    <p><a href="https://youtu.be/z2mReVIfYI0" target="_blank">Watch the Workshop Video</a></p>
</div>

## 💡 The Use Case for This Lab

<div align="left" style="padding: 10px;">
    <img src="media/image-2.png" alt="📊" height="150px">
</div>

Imagine you are a sales manager at Contoso, a multinational retail company that sells outdoor equipment. 🏕️ You need to analyze sales data to find trends, understand customer preferences, and make informed business decisions. To help you, Contoso has developed a conversational agent that can answer questions about your sales data. 💬📈

## 🎯 What You Will Learn

By the end of this workshop, you will:
- 🛠️ Build an agent app using Azure AI Agent Service.
- 🔍 Explore its tools.
- 📜 Effectively use instructions to guide the LLM.

After the basic workshop we will guide you to continue enhancing your agent with more advanced features, such as:
- 🚀 Expand the agent's capabilities beyond basic conversational tasks.
- 🧠 Integrate advanced AI features such as reasoning, planning, and decision-making.
- 🔗 Connect the agent to external APIs and data sources for enriched functionality.
- 📊 Enable the agent to generate visualizations and actionable insights from datasets.
- 🤝 Incorporate multi-agent collaboration to solve intricate business challenges.
- 🌐 Leverage Azure AI services to scale and enhance the agent's performance.

## 📖 Workshop Instructions

👉 Start the full workshop here: [Introduction](docs/docs/introduction.md)

## 📚 Additional Resources

When you finished the workshop, check out additional resources such as the samples in the [samples folder](src/samples) and the [official documentation](https://learn.microsoft.com/azure/ai-services/agents/overview).

### Samples overview
Agent Creation:
- [Create AI Agents using the AI Foundry UI](src/samples/create-agent-using-ui/lab-create-ai-agent-in-ai-foundry-ui.md)
- [Create AI Agents using Jupyter Notebooks](src/samples/create-agent-using-notebook/lab-create-ai-agent-using-notebook.ipynb)
- [Create RAG Agents using Jupyter Notebooks](src/samples/create-rag-agent-using-notebook/lab-create-rag-agent-using-notebook.ipynb)
- [Create Multi-Agent Systems using Jupyter Notebooks](src/samples/create-multi-agent-system-using-notebook/lab-create-multi-agent-system-using-notebook.ipynb)
- [Create Agents with the Bing Grounding Tool](src/samples/create-a-bing-grounding-connection/lab-create-a-bing-grounding-connection.md)

Deep Research Tool:
- [Create Agents with the Deep Research Tool](src/samples/create-deep-research-tool/lab-how-to-use-the-deep-research-tool.md)
- [Debugging sample for the Deep Research Tool](src/samples/create-deep-research-tool/lab-deep-research-tool-debugging-sample.md)

Agent Framework:
- [Create Agents using Semantic Kernel](src/samples/create-semantic-kernel-agents/lab-create-simple-semantic-kernel-agents.md)
- *Create Agents using AutoGen.... (coming soon)*
- *Create Agents using the Agent Framework.... (coming soon)*

Autonomous Agents:
- *Create Autonomous Agents....(coming soon)*

Sovereign AI using Foundry Local:
- [Setup Foundry Local to go Sovereign](src/samples/create-sovereign-agents-using-foundry-local/lab-get-started-with-foundry-local.md)
- [Use OpenAI SDK with Foundry Local](src/samples/create-sovereign-agents-using-foundry-local/lab-use-openai-sdk-with-foundry-local.md)

Build User Interfaces:
- [Create a (mockup) User Interface for Agents using Vibe Coding](src/samples/create-a-user-interface-for-agents/lab-vibe-coding-mockup-ui.md)
- *Create a NLWeb UI for Agents....(coming soon)*

MCP Integration:
- [Create AI Foundry Agents connected to MCP Servers](src/samples/create-mcp-foundry-agents/lab-create-agent-that-uses-mcp-server.md)

- *Create MCP Server....(coming soon)*

Multimodal Agents:
- [Create a Talking Avatar website using Azure Text-to-Speech Avatar Real-Time API](src/samples/create-a-talking-avatar/avatar/README.md)
- Create Multimodal Agents....(coming soon)
- Create Agents with Vision Tool....(coming soon)
- Create Agents with Speech Tool....(coming soon)

Integration with Business Applications:
- Create Agents with SAP Connector....(coming soon)
- Create Agents with Salesforce Connector....(coming soon)

## Resources for organizing a hackathon 🎉

If you are interested in organizing a hackathon using this repository, check out the infra folder. 📂 It contains scripts and templates to set up the Azure infrastructure needed for the hackathon, as well as policies to control costs. 💰 Below are the links to the guides:

- **Hackathon Infrastructure Setup Guide**: 🛠️ Learn how to set up the necessary Azure infrastructure for hosting a hackathon, including cost control policies and deployment scripts. [Read more here](infra/README.md).
- **Cost Control Policies Guide**: 📊 Understand the cost control policies implemented to manage and monitor expenses during the hackathon. [Read more here](infra/policies/README.md).
---

## 📝 Changelog

### January 2026 - Major Infrastructure & SDK Update

**🔄 Breaking Changes**
- **Infrastructure Migration**: Migrated from `Microsoft.CognitiveServices/accounts/projects` to `Microsoft.MachineLearningServices/workspaces` (AI Hub + AI Project pattern)
  - Updated [main.bicep](infra/main.bicep) to use AI Hub architecture
  - Created [ai-services.bicep](infra/modules/ai-services.bicep) for AI Services resource
  - Updated [ai-hub.bicep](infra/modules/ai-hub.bicep) to API version `2024-10-01-preview`
  - Refactored [ai-project.bicep](infra/modules/ai-project.bicep) to use `kind: 'Project'` with `hubResourceId`
  - Added [role-assignment.bicep](infra/modules/role-assignment.bicep) for identity-based access
- **SDK Compatibility**: Updated to Azure AI Projects SDK 2.0.0b3
  - New API patterns: `PromptAgentDefinition`, `create_version()`, `get_openai_client()`
  - Replaced Threads API with Conversations API
  - Updated FunctionTool initialization syntax

**🔐 Security Enhancements**
- Replaced API key authentication with Azure AD (DefaultAzureCredential)
- Updated AI Hub connections to use `authType: 'AAD'` instead of API keys
- Updated Semantic Kernel samples to use managed identity authentication

**✨ New Features**
- Created [setup_env.py](src/workshop/setup_env.py) - Automated environment configuration script
  - Retrieves configuration from existing Azure deployments
  - Azure CLI integration with timeout handling
  - Graceful fallback mechanisms
- Added [.env.sample](src/workshop/.env.sample) template file
- Created [main_v2.py](src/workshop/main_v2.py) demonstrating Azure AI Projects SDK 2.0 patterns

**📚 Documentation Updates**
- Updated [getting-started.md](docs/docs/getting-started.md) with automated setup instructions
- Enhanced Semantic Kernel samples with DefaultAzureCredential examples

**🗑️ Removed**
- Removed o3-deep-research model deployment (commented out in bicep templates)
- Deprecated old `ai-foundry.bicep` module (replaced by ai-services.bicep)

**⚙️ Technical Details**
- Resource API versions updated to `2024-10-01-preview` (MachineLearningServices)
- AI Services uses `2024-10-01` API version
- Role-based access control for AI Project → AI Services communication
- Proper resource hierarchy: AI Services → AI Hub → AI Project

**🔗 Migration Path**
For existing deployments, a full redeployment is required:
1. Back up current `.env` configuration
2. Run `az deployment group create` with updated bicep templates
3. Update `.env` with new project workspace ID
4. Test with `main_v2.py` to verify SDK 2.0 compatibility

---