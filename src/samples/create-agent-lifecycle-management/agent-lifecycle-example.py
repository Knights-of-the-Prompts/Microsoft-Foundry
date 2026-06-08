"""
agent-lifecycle-example.py

Entry point for the Agent Lifecycle Management sample.

Loads the agent profile, collects live Azure evidence,
evaluates lifecycle gates against the policy, and writes
a Lifecycle Decision Package to the outputs/ directory.
"""

import yaml

from collect_azure_evidence import collect_azure_evidence, load_agent_profile
from evaluate_lifecycle import evaluate_lifecycle
from render_decision_package import write_decision_package


def main() -> None:
    profile = load_agent_profile("agent_profile.yaml")
    evidence = collect_azure_evidence(profile)

    with open("lifecycle_policy.yaml", encoding="utf-8") as fh:
        policy = yaml.safe_load(fh)

    package = evaluate_lifecycle(profile, evidence, policy)

    print(f"\nAgent:    {package.display_name}")
    print(f"Owner:    {package.owner_email}")
    print(f"Sponsor:  {package.sponsor_email}")
    print(f"\nCurrent state:      {package.current_state}")
    print(f"Recommended action: {package.recommended_action}")
    print(f"Recommended state:  {package.recommended_state}")
    print(f"\nWhy:\n{package.explanation}")

    if package.required_actions:
        print("\nRequired actions:")
        for action in package.required_actions:
            print(f"  - {action}")

    if evidence.collection_warnings:
        print("\nAzure evidence warnings:")
        for w in evidence.collection_warnings:
            print(f"  - {w}")

    md_path, json_path = write_decision_package(package)
    print(f"\nDecision package written:")
    print(f"  {md_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
