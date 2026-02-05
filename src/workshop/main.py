import asyncio
from datetime import date
import json
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    CodeInterpreterTool,
    FileSearchTool,
    FunctionTool,
    PromptAgentDefinition,
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

# Function tool definition
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
        "required": ["sqlite_query"],
        "additionalProperties": False
    },
    strict=True,
)

# Function to handle the function call
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
        import json
        return json.dumps({"error": str(e)})


# ============================================================================
# LEARNING EXERCISE: Tools & Instructions
# Uncomment the tool in get_tools() AND its corresponding INSTRUCTIONS_FILE
# to see the agent use that capability
# ============================================================================

# STEP 1: Function Calling - SQL Database Queries
INSTRUCTIONS_FILE = "instructions/instructions_function_calling.txt"

# STEP 2: Code Interpreter - Python Code Execution
# Uncomment the line below when you uncomment the Code Interpreter tool in get_tools()
# INSTRUCTIONS_FILE = "instructions/instructions_code_interpreter.txt"

# STEP 3: File Search - Knowledge Search over Documents
# Uncomment the line below when you uncomment the File Search tool in get_tools()
# INSTRUCTIONS_FILE = "instructions/instructions_file_search.txt"


async def get_tools(project_client: AIProjectClient) -> list:
    """Get tools for the agent to be registered with agents_client.
    
    LEARNING EXERCISE: Uncomment the tool sections below step by step to add capabilities.
    After uncommenting tools, restart the script to see the agent use them.
    """
    tools = []
    
    # ============================================================================
    # STEP 1: Function Tool - Enables SQL database queries
    # Start with this tool enabled to learn about function calling
    # ============================================================================
    tools.append(function_tool)
    
    # ============================================================================
    # STEP 2: Code Interpreter Tool - Enables Python code execution
    # Uncomment the lines below to add code execution capability to the agent
    # Then restart the script to enable this tool
    # ============================================================================
    # print("Adding Code Interpreter tool...")
    # code_interpreter = CodeInterpreterTool()
    # tools.append(code_interpreter)
    
    # ============================================================================
    # STEP 3: File Search Tool - Enables knowledge search over documents
    # Uncomment the lines below to add file search capability (requires vector store)
    # Then restart the script to enable this tool
    # ============================================================================
    # print("Adding File Search tool...")
    # try:
    #     # Create vector store for file search
    #     vector_store = project_client.agents.create_vector_store_and_files(
    #         file_paths=[TENTS_DATA_SHEET_FILE],
    #         vector_store_name="Contoso Product Information Vector Store",
    #     )
    #     print(f"Vector store created: {vector_store.id}")
    #     
    #     file_search = FileSearchTool(vector_store_ids=[vector_store.id])
    #     tools.append(file_search)
    #     print(f"File search tool added with vector store: {vector_store.id}")
    # except Exception as e:
    #     print(f"Error creating file search tools: {e}")
    #     print("Continuing without file search capability...")
    
    return tools


async def initialize(project_client: AIProjectClient):
    """Initialize the agent with the sales data schema and instructions."""
    
    await sales_data.connect()
    database_schema_string = await sales_data.get_database_info()

    try:
        env = os.getenv("ENVIRONMENT", "local")
        # Since we chdir to workshop directory, use relative path
        INSTRUCTIONS_FILE_PATH = INSTRUCTIONS_FILE
        
        with open(INSTRUCTIONS_FILE_PATH, "r", encoding="utf-8", errors="ignore") as file:
            instructions = file.read()

        # Replace the placeholder with the database schema string
        instructions = instructions.replace("{database_schema_string}", database_schema_string)
        instructions = instructions.replace("{current_date}", date.today().strftime("%Y-%m-%d"))

        # Get tools
        tools = await get_tools(project_client)

        # Create agent using create_version API with PromptAgentDefinition
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
        print(f"Created agent (id: {agent.id}, name: {agent.name})")

        return agent

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        raise


