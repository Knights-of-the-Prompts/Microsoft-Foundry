<div align="center">
    <img src="../../../media/image-sk1.png" width="100%" alt="Azure AI Foundry workshop / lab / sample">
</div>

## What is Semantic Kernel?

Semantic Kernel is a model-agnostic SDK that empowers developers to build, orchestrate, and deploy AI agents and multi-agent systems. Whether you're building a simple chatbot or a complex multi-agent workflow, Semantic Kernel provides the tools you need with enterprise-grade reliability and flexibility.

## System Requirements

- **Python**: 3.10+
- **OS Support**: Windows, macOS, Linux

## Key Features

- **Model Flexibility**: Connect to any LLM with built-in support for [OpenAI](https://platform.openai.com/docs/introduction), [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service), [Hugging Face](https://huggingface.co/), [NVidia](https://www.nvidia.com/en-us/ai-data-science/products/nim-microservices/) and more
- **Agent Framework**: Build modular AI agents with access to tools/plugins, memory, and planning capabilities
- **Multi-Agent Systems**: Orchestrate complex workflows with collaborating specialist agents
- **Plugin Ecosystem**: Extend with native code functions, prompt templates, OpenAPI specs, or Model Context Protocol (MCP)
- **Vector DB Support**: Seamless integration with [Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-what-is-azure-search), [Elasticsearch](https://www.elastic.co/), [Chroma](https://docs.trychroma.com/getting-started), and more
- **Multimodal Support**: Process text, vision, and audio inputs
- **Local Deployment**: Run with [Ollama](https://ollama.com/), [LMStudio](https://lmstudio.ai/), or [ONNX](https://onnx.ai/)
- **Process Framework**: Model complex business processes with a structured workflow approach
- **Enterprise Ready**: Built for observability, security, and stable APIs

## Installation

First, make sure you have your Python environment setup. You should run the workshop first or at least the [Getting Started](getting-started.md) so that you have the required environment variables set up.

After setting up your virtual environment, install the Semantic Kernel SDK for your preferred programming language:

## Install Python packages

```bash
pip install semantic-kernel
```

# Basic Agent

Create a simple assistant that responds to user prompts. In the root of your project, create a new Python file named `simple_agent.py` and add the following code:

```python
import asyncio
import os
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from azure.identity import DefaultAzureCredential
import dotenv

# Load environment variables from a .env file (if present)
dotenv.load_dotenv()  

async def main():
    # Get Azure OpenAI endpoint and deployment name from environment variables
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AGENT_MODEL_DEPLOYMENT_NAME")

    # Check if all required environment variables are set
    if not all([endpoint, deployment]):
        raise ValueError("Make sure AZURE_OPENAI_ENDPOINT and AGENT_MODEL_DEPLOYMENT_NAME are set as environment variables.")

    # Create an agent that can chat using Azure OpenAI with DefaultAzureCredential (more secure)
    agent = ChatCompletionAgent(
        service=AzureChatCompletion(
            endpoint=endpoint,
            ad_token_provider=DefaultAzureCredential(),
            deployment_name=deployment,
        ),
        name="SK-Assistant",  # Name of the agent
        instructions="You are a helpful assistant.",  # Instructions for the agent's behavior
    )

    # Ask the agent to write a haiku about Semantic Kernel
    response = await agent.get_response(messages="Write a haiku about Semantic Kernel.")
    # Print the agent's response
    print(response.content)

# Run the main function using asyncio (for asynchronous code)
asyncio.run(main()) 
```
Run the script:

```bash
python simple_agent.py
```

The output will be something like this:
```prompt
Language's essence,
Semantic threads intertwine,
Meaning's core revealed.
```

# Agent with Plugins

Enhance your agent with custom tools (plugins) and structured output. Create a new Python file named `agent_with_plugins.py` and add the following code:

```python
import asyncio  # For asynchronous execution
import os  # For accessing environment variables
import dotenv  # For loading .env files
from typing import Annotated  # For type annotations
from pydantic import BaseModel  # For structured data models
from semantic_kernel.agents import ChatCompletionAgent  # Agent class
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatPromptExecutionSettings  # Azure OpenAI connectors
from semantic_kernel.functions import kernel_function, KernelArguments  # For creating plugins and function calls
from azure.identity import DefaultAzureCredential  # For secure Azure authentication

# Load environment variables from a .env file (if present)
dotenv.load_dotenv()

# Plugin class that provides menu-related functions for the agent
class MenuPlugin:
    @kernel_function(description="Provides a list of specials from the menu.")
    def get_specials(self) -> Annotated[str, "Returns the specials from the menu."]:
        return """
        Special Soup: Clam Chowder
        Special Salad: Cobb Salad
        Special Drink: Chai Tea
        """

    @kernel_function(description="Provides the price of the requested menu item.")
    def get_item_price(
        self, menu_item: Annotated[str, "The name of the menu item."]
    ) -> Annotated[str, "Returns the price of the menu item."]:
        return "$9.99"

# Pydantic model for structured output format (defines the expected response structure)
class MenuItem(BaseModel):
    price: float
    name: str


async def main():
    # Get Azure OpenAI configuration from environment variables
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AGENT_MODEL_DEPLOYMENT_NAME")

    # Check if all required environment variables are set
    if not all([endpoint, deployment]):
        raise ValueError("Make sure AZURE_OPENAI_ENDPOINT and AGENT_MODEL_DEPLOYMENT_NAME are set as environment variables.")

    # Configure structured output format (tells the agent to respond in MenuItem format)
    settings = OpenAIChatPromptExecutionSettings()
    settings.response_format = MenuItem

    # Create an agent with the menu plugin and structured output settings
    agent = ChatCompletionAgent(
        service=AzureChatCompletion(
            endpoint=endpoint,
            ad_token_provider=DefaultAzureCredential(),
            deployment_name=deployment,
        ),
        name="SK-Assistant",
        instructions="You are a helpful assistant. Use the provided tools to answer user questions about the menu. Format the response in a human readable way.",
        plugins=[MenuPlugin()],  # Add the menu plugin so agent can use its functions
        arguments=KernelArguments(settings)  # Pass the structured output settings
    )

    # Ask the agent a question about the menu
    response = await agent.get_response(messages="What is the price of the soup special?")
    print(response.content)

# Run the main function when script is executed directly
asyncio.run(main()) 
```

Run the script:

```bash
python agent_with_plugins.py
```

The output will be something like this:
```prompt
{"price":9.99,"name":"soup special"}
```

# Multi-Agent System

Build a system of specialized agents that can collaborate. In this case we also add a logging class so that we can see the conversation between the agents. Create a new Python file named `multi_agent_system.py` and add the following code:

```python
import asyncio  # For asynchronous execution
import os  # For accessing environment variables
import dotenv  # For loading .env files
import logging  # For logging agent activity
from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread  # Agent classes
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion, OpenAIChatCompletion  # LLM connectors
from azure.identity import DefaultAzureCredential  # For secure Azure authentication

# Load environment variables from a .env file (if present)
dotenv.load_dotenv()

# Configure logging so we can see which agent is processing each task
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# Get Azure OpenAI configuration from environment variables
# These variables must be set in your .env file
endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
deployment = os.environ.get("AGENT_MODEL_DEPLOYMENT_NAME")

# Check if all required environment variables are set
if not all([endpoint, deployment]):
    raise ValueError("Make sure AZURE_OPENAI_ENDPOINT and AGENT_MODEL_DEPLOYMENT_NAME are set as environment variables.")

# Subclass for logging per agent. This class logs the name of the agent for each task.
class LoggingChatCompletionAgent(ChatCompletionAgent):
    async def get_response(self, *args, **kwargs):
        logging.info(f"{self.name} is processing the request...")
        return await super().get_response(*args, **kwargs)

# Agent responsible for billing-related questions
billing_agent = LoggingChatCompletionAgent(
    service=AzureChatCompletion(
        endpoint=endpoint,
        ad_token_provider=DefaultAzureCredential(),
        deployment_name=deployment,
    ),
    name="BillingAgent",
    instructions="You handle billing issues like charges, payment methods, cycles, fees, discrepancies, and payment failures."
)

# Agent responsible for refund-related questions
refund_agent = LoggingChatCompletionAgent(
    service=AzureChatCompletion(
        endpoint=endpoint,
        ad_token_provider=DefaultAzureCredential(),
        deployment_name=deployment,
    ),
    name="RefundAgent",
    instructions="Assist users with refund inquiries, including eligibility, policies, processing, and status updates.",
)

# Agent that determines which specialized agent (billing/refund) should handle the request
triage_agent = LoggingChatCompletionAgent(
    service=AzureChatCompletion(
        endpoint=endpoint,
        ad_token_provider=DefaultAzureCredential(),
        deployment_name=deployment,
    ),
    name="TriageAgent",
    instructions="Evaluate user requests and forward them to BillingAgent or RefundAgent for targeted assistance. Provide the full answer to the user containing any information from the agents and the name of the agent that handled the request.",
    plugins=[billing_agent, refund_agent],
)

# Thread object to maintain chat history (for context between turns)
thread: ChatHistoryAgentThread = None

# Main program: start a chat loop with the user
async def main() -> None:
    print("Welcome to the chat bot!\n  Type 'exit' to exit.\n  Try to get some billing or refund help.")
    while True:
        # Read user input
        user_input = input("User:> ")

        # Exit if user types 'exit'
        if user_input.lower().strip() == "exit":
            print("\n\nExiting chat...")
            return False

        # Ask triage_agent to process the request
        response = await triage_agent.get_response(
            messages=user_input,
            thread=thread,
        )

        # Display the agent's response
        if response:
            print(f"Agent:> {response}")

# Start the main program when the script is run directly
if __name__ == "__main__":
    asyncio.run(main())
```
Run the script:

```bash
python multi_agent_system.py
``` 

In the terminal, you can start asking questions about billing or refunds. For example:

```prompt
User:> i'm charged twice for my subscription last month
```

The output will be something like this:

```prompt
2025-09-26 13:15:50,068 INFO TriageAgent is processing the request...
2025-09-26 13:15:51,783 INFO HTTP Request: POST https://aif-qinv-ocri.cognitiveservices.azure.com/openai/deployments/gpt41/chat/completions?api-version=2024-10-21 "HTTP/1.1 200 OK"
2025-09-26 13:15:51,791 INFO OpenAI usage: CompletionUsage(completion_tokens=28, prompt_tokens=184, total_tokens=212, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0))
2025-09-26 13:15:51,791 INFO processing 1 tool calls in parallel.
2025-09-26 13:15:51,791 INFO Calling BillingAgent-BillingAgent function with args: {"messages":"I was charged twice for my subscription last month."}
2025-09-26 13:15:51,794 INFO Function BillingAgent-BillingAgent invoking.
2025-09-26 13:15:51,794 INFO BillingAgent is processing the request...
2025-09-26 13:15:53,645 INFO HTTP Request: POST https://aif-qinv-ocri.cognitiveservices.azure.com/openai/deployments/gpt41/chat/completions?api-version=2024-10-21 "HTTP/1.1 200 OK"
2025-09-26 13:15:53,646 INFO OpenAI usage: CompletionUsage(completion_tokens=88, prompt_tokens=44, total_tokens=132, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0))
2025-09-26 13:15:53,646 INFO Function BillingAgent-BillingAgent succeeded.
2025-09-26 13:15:53,646 INFO Function completed. Duration: 1.852057s
2025-09-26 13:15:55,870 INFO HTTP Request: POST https://aif-qinv-ocri.cognitiveservices.azure.com/openai/deployments/gpt41/chat/completions?api-version=2024-10-21 "HTTP/1.1 200 OK"
2025-09-26 13:15:55,871 INFO OpenAI usage: CompletionUsage(completion_tokens=103, prompt_tokens=309, total_tokens=412, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0))
Agent:> I'm sorry to hear you were charged twice for your subscription last month. To help resolve this issue, could you please provide the following details:

- The date(s) of both charges
- The total amount charged each time
- The last 4 digits of your payment method (if applicable)
- Any reference or transaction IDs you may have

Once I have this information, I can look into your account and help process a refund for any duplicate charge. This request will be handled by the BillingAgent.
User:>
```

# Optional: Build an UI using vibe coding
Make sure Github Copilot is set to Agent mode and add the python script is added as context. 

```prompt
Build a nice interface that looks like a customer support page of a campsite ecommerce store. The interface should be based on Fluent UI. 
```

After some iterations you should get something like this:

![alt text](../../../media/image-sk2.png)

If you run into issues, just ask Copilot to fix the issues. Copy and paste any error messages you get to Copilot.

## Additional Resources

1. 🔌 Explore over 100 [Detailed Samples](https://learn.microsoft.com/en-us/semantic-kernel/get-started/detailed-samples)
2. 💡 Learn about core Semantic Kernel [Concepts](https://learn.microsoft.com/en-us/semantic-kernel/concepts/kernel)
