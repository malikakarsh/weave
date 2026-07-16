import csv
import os
import tempfile

import pytest

from models import AxisMapping


def _write_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def tmp_csv(tmp_path):
    """Return a helper that writes rows to a temp CSV and returns the path."""
    def _make(rows: list[dict], filename: str = "data.csv") -> str:
        p = tmp_path / filename
        _write_csv(str(p), rows)
        return str(p)
    return _make


@pytest.fixture
def flat_mapping():
    """Minimal flat bar-chart mapping for transformer tests."""
    return AxisMapping(
        chart_type="bar",
        x_column="name",
        y_column="value",
        aggregation="sum",
        sort_order="none",
    )