async def cleanup(project_client: AIProjectClient, agent) -> None:
    """Cleanup the resources."""
    try:
        if agent:
            # Delete all versions of the agent
            versions = project_client.agents.list_versions(agent_name=agent.name)
            for version in versions:
                project_client.agents.delete_version(agent_name=agent.name, agent_version=version.version)
                print(f"Deleted agent version: {agent.name}/{version.version}")
    except Exception as e:
        print(f"Error deleting agent: {e}")
    
    await sales_data.close()


async def handle_function_calls(openai_client, agent_name: str, tool_calls: list) -> None:
    """Handle function tool calls from the agent."""
    if not tool_calls:
        return
    
    print(f"Agent requested {len(tool_calls)} function call(s)")
    
    # Process each tool call
    for tool_call in tool_calls:
        if tool_call.type == "function":
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"Executing function: {function_name}")
            print(f"Arguments: {function_args}")
            
            if function_name == "fetch_sales_data_using_sqlite_query":
                result = await fetch_sales_data_using_sqlite_query(function_args.get("sqlite_query", ""))
                print(f"Function result: {result}")


async def post_message(
    openai_client,
    agent_name: str,
    content: str
) -> None:
    """Post a message and get agent response."""
    try:
        print(f"\nUser: {content}")
        
        # First turn: Agent processes the request and makes function calls
        response = openai_client.responses.create(
            input=[{"role": "user", "content": content}],
            extra_body={"agent": {"name": agent_name, "type": "agent_reference"}},
        )
        
        response_items = response.output if hasattr(response, 'output') else []
        
        # Process items looking for function calls
        function_data = {}
        
        for item in response_items:
            item_type = getattr(item, 'type', None)
            item_class = item.__class__.__name__
            
            # Look for function calls
            if 'FunctionToolCall' in item_class or item_type == 'function_call':
                if hasattr(item, 'name') and item.name == "fetch_sales_data_using_sqlite_query":
                    try:
                        args = json.loads(item.arguments) if isinstance(item.arguments, str) else item.arguments
                        result = await fetch_sales_data_using_sqlite_query(args.get("sqlite_query", ""))
                        try:
                            function_data['result'] = json.loads(result)
                        except:
                            function_data['result'] = result
                    except Exception as e:
                        function_data['error'] = str(e)
        
        # If a function was executed, ask the agent to format the result
        if function_data:
            result_json = json.dumps(function_data.get('result'), indent=2)
            format_request = f"Please format this query result as a markdown table:\n\n{result_json}"
            
            response2 = openai_client.responses.create(
                input=[{"role": "user", "content": format_request}],
                extra_body={"agent": {"name": agent_name, "type": "agent_reference"}},
            )
            
            response_items2 = response2.output if hasattr(response2, 'output') else []
            
            # Get the agent's formatted response
            for item in response_items2:
                item_class = item.__class__.__name__
                if 'OutputMessage' in item_class:
                    if hasattr(item, 'content'):
                        if isinstance(item.content, list):
                            for content_item in item.content:
                                if hasattr(content_item, 'text'):
                                    # Remove markdown code block wrappers if present
                                    text = content_item.text
                                    text = text.replace("```markdown\n", "").replace("\n```", "").replace("```", "")
                                    print(f"\n{text}")
                        elif hasattr(item.content, 'text'):
                            # Remove markdown code block wrappers if present
                            text = item.content.text
                            text = text.replace("```markdown\n", "").replace("\n```", "").replace("```", "")
                            print(f"\n{text}")

    except Exception as e:
        print(f"An error occurred posting the message: {str(e)}")
        import traceback
        traceback.print_exc()




async def main() -> None:
    """
    Main function to run the agent.
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
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
        
        # Interactive loop
        while True:
            print("\n")
            prompt = input(f"{tc.GREEN}Enter your query (type exit to finish): {tc.RESET}")
            if prompt.lower() == "exit":
                break
            if not prompt:
                continue
            
            await post_message(
                openai_client=openai_client,
                agent_name=agent_name,
                content=prompt
            )
        
        # Cleanup
        await cleanup(project_client, agent)


if __name__ == "__main__":
    print("Starting Azure AI Projects Workshop Application...")
    asyncio.run(main())
    print("Program finished.")
