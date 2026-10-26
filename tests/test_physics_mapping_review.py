"""Regression tests for conservative physical mapping review.

No suggestion may bypass the explicit profile requirement for unknown headerless files.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import polars as pl

from battery_data_standard.inspection import inspect
from battery_data_standard.physics_mapping import (
    _capacity_relation,
    _power_relation,
    review_mapped_physics,
    suggest_headerless_columns,
)
from battery_data_standard.reports import ColumnProvenance


def _two_row_headerless(path: Path) -> None:
    path.write_text(
        "11/7/2018 5:08:07 PM,3,PAU,00:00:00.000,00:00:00.000,"
        "0,0,NN_Char_Charge,3.38427,0.00000,38.06739,0,0,2,\n"
        "11/7/2018 5:08:08 PM,3,CHA,00:00:01.000,00:00:01.000,"
        "0,0,NN_Char_Charge,3.39000,1.50000,38.10000,0,0,2,\n",
        encoding="utf-8",
    )


def test_headerless_backend_names_are_stably_one_based(tmp_path):
    """The position labels must not shift with pandas or Polars releases."""
    from battery_data_standard.io import (
        _canonicalize_headerless_positions,
        read_table_with_metadata,
    )

    zero_based = pl.DataFrame({f"column_{idx}": [idx] for idx in range(10)})
    renamed = _canonicalize_headerless_positions(zero_based)
    assert renamed.columns == [f"column_{idx}" for idx in range(1, 11)]
    assert renamed["column_9"].to_list() == [8]

    one_based = pl.DataFrame({f"column_{idx}": [idx] for idx in range(1, 11)})
    assert _canonicalize_headerless_positions(one_based).columns == one_based.columns

    source = tmp_path / "557_Charge10.csv"
    _two_row_headerless(source)
    result = read_table_with_metadata(source, options={"allow_headerless": True})
    assert result.metadata["has_header"] is False
    assert result.data.columns[0] == "column_1"
    assert result.data["column_9"].to_list() == [3.38427, 3.39]
    assert result.data["column_10"].to_list() == [0.0, 1.5]


def test_two_row_fixture_only_suggests_mapping_without_silent_conversion(tmp_path):
    path = tmp_path / "557_Charge10.csv"
    _two_row_headerless(path)
    original = path.read_bytes()

    suggestions = suggest_headerless_columns(path)
    fields = {(item["field"], item["column"]) for item in suggestions["candidates"]}
    assert suggestions["status"] == "needs_confirmation"
    assert ("voltage_candidate", "column_9") in fields
    assert ("current_candidate", "column_10") in fields
    assert ("elapsed_time_candidate", "column_4") in fields
    assert ("elapsed_time_candidate", "column_5") in fields
    assert all(item["status"] == "needs_confirmation" for item in suggestions["candidates"])
    assert suggestions["physics_checks"][0]["status"] == "not_assessable"
    assert path.read_bytes() == original


def test_inspect_error_keeps_headerless_file_blocked(tmp_path):
    path = tmp_path / "557_Charge10.csv"
    _two_row_headerless(path)
    report = inspect(path, cycler="generic")
    assert report.readable is False
    assert report.inspection_status in {"failed", "unsupported"}
    assert report.mapping_suggestions is not None
    assert report.mapping_suggestions["status"] == "needs_confirmation"
    assert "Unapproved mapping suggestions" in report.to_text()
    assert report.to_dict()["mapping_suggestions"]["candidates"]
    assert path.read_text(encoding="utf-8").count("\n") == 2


def test_physical_relations_require_multiple_samples():
    result = _power_relation([3.4, 3.5], [0.0, 1.5], [0.0, 5.25])
    assert result["status"] == "not_assessable"
    capacity = _capacity_relation([0.0, 1.0], [0.0, 1.5], [0.0, 0.0002])
    assert capacity["status"] == "not_assessable"


def test_mapped_physics_checks_independently_measured_columns():
    times = list(range(0, 3600, 300))
    currents = [0.0] + [1.0] * (len(times) - 1)
    voltage = [3.85 - 0.01 * x for x in range(len(times))]
    power = [v * i for v, i in zip(voltage, currents, strict=True)]
    capacity = [0.0]
    for index in range(1, len(times)):
        capacity.append(capacity[-1] + (currents[index - 1] + currents[index]) * 0.5 * 300 / 3600)
    frame = pl.DataFrame(
        {
            "test_time_s": times,
            "voltage_v": voltage,
            "current_a": currents,
            "power_w": power,
            "charge_capacity_ah": capacity,
        }
    )
    provenance = [
        ColumnProvenance(column="power_w", source="Power (W)"),
        ColumnProvenance(column="charge_capacity_ah", source="Charging Capacity (Ah)"),
    ]
    checks = review_mapped_physics(frame, provenance)
    statuses = {c["check"]: c["status"] for c in checks}
    assert statuses["test_time_progression"] == "consistent_screen"
    assert statuses["source_power_vs_voltage_current"] == "consistent_screen"
    assert statuses["source_capacity_vs_integrated_current"] == "consistent_screen"

    # Synthetic derived power is circular evidence, so do not claim independence.
    derived = [ColumnProvenance(column="power_w", source="derived from voltage and current")]
    assert not any(
        check["check"] == "source_power_vs_voltage_current" for check in review_mapped_physics(frame, derived)
    )

    corrupted = frame.with_columns((pl.col("power_w") * 1.5).alias("power_w"))
    invalid = review_mapped_physics(corrupted, provenance)
    assert (
        next(c for c in invalid if c["check"] == "source_power_vs_voltage_current")["status"]
        == "inconsistent_screen"
    )


def test_headerless_power_capacity_consistency_is_only_a_candidate(tmp_path):
    path = tmp_path / "unknown.csv"
    times = list(range(0, 3600, 300))
    currents = [0.0] + [1.0] * (len(times) - 1)
    voltages = [3.9 - 0.012 * n for n in range(len(times))]
    capacity = 0.0
    records = []
    for index, (time, voltage, current) in enumerate(zip(times, voltages, currents, strict=True)):
        if index:
            capacity += 0.5 * (currents[index - 1] + current) * 300 / 3600
        records.append([time, voltage, current, voltage * current, capacity])
    pd.DataFrame(records).to_csv(path, header=False, index=False)

    result = suggest_headerless_columns(path)
    assert result["status"] == "needs_confirmation"
    assert any(
        check["check"] == "power_vs_voltage_current" and check["status"] == "consistent_screen"
        for check in result["physics_checks"]
    )
    assert any(
        check["check"] == "capacity_vs_integrated_current" and check["status"] == "consistent_screen"
        for check in result["physics_checks"]
    )
    assert result["candidates"]
    assert all(candidate["status"] == "needs_confirmation" for candidate in result["candidates"])
    assert "original file" not in json.dumps(result)
