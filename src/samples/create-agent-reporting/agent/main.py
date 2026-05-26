"""
Create and interact with the ITHelpDeskAgent in Microsoft Foundry.

After creation the agent is automatically discoverable in the
Microsoft 365 admin center under:
    Agents > All agents > Registry

The Entra agent ID printed on first run must be saved to .env as
AGENT_GUID so governance/set_ownership.py can assign Owner and Sponsor.

Usage:
    python agent/main.py
"""

import asyncio
import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(dotenv_path=_ENV)

PROJECT_ENDPOINT = os.environ["PROJECT_ENDPOINT"]
MODEL = os.getenv("AGENT_MODEL_DEPLOYMENT_NAME", "gpt-4o")
AGENT_NAME = "ITHelpDeskAgent"
AGENT_DESCRIPTION = "IT Help Desk FAQ agent — Agent 365 governance demonstration"


async def get_or_create_agent(client: AIProjectClient):
    """Return the existing agent version or create a new one."""
    try:
        versions = client.agents.list_versions(agent_name=AGENT_NAME)
        if versions:
            agent = versions[0]
            agent_guid = getattr(agent, "agent_guid", None)
            print(f"Reusing existing agent : {agent.name}/{agent.version}")
            if agent_guid:
                print(f"Entra agent ID         : {agent_guid}")
            return agent
    except Exception:
        pass

    instructions_path = os.path.join(os.path.dirname(__file__), "instructions.md")
    with open(instructions_path, "r", encoding="utf-8") as f:
        instructions = f.read()

    print(f"Creating agent '{AGENT_NAME}' ...")
    agent = client.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL,
            instructions=instructions,
            temperature=0.2,
        ),
        description=AGENT_DESCRIPTION,
    )

    agent_guid = getattr(agent, "agent_guid", None)
    print(f"Created agent          : {agent.name}/{agent.version}")
    if agent_guid:
        print(f"Entra agent ID         : {agent_guid}")
        print(f"\n  → Add to .env:  AGENT_GUID={agent_guid}")
        print(  "  → Then run:     python governance/set_ownership.py")

    return agent


async def chat(openai_client, agent) -> None:
    """Interactive chat loop."""
    print("\nAgent ready. Type an IT support question or 'exit' to quit.\n")
    agent_ref = {
        "agent_reference": {
            "type": "agent_reference",
            "name": agent.name,
            "version": agent.version,
        }
    }
    while True:
        question = input("You: ").strip()
        if question.lower() in ("exit", "quit", ""):
            break
        if not question:
            continue
        try:
            response = openai_client.responses.create(
                model=MODEL,
                input=[{"role": "user", "content": question}],
                extra_body=agent_ref,
            )
            for item in response.output:
                if getattr(item, "type", None) == "message":
                    for c in item.content or []:
                        if hasattr(c, "text"):
                            print(f"\nAgent: {c.text}\n")
        except Exception as exc:
            print(f"Error: {exc}")


async def main() -> None:
    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(PROJECT_ENDPOINT, credential=credential) as client,
        client.get_openai_client() as openai_client,
    ):
        agent = await get_or_create_agent(client)
        await chat(openai_client, agent)


if __name__ == "__main__":
    asyncio.run(main())
