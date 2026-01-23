import asyncio
from datetime import date
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    Agent,
    AgentThread,
    AsyncFunctionTool,
    AsyncToolSet,
    CodeInterpreterTool,
    FileSearchTool,
    MessageRole,
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

toolset = AsyncToolSet()
sales_data = SalesData()
utilities = Utilities()

# Project client initialization (outside the context manager for global access)
# Try different client initialization approaches
try:
    # Method 1: Full endpoint approach
    if "/api/projects/" in PROJECT_ENDPOINT:
        project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
        )
        # Access agents through AIProjectClient (correct for SDK 2.0)
        agents_client = project_client.agents
        print(f"Using full project endpoint: {PROJECT_ENDPOINT}")
    else:
        # Method 2: Base endpoint approach
        project_client = AIProjectClient(
            endpoint=PROJECT_ENDPOINT,
            credential=DefaultAzureCredential(),
            subscription_id=AZURE_SUBSCRIPTION_ID,
            resource_group_name=AZURE_RESOURCE_GROUP_NAME,
            project_name=AZURE_PROJECT_NAME,
        )
        agents_client = project_client.agents
        print(f"Using base endpoint with project details: {PROJECT_ENDPOINT}")
except Exception as e:
    print(f"Error creating project client: {e}")
    # Fallback: try with just endpoint
    project_client = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )
    agents_client = project_client.agents
    print("Using fallback client configuration")

functions = AsyncFunctionTool(
    {
        sales_data.async_fetch_sales_data_using_sqlite_query,
    }
)

INSTRUCTIONS_FILE = "instructions/instructions_function_calling.txt"
# INSTRUCTIONS_FILE = "instructions/instructions_code_interpreter.txt"
# INSTRUCTIONS_FILE = "instructions/instructions_file_search.txt"


async def add_agent_tools():
    """Add tools for the agent."""

    # # Add the functions tool
    toolset.add(functions)

    # # Add the code interpreter tool
    # code_interpreter = CodeInterpreterTool()
    # toolset.add(code_interpreter)

    # # Add file search tool - uncomment to enable file search capability
    # print("Creating vector store for file search...")
    # try:
    #     vector_store = utilities.create_vector_store(
    #         project_client,
    #         files=[TENTS_DATA_SHEET_FILE],
    #         vector_store_name="Contoso Product Information Vector Store",
    #     )
    #     file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])
    #     toolset.add(file_search_tool)
    #     print(f"File search tool added with vector store: {vector_store.id}")
    # except Exception as e:
    #     print(f"Error creating file search tool: {e}")
    #     print("Continuing without file search capability...")


async def initialize() -> tuple[Agent, AgentThread]:
    """Initialize the agent with the sales data schema and instructions."""
    agent = None
    thread = None

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

        # Add agent tools (this must be done inside the context manager)
        await add_agent_tools()

        # Create agent and thread without closing the context manager
        print("Creating agent...")
        agent = agents_client.create_agent(
            model=API_DEPLOYMENT_NAME,
            name="Contoso Sales AI Agent",
            instructions=instructions,
            toolset=toolset,
            temperature=TEMPERATURE,
        )
        print(f"Created agent, ID: {agent.id}")

        # Create thread
        print("Creating thread...")
        thread = agents_client.threads.create()
        print(f"Created thread, ID: {thread.id}")

        return agent, thread

    except Exception as e:
        logger.error("An error occurred initializing the agent: %s", str(e))
        logger.error("Please ensure you've enabled an instructions file.")
        raise


async def cleanup(agent: Agent, thread: AgentThread) -> None:
    """Cleanup the resources."""
    try:
        agents_client.delete_agent(agent.id)
        print(f"Deleted agent: {agent.id}")
    except Exception as e:
        print(f"Error deleting agent: {e}")
    
    await sales_data.close()


async def post_message(thread_id: str, content: str, agent: Agent, thread: AgentThread) -> None:
    """Post a message to the Azure AI Agent Service."""
    try:
        print(f"Creating message in thread {thread_id}...")
        
        # Create message using agents_client
        message = agents_client.messages.create(
            thread_id=thread_id,
            role="user",
            content=content,
        )
        print(f"Message created: {message.id}")

        print(f"Creating run for agent {agent.id}...")
        # Create and poll run
        run = agents_client.runs.create(
            thread_id=thread.id,
            agent_id=agent.id,
        )
        print(f"Run created: {run.id}")
        
        # Enhanced polling with action handling
        import time
        max_iterations = 120  # Max 2 minutes
        iteration = 0
        
        while run.status in ("queued", "in_progress", "requires_action") and iteration < max_iterations:
            time.sleep(2)  # Increased sleep time
            iteration += 1
            
            try:
                run = agents_client.runs.get(thread_id=thread.id, run_id=run.id)
                print(f"Run status: {run.status} (iteration {iteration})")
            except Exception as e:
                print(f"Error getting run status: {e}")
                time.sleep(5)  # Wait longer on error
                continue
            
            # Handle required actions (function calls)
            if run.status == "requires_action" and run.required_action:
                print("Run requires action - handling function calls...")
                
                tool_outputs = []
                try:
                    for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                        print(f"Executing function: {tool_call.function.name}")
                        
                        # Execute the function call
                        if tool_call.function.name == "async_fetch_sales_data_using_sqlite_query":
                            import json
                            args = json.loads(tool_call.function.arguments)
                            result = await sales_data.async_fetch_sales_data_using_sqlite_query(args["sqlite_query"])
                            tool_outputs.append({
                                "tool_call_id": tool_call.id,
                                "output": result
                            })
                    
                    # Submit the tool outputs
                    if tool_outputs:
                        print("Submitting tool outputs...")
                        run = agents_client.runs.submit_tool_outputs(
                            thread_id=thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                        print("Tool outputs submitted successfully")
                except Exception as e:
                    print(f"Error handling tool outputs: {e}")
                    break
        
        if iteration >= max_iterations:
            print("Run timed out after maximum iterations")
            return
            
        print(f"Run finished with status: {run.status}")
        
        if run.status == "failed":
            print(f"Run failed: {run.last_error}")
        elif run.status == "completed":
            # Get the last message from the agent
            try:
                messages = agents_client.messages.list(thread_id=thread_id)
                # Get the first message (most recent) from assistant
                if messages.data:
                    for msg in messages.data:
                        if msg.role == "assistant":
                            print("\nAgent response:")
                            for content in msg.content:
                                if hasattr(content, 'text') and hasattr(content.text, 'value'):
                                    print(content.text.value)
                            break
                else:
                    print("No response message found")
                
                # Handle file downloads from code interpreter
                try:
                    utilities.download_agent_files(project_client, thread_id)
                except Exception as e:
                    print(f"Error handling file downloads: {e}")
                    
            except Exception as e:
                print(f"Error getting response message: {e}")

    except Exception as e:
        print(f"An error occurred posting the message: {str(e)}")
        import traceback
        traceback.print_exc()


async def main() -> None:
    """
    Main function to run the agent.
    Example questions: Sales by region, top-selling products, total shipping costs by region, show as a pie chart.
    """
    # Use the project client within a context manager for the entire session
    with project_client:
        agent, thread = await initialize()

        while True:
            # Get user input prompt in the terminal using a pretty shade of green
            print("\n")
            prompt = input(f"{tc.GREEN}Enter your query (type exit to finish): {tc.RESET}")
            if prompt.lower() == "exit":
                break
            if not prompt:
                continue
            await post_message(agent=agent, thread_id=thread.id, content=prompt, thread=thread)

        await cleanup(agent, thread)


if __name__ == "__main__":
    print("Starting async program...")
    asyncio.run(main())
    print("Program finished.")
