import csv
from pathlib import Path


REQUIRED_COLUMNS = [
    "date",
    "resourceId",
    "resourceGroupName",
    "serviceName",
    "meterCategory",
    "meterSubCategory",
    "costInBillingCurrency",
    "billingCurrency",
    "tags",
]


def test_sample_csv_has_required_columns():
    p = Path(__file__).parent.parent.resolve()
    csv_path = p / "data" / "azure-cost-export-sample.csv"
    assert csv_path.exists(), f"Sample CSV not found at {csv_path}"
    with open(csv_path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        assert not missing, f"CSV missing required columns: {missing}"


def test_loader_parses_rows_and_fields():
    # Import here so pytest can discover test without importing sample package at collection time
    p = Path(__file__).parent.parent.resolve()
    import sys

    sys.path.insert(0, str(p))
    from loaders import load_cost_rows

    csv_path = p / "data" / "azure-cost-export-sample.csv"
    rows = load_cost_rows(csv_path)
    assert len(rows) > 0, "Loader returned no rows"

    # Verify first few fields on each row
    for r in rows:
        assert getattr(r, "resource_id", None) is not None
        assert isinstance(r.cost_amount, float)
        assert getattr(r, "currency", None) is not None
        assert isinstance(r.tags, dict)
