"""
Azure AI Projects 2.0 - Workshop Main Application
Uses the new Prompt Agent API with Conversations and Responses
Based on azure-sdk-for-python samples
"""

import asyncio
from datetime import date
import logging
import os
import json

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    FunctionTool,
    FileSearchTool,
    CodeInterpreterTool,
    CodeInterpreterToolAuto,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from sales_data import SalesData
from terminal_colors import TerminalColors as tc
from utilities import Utilities

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

load_dotenv()

TENTS_DATA_SHEET_FILE = "datasheet/contoso-tents-datasheet.pdf"
API_DEPLOYMENT_NAME = os.getenv("AGENT_MODEL_DEPLOYMENT_NAME")
PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
AZURE_SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
AZURE_RESOURCE_GROUP_NAME = os.environ["AZURE_RESOURCE_GROUP_NAME"]
AZURE_PROJECT_NAME = os.environ["AZURE_PROJECT_NAME"]
BING_CONNECTION_NAME = os.getenv("BING_CONNECTION_NAME")
MAX_COMPLETION_TOKENS = 4096
MAX_PROMPT_TOKENS = 10240
TEMPERATURE = 0.1
TOP_P = 0.1

sales_data = SalesData()
utilities = Utilities()

# INSTRUCTIONS_FILE = "instructions/instructions_function_calling.txt"
# INSTRUCTIONS_FILE = "instructions/instructions_code_interpreter.txt"
# INSTRUCTIONS_FILE = "instructions/instructions_file_search.txt"


# Function tool definition
async def fetch_sales_data_using_sqlite_query(sqlite_query: str) -> str:
    """
    Fetch sales data using a SQLite query.
    
    Args:
        sqlite_query: The SQLite query to execute
        
    Returns:
        str: JSON string with query results
    """
    try:
        result = await sales_data.async_fetch_sales_data_using_sqlite_query(sqlite_query)
        return result
    except Exception as e:
        return json.dumps({"error": str(e)})


# Function schema for the agent  
function_tool = FunctionTool(
    name="fetch_sales_data_using_sqlite_query",
    description="Fetch sales data from the database using a SQLite query",
    parameters={
        "type": "object",
        "properties": {
            "sqlite_query": {
                "type": "string",
                "description": "The SQLite query to execute"
            }
        },
        "required": ["sqlite_query"]
    },
    strict=True,
)


async def get_tools():
    """Get tools for the agent based on the instructions file."""
    tools = []
    
    # Function tool (always enabled for this workshop)
    # tools.append(function_tool)
    
    # # Code interpreter tool
    # if "code_interpreter" in INSTRUCTIONS_FILE:
    #     tools.append(CodeInterpreterTool(container=CodeInterpreterToolAuto()))
    
    # # File search tool
    # if "file_search" in INSTRUCTIONS_FILE:
    #     try:
    #         print("Creating vector store for file search...")
    #         vector_store = utilities.create_vector_store(
    #             project_client,
    #             files=[TENTS_DATA_SHEET_FILE],
    #             vector_store_name="Contoso Product Information Vector Store",
    #         )
    #         tools.append(FileSearchTool(container=FileSearchToolAuto(vector_store_ids=[vector_store.id])))
    #         print(f"File search tool added with vector store: {vector_store.id}")
    #     except Exception as e:
    #         print(f"Error creating file search tool: {e}")
    #         print("Continuing without file search capability...")
    
    return tools


async def initialize(project_client: AIProjectClient):
    """Initialize the agent with the sales data schema and instructions."""
    
    await sales_data.connect()
    database_schema_string = await sales_data.get_database_info()

    try:
        env = os.getenv("ENVIRONMENT", "local")
        INSTRUCTIONS_FILE_PATH = f"{'src/workshop/' if env == 'container' else ''}{INSTRUCTIONS_FILE}"
        
        with open(INSTRUCTIONS_FILE_PATH, "r", encoding="utf-8", errors="ignore") as file:
            instructions = file.read()

        # Replace the placeholder with the database schema string
        instructions = instructions.replace("{database_schema_string}", database_schema_string)
        instructions = instructions.replace("{current_date}", date.today().strftime("%Y-%m-%d"))

        # Get tools
        tools = await get_tools()

        # Create agent using the new API
        print("Creating agent...")
        agent = project_client.agents.create_version(
            agent_name="ContosoSalesAgent",
            definition=PromptAgentDefinition(
                model=API_DEPLOYMENT_NAME,
                instructions=instructions,
                tools=tools,
                temperature=TEMPERATURE,
            ),
        )
        print(f"Created agent (id: {agent.id}, name: {agent.name}, version: {agent.version})")

        return agent

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        raise


async def cleanup(project_client: AIProjectClient, agent_name: str):
    """Cleanup the resources."""
    try:
        # Get all versions of the agent
        versions = project_client.agents.list_versions(agent_name=agent_name)
        for version in versions:
            project_client.agents.delete_version(agent_name=agent_name, agent_version=version.version)
            print(f"Deleted agent version: {agent_name}/{version.version}")
    except Exception as e:
        print(f"Error deleting agent: {e}")
    
    await sales_data.close()


def handle_function_calls(openai_client, agent_name: str, conversation_id: str, response):
    """Handle function tool calls from the agent."""
    if not hasattr(response, 'tool_calls') or not response.tool_calls:
        return response
    
    print(f"Agent requested {len(response.tool_calls)} function call(s)")
    
    tool_results = []
    for tool_call in response.tool_calls:
        if tool_call.type == "function":
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"Executing function: {function_name}")
            print(f"Arguments: {function_args}")
            
            # Execute the function (note: calling async function synchronously here)
            if function_name == "fetch_sales_data_using_sqlite_query":
                # Run the async function
                import asyncio
                result = asyncio.run(fetch_sales_data_using_sqlite_query(function_args.get("sqlite_query", "")))
                tool_results.append({
                    "type": "tool_result",
                    "tool_call_id": tool_call.id,
                    "content": result
                })
    
    # Add tool results to conversation
    if tool_results:
        print("Submitting function results...")
        openai_client.conversations.items.create(
            conversation_id=conversation_id,
            items=tool_results
        )
        
        # Get a new response with the tool results
        return openai_client.responses.create(
            conversation=conversation_id,
            extra_body={"agent": {"name": agent_name, "type": "agent_reference"}},
            input=""
        )
    
    return response


def post_message(
    project_client: AIProjectClient,
    openai_client,
    agent_name: str,
    conversation_id: str,
    content: str
) -> None:
    """Post a message and get agent response."""
    try:
        # Add user message to conversation
        print(f"\nUser: {content}")
        openai_client.conversations.items.create(
            conversation_id=conversation_id,
            items=[{"type": "message", "role": "user", "content": content}]
        )
        
        # Get agent response
        response = openai_client.responses.create(
            conversation=conversation_id,
            extra_body={"agent": {"name": agent_name, "type": "agent_reference"}},
            input=""
        )
        
        # Handle function calls if any
        max_iterations = 5
        iteration = 0
        while hasattr(response, 'tool_calls') and response.tool_calls and iteration < max_iterations:
            response = handle_function_calls(openai_client, agent_name, conversation_id, response)
            iteration += 1
        
        if iteration >= max_iterations:
            print("Warning: Maximum function call iterations reached")
        
        # Display the response
        print(f"\nAgent: {response.output_text}")

    except Exception as e:
        print(f"An error occurred posting the message: {str(e)}")
        import traceback
        traceback.print_exc()


async def main() -> None:
    """
    Main function to run the agent.
    Example questions: Sales by region, top-selling products, total shipping costs by region.
    """
    # Ensure we're in the correct directory for database access
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    endpoint = PROJECT_ENDPOINT
    
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        # Initialize agent
        agent = await initialize(project_client)
        agent_name = agent.name
        
        # Create conversation
        conversation = openai_client.conversations.create()
        print(f"Created conversation (id: {conversation.id})")
        
        # Interactive loop
        while True:
            print("\n")
            prompt = input(f"{tc.GREEN}Enter your query (type exit to finish): {tc.RESET}")
            if prompt.lower() == "exit":
                break
            if not prompt:
                continue
            
            post_message(
                project_client=project_client,
                openai_client=openai_client,
                agent_name=agent_name,
                conversation_id=conversation.id,
                content=prompt
            )
        
        # Cleanup
        await cleanup(project_client, agent_name)


if __name__ == "__main__":
    print("Starting Azure AI Projects 2.0 Workshop Application...")
    asyncio.run(main())
    print("Program finished.")
