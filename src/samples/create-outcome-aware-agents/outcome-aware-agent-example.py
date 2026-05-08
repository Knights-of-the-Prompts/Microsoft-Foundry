"""Workshop entry-point: runs the Outcome-Aware Agent locally and prints the
value-attribution ledger to the terminal.

The agent and ledger classes live in ``agent.py`` so they can also be imported
by ``app.py`` (the FastAPI UI). Run this file directly for the pure-Python
demo; run ``uvicorn app:app --reload`` for the web UI.
"""

from agent import OutcomeAwareAgent


def main() -> None:
    agent = OutcomeAwareAgent()

    print("Starting Outcome-Aware Agent Demo...")
    agent.run_tasks()

    agent.ledger.print_ledger()

    report = agent.get_value_report()
    print(f"Total Value Created: {report['total_entries']} tasks completed")
    print(f"Total Hours Saved: {report['total_hours_saved']} hours")


if __name__ == "__main__":
    main()
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import asdict

from ledger_store import LedgerStore, InMemoryLedgerStore, ValueEntry


class ValueLedger:
    """Manages the ledger of value attribution.

    Storage is delegated to a pluggable ``LedgerStore`` so the same agent code
    can run against an in-memory list (for the local workshop demo) or against
    Azure Confidential Ledger (for tamper-evident, durable persistence).
    """

    def __init__(self, store: Optional[LedgerStore] = None):
        self.store: LedgerStore = store or InMemoryLedgerStore()

    @property
    def entries(self):
        return self.store.list_entries()

    def add_entry(self, task_description: str, hours_saved: float, materialized_value: str, agent_action: str) -> None:
        """Add a new entry to the value ledger."""
        entry = ValueEntry(
            timestamp=datetime.now().isoformat(),
            task_description=task_description,
            hours_saved=hours_saved,
            materialized_value=materialized_value,
            agent_action=agent_action,
        )
        self.store.append(entry)

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all value attribution."""
        entries = self.store.list_entries()
        total_hours_saved = sum(entry.hours_saved for entry in entries)
        return {
            "total_entries": len(entries),
            "total_hours_saved": total_hours_saved,
            "entries": [asdict(entry) for entry in entries],
        }
    
    def print_ledger(self) -> None:
        """Print the ledger in a readable format."""
        print("\n" + "="*80)
        print("VALUE ATTRIBUTION LEDGER")
        print("="*80)
        for i, entry in enumerate(self.entries, 1):
            print(f"\nEntry {i}:")
            print(f"  Timestamp: {entry.timestamp}")
            print(f"  Task: {entry.task_description}")
            print(f"  Agent Action: {entry.agent_action}")
            print(f"  Hours Saved: {entry.hours_saved}")
            print(f"  Materialized Value: {entry.materialized_value}")
        
        summary = self.get_summary()
        print(f"\n{'-'*80}")
        print(f"SUMMARY - Total Hours Saved: {summary['total_hours_saved']}")
        print("="*80 + "\n")


class OutcomeAwareAgent:
    """A simple agent that performs tasks and tracks value attribution."""

    def __init__(self, ledger: Optional[ValueLedger] = None):
        self.ledger = ledger or ValueLedger()
    
    def process_customer_inquiry(self, inquiry: str) -> None:
        """Simulate processing a customer inquiry and log value."""
        self.ledger.add_entry(
            task_description="Customer Inquiry Processing",
            hours_saved=2.5,
            materialized_value="Won a new customer contract",
            agent_action=f"Processed inquiry: {inquiry}"
        )
    
    def automate_report_generation(self, report_type: str) -> None:
        """Simulate automating report generation and log value."""
        self.ledger.add_entry(
            task_description="Report Generation Automation",
            hours_saved=4.0,
            materialized_value="Improved reporting accuracy by 30%",
            agent_action=f"Generated automated {report_type} report"
        )
    
    def optimize_resource_allocation(self, resource_type: str) -> None:
        """Simulate resource optimization and log value."""
        self.ledger.add_entry(
            task_description="Resource Allocation Optimization",
            hours_saved=1.5,
            materialized_value="Hired 2 new talents with optimized budget",
            agent_action=f"Optimized allocation of {resource_type}"
        )
    
    def run_tasks(self) -> None:
        """Execute a set of example tasks."""
        self.process_customer_inquiry("Product pricing question")
        self.automate_report_generation("monthly sales")
        self.optimize_resource_allocation("engineering team budget")
    
    def get_value_report(self) -> Dict[str, Any]:
        """Return the current value attribution report."""
        return self.ledger.get_summary()


def main():
    """Main function to demonstrate the outcome-aware agent."""
    agent = OutcomeAwareAgent()
    
    print("Starting Outcome-Aware Agent Demo...")
    agent.run_tasks()
    
    agent.ledger.print_ledger()
    
    report = agent.get_value_report()
    print(f"Total Value Created: {report['total_entries']} tasks completed")
    print(f"Total Hours Saved: {report['total_hours_saved']} hours")


if __name__ == "__main__":
    main()