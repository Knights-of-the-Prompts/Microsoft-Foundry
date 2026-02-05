#!/usr/bin/env python3
"""Debug script to understand response structure"""

import asyncio
import os
import json
import sys
from datetime import date
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from sales_data import SalesData
from azure.ai.projects.models import FunctionTool, PromptAgentDefinition

sales_data = SalesData()

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
API_DEPLOYMENT_NAME = os.getenv("API_DEPLOYMENT_NAME")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.7))

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

async def fetch_sales_data_using_sqlite_query(sqlite_query: str) -> str:
    """Fetch sales data using a SQLite query."""
    try:
        result = await sales_data.async_fetch_sales_data_using_sqlite_query(sqlite_query)
        return result
    except Exception as e:
        import json as json_module
        return json_module.dumps({"error": str(e)})

async def test_response_structure():
    """Test to understand response structure"""
    print("Starting debug test...")
    
    await sales_data.connect()
    
    endpoint = PROJECT_ENDPOINT
    
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
        project_client.get_openai_client() as openai_client,
    ):
        # Create agent
        print("\nCreating agent...")
        agent = project_client.agents.create_version(
            agent_name="ContosoSalesAgent",
            definition=PromptAgentDefinition(
                model=API_DEPLOYMENT_NAME,
                instructions="You are a sales assistant. Help analyze sales data by making function calls.",
                tools=[function_tool],
                temperature=TEMPERATURE,
            ),
        )
        print(f"Created agent: {agent.name}")
        
        # Send message and debug the response
        print("\n=== SENDING MESSAGE ===")
        response = openai_client.responses.create(
            input=[{"role": "user", "content": "What are the total sales by region?"}],
            extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
        )
        
        print(f"\nResponse type: {type(response)}")
        print(f"Response: {response}")
        
        # Convert to list
        response_items = []
        try:
            if isinstance(response, list):
                response_items = response
            elif hasattr(response, '__iter__') and not isinstance(response, str):
                response_items = list(response)
            else:
                response_items = [response]
        except:
            response_items = [response]
        
        print(f"\nTotal items: {len(response_items)}")
        print("\n=== ITEM BREAKDOWN ===")
        
        for idx, item in enumerate(response_items):
            item_type = getattr(item, 'type', 'NO_TYPE_ATTR')
            item_class = item.__class__.__name__
            print(f"{idx}: {item_class} (type={item_type})")
            
            if item_type == 'function_call':
                print(f"   Function: {getattr(item, 'name', 'N/A')}")
                print(f"   Args: {getattr(item, 'arguments', 'N/A')[:100]}...")
            elif item_type == 'message':
                if hasattr(item, 'content'):
                    print(f"   Content type: {type(item.content)}")
                    if isinstance(item.content, list):
                        for c_idx, c in enumerate(item.content):
                            print(f"     [{c_idx}] {c.__class__.__name__}")
        
        # Cleanup
        print("\n\nCleaning up...")
        versions = project_client.agents.list_versions(agent_name=agent.name)
        for version in versions:
            project_client.agents.delete_version(agent_name=agent.name, agent_version=version.version)
            print(f"Deleted agent version: {agent.name}/{version.version}")

if __name__ == "__main__":
    asyncio.run(test_response_structure())
