"""
render_decision_package.py

Renders a LifecycleDecisionPackage to Markdown and JSON files
in the outputs/ directory.
"""

from __future__ import annotations

import dataclasses
import json
import os
from datetime import datetime, timezone

from models import LifecycleDecisionPackage


def write_decision_package(
    package: LifecycleDecisionPackage,
    output_dir: str = "outputs",
) -> tuple[str, str]:
    """
    Write the lifecycle decision package to Markdown and JSON files.

    Returns (markdown_path, json_path).
    """
    os.makedirs(output_dir, exist_ok=True)

    md_path = os.path.join(output_dir, "lifecycle-decision-package.md")
    json_path = os.path.join(output_dir, "lifecycle-decision-package.json")

    _write_markdown(package, md_path)
    _write_json(package, json_path)

    return md_path, json_path


def _write_markdown(package: LifecycleDecisionPackage, path: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    gate_rows = "\n".join(
        f"| {g.gate_name} | {g.status} | {g.message} |"
        for g in package.gate_results
    )

    required_actions_md = (
        "\n".join(f"- {a}" for a in package.required_actions)
        if package.required_actions
        else "- None"
    )

    content = f"""# Lifecycle Decision Package

*Generated: {timestamp}*

## Agent

- **Name:** {package.display_name}
- **Agent ID:** {package.agent_id}
- **Owner:** {package.owner_email}
- **Sponsor:** {package.sponsor_email}

## Decision

- **Current state:** {package.current_state}
- **Recommended action:** {package.recommended_action}
- **Recommended state:** {package.recommended_state}

## Gate Results

| Gate | Status | Message |
|---|---|---|
{gate_rows}

## Required Actions

{required_actions_md}

## Explanation

{package.explanation}
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def _write_json(package: LifecycleDecisionPackage, path: str) -> None:
    data = dataclasses.asdict(package)
    data["generated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
