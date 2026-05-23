"""
Simulate usage by sending sample IT Help Desk questions to ITHelpDeskAgent.

This generates metric data in Azure Monitor (TokenTransaction, SuccessfulCalls,
TotalErrors, Latency) that the Azure Monitor Workbook and the governance report
can visualize.

Usage:
    python monitoring/simulate_usage.py           # sends 10 questions
    python monitoring/simulate_usage.py --count 25
"""

import argparse
import asyncio
import os
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

_ENV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(dotenv_path=_ENV)

AGENT_NAME = "ITHelpDeskAgent"

SAMPLE_QUESTIONS = [
    "How do I reset my Windows login password?",
    "My VPN keeps disconnecting every few minutes, what should I do?",
    "I can't access SharePoint — it says 'Access denied'. Can you help?",
    "How do I connect to the printer on the 3rd floor?",
    "My laptop is very slow after the latest Windows update. Any tips?",
    "Teams is not showing my calendar meetings. How do I fix this?",
    "How do I request a new software license?",
    "My Outlook is not syncing emails. What should I check?",
    "I accidentally deleted an important file. Can it be recovered?",
    "How do I set up multi-factor authentication on my account?",
]


async def run(count: int) -> None:
    project_endpoint = os.environ["PROJECT_ENDPOINT"]
    model = os.environ.get("AGENT_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(
        endpoint=project_endpoint,
        credential=credential,
    )

    # Find the agent
    agent = None
    versions = project_client.agents.list_versions(name=AGENT_NAME)
    for v in versions:
        agent = v
        break

    if agent is None:
        print(f"Error: Agent '{AGENT_NAME}' not found.")
        print("Run agent/main.py first to create the agent.")
        return

    print(f"Found agent '{agent.name}' (ID: {agent.id})")
    print(f"Sending {count} question(s) to generate metric data…")
    print()

    questions = (SAMPLE_QUESTIONS * (count // len(SAMPLE_QUESTIONS) + 1))[:count]

    openai_client = project_client.inference.get_azure_openai_client(api_version="2025-01-01-preview")

    for i, question in enumerate(questions, start=1):
        print(f"  [{i:>3}/{count}] {question[:60]}", end="", flush=True)
        try:
            response = openai_client.responses.create(
                model=model,
                input=question,
                extra_body={"agent_reference": {"agent_id": agent.id}},
            )
            output = getattr(response, "output_text", "")
            truncated = (output[:80] + "…") if len(output) > 80 else output
            print(f"\n           → {truncated}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n           ✗ Error: {exc}")

    print()
    print(f"Done. {count} request(s) sent.")
    print("Metrics will appear in Azure Monitor within a few minutes.")
    print("Open the Azure Monitor Workbook (deployed via infra/deploy.sh) to visualize.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate ITHelpDeskAgent usage")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of questions to send (default: 10)",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("Error: --count must be at least 1")
        sys.exit(1)

    asyncio.run(run(args.count))


if __name__ == "__main__":
    main()
