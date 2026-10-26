"""Conservative physical-consistency screens and headerless column suggestions.

The checks produce review evidence, not a schema mapping or scientific acceptance.
No caller may use a suggested column as a conversion mapping without confirmation.
"""

from __future__ import annotations

import math
import re
from itertools import pairwise
from pathlib import Path
from typing import Any

import pandas as pd
import polars as pl

from .reports import ColumnProvenance

MAX_REVIEW_ROWS = 512
MAX_REVIEW_COLUMNS = 64
MIN_RELATION_POINTS = 6


def _finite_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _is_increasing(values: list[float]) -> bool:
    return (
        len(values) > 1
        and all(later >= earlier for earlier, later in pairwise(values))
        and values[-1] > values[0]
    )


def _power_relation(
    voltage: list[float],
    current: list[float],
    observed_power: list[float],
) -> dict[str, Any]:
    """Compare independent power samples under both possible sign conventions."""
    selected = [
        (v * i, p)
        for v, i, p in zip(voltage, current, observed_power, strict=False)
        if all(math.isfinite(x) for x in (v, i, p)) and abs(v * i) > 0.05
    ]
    if len(selected) < MIN_RELATION_POINTS:
        return {"status": "not_assessable", "reason": "Fewer than six active power samples"}
    # Use a scale-normalized residual, not a field-specific absolute error threshold.
    denominator = sum(max(abs(calculated), abs(recorded)) for calculated, recorded in selected)
    if denominator <= 0:
        return {"status": "not_assessable", "reason": "Power comparison has zero scale"}
    positive = sum(abs(calculated - recorded) for calculated, recorded in selected) / denominator
    negative = sum(abs(-calculated - recorded) for calculated, recorded in selected) / denominator
    error = min(positive, negative)
    return {
        "status": "consistent_screen" if error <= 0.05 else "inconsistent_screen",
        "observations": len(selected),
        "relative_residual": round(error, 7),
        "power_sign": "same_as_V_times_I" if positive <= negative else "opposite_to_V_times_I",
        "criterion": "scale-normalized absolute residual <= 0.05",
        "limitation": "A numerical identity cannot establish instrument identity, units or calibration.",
    }


def _capacity_relation(
    time: list[float],
    current: list[float],
    capacity: list[float],
    *,
    cycle: list[Any] | None = None,
    step: list[Any] | None = None,
) -> dict[str, Any]:
    """Screen capacity accumulation against current integration within stable steps."""
    integrated = observed = 0.0
    comparisons = reset_count = 0
    for index in range(1, min(len(time), len(current), len(capacity))):
        if cycle is not None and cycle[index] != cycle[index - 1]:
            continue
        if step is not None and step[index] != step[index - 1]:
            continue
        t0, t1 = time[index - 1 : index + 1]
        i0, i1 = current[index - 1 : index + 1]
        q0, q1 = capacity[index - 1 : index + 1]
        if not all(math.isfinite(x) for x in (t0, t1, i0, i1, q0, q1)):
            continue
        dt = t1 - t0
        dq = q1 - q0
        if dt <= 0:
            continue
        if dq < -1e-7:
            reset_count += 1
            continue
        if dq <= 1e-9:
            # Charge and discharge accumulators can be inactive on opposite steps.
            continue
        integrated += 0.5 * (abs(i0) + abs(i1)) * dt / 3600.0
        observed += dq
        comparisons += 1
    if comparisons < MIN_RELATION_POINTS or integrated < 0.001:
        return {
            "status": "not_assessable",
            "reason": "Insufficient increasing capacity samples in a stable measurement segment",
            "usable_intervals": comparisons,
            "excluded_resets": reset_count,
        }
    error = abs(observed - integrated)
    threshold = max(0.002, 0.05 * integrated)
    return {
        "status": "consistent_screen" if error <= threshold else "inconsistent_screen",
        "usable_intervals": comparisons,
        "excluded_resets": reset_count,
        "integrated_absolute_current_Ah": round(integrated, 8),
        "observed_capacity_change_Ah": round(observed, 8),
        "absolute_difference_Ah": round(error, 8),
        "criterion": "absolute difference <= max(0.002 Ah, 5% of integrated capacity)",
        "limitation": (
            "Assumes seconds, amperes, Ah and an increasing source accumulator; "
            "does not establish sign, charge/discharge mode or reset semantics."
        ),
    }


def _independent_source(provenance: list[ColumnProvenance], field: str) -> bool:
    """Exclude calculated fields to avoid a circular consistency check."""
    matches = [item for item in provenance if item.column == field]
    if not matches:
        return False
    for item in matches:
        origin = str(item.source or "").lower()
        transform = str(item.transform or "").lower()
        if (
            origin
            and not any(key in origin for key in ("derived", "calculated", "computed"))
            and not any(key in transform for key in ("derived", "calculated", "computed"))
        ):
            return True
    return False


def review_mapped_physics(
    frame: pl.DataFrame, provenance: list[ColumnProvenance], *, max_rows: int = 20000
) -> list[dict[str, Any]]:
    """Review source-backed cross-column relations without changing conversion status."""
    if frame.height == 0 or not {"test_time_s", "voltage_v", "current_a"} <= set(frame.columns):
        return []
    subset = frame.head(max_rows)
    time = [_finite_number(x) for x in subset["test_time_s"].to_list()]
    voltage = [_finite_number(x) for x in subset["voltage_v"].to_list()]
    current = [_finite_number(x) for x in subset["current_a"].to_list()]
    result: list[dict[str, Any]] = []
    valid_time = [x for x in time if x is not None]
    result.append(
        {
            "check": "test_time_progression",
            "status": "consistent_screen"
            if len(valid_time) == len(time) and _is_increasing(valid_time)
            else "inconsistent_screen",
            "observations": len(time),
            "limitation": "A monotonic time axis alone does not identify the time field.",
        }
    )
    if len(time) < MIN_RELATION_POINTS:
        return result
    if all(x is not None for x in (*voltage, *current)) and (
        "power_w" in subset.columns and _independent_source(provenance, "power_w")
    ):
        power = [_finite_number(x) for x in subset["power_w"].to_list()]
        if all(x is not None for x in power):
            result.append(
                {
                    "check": "source_power_vs_voltage_current",
                    **_power_relation(voltage, current, power),
                }
            )
    if all(x is not None for x in (*time, *current)):
        cycle = subset["cycle_index"].to_list() if "cycle_index" in subset.columns else None
        step = subset["step_index"].to_list() if "step_index" in subset.columns else None
        for field in ("charge_capacity_ah", "discharge_capacity_ah", "source_capacity_ah"):
            if field not in subset.columns or not _independent_source(provenance, field):
                continue
            capacity = [_finite_number(x) for x in subset[field].to_list()]
            if all(x is not None for x in capacity):
                result.append(
                    {
                        "check": "source_capacity_vs_integrated_current",
                        "capacity_column": field,
                        **_capacity_relation(time, current, capacity, cycle=cycle, step=step),
                    }
                )
    return result


def _read_sample(path: Path, sheet: str | int | None, max_rows: int) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        selected_sheet = sheet if sheet is not None else 0
        return pd.read_excel(path, header=None, dtype=str, nrows=max_rows, sheet_name=selected_sheet)
    if path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        return pd.read_csv(
            path,
            header=None,
            sep=None,
            engine="python",
            dtype=str,
            nrows=max_rows,
            encoding="utf-8-sig",
        )
    raise ValueError("Suggestions currently support CSV, TSV, text and Excel only")


def suggest_headerless_columns(
    path: str | Path, *, sheet: str | int | None = None, max_rows: int = MAX_REVIEW_ROWS
) -> dict[str, Any]:
    """Return unapproved column candidates from a bounded, read-only sample."""
    source = Path(path)
    report: dict[str, Any] = {
        "status": "needs_confirmation",
        "candidates": [],
        "physics_checks": [],
        "limitations": [
            "Column suggestions are not mappings and must never be passed to conversion automatically.",
            "Value ranges assume a single lithium-ion cell and do not cover arbitrary packs or units.",
        ],
    }
    try:
        sampled = _read_sample(source, sheet, max_rows)
    except (OSError, ValueError, UnicodeError, ImportError, KeyError) as exc:
        report["status"] = "not_assessable"
        report["limitations"].append(f"Source sample could not be read: {type(exc).__name__}")
        return report
    if sampled.empty or sampled.shape[1] > MAX_REVIEW_COLUMNS or sampled.shape[0] < 2:
        report["status"] = "not_assessable"
        report["limitations"].append("Source sample is empty, too wide or contains fewer than two rows.")
        return report
    report["sampled_rows"] = len(sampled)
    report["sampled_columns"] = int(sampled.shape[1])
    numeric: dict[str, list[float]] = {}
    time_candidates: dict[str, list[float]] = {}
    voltage_candidates: list[str] = []
    current_candidates: list[str] = []

    def add(field: str, column: str, evidence: str) -> None:
        if len([item for item in report["candidates"] if item["field"] == field]) < 5:
            report["candidates"].append(
                {
                    "field": field,
                    "column": column,
                    "evidence": evidence,
                    "status": "needs_confirmation",
                }
            )

    for idx in range(sampled.shape[1]):
        column = f"column_{idx + 1}"
        values = sampled.iloc[:, idx].fillna("").astype(str).str.strip()
        if (values == "").any():
            continue
        items = values.tolist()
        if all(re.fullmatch(r"\d{1,3}:\d{2}:\d{2}(?:\.\d+)?", x) for x in items):
            durations = pd.to_timedelta(values, errors="coerce").dt.total_seconds()
            if durations.notna().all():
                seconds = durations.astype(float).tolist()
                if _is_increasing(seconds):
                    time_candidates[column] = seconds
                    add(
                        "elapsed_time_candidate",
                        column,
                        "Monotonic HH:MM:SS values; total versus step time unknown",
                    )
            continue
        if all(re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\s+", x) for x in items):
            add("timestamp_candidate", column, "Date/time-like strings; not proof of elapsed test time")
            continue
        numbers = pd.to_numeric(values, errors="coerce")
        if numbers.isna().any():
            continue
        parsed = numbers.astype(float).tolist()
        if not all(math.isfinite(v) for v in parsed):
            continue
        numeric[column] = parsed
        low, high = min(parsed), max(parsed)
        if _is_increasing(parsed) and low >= -1e-6 and high - low >= 3:
            time_candidates[column] = parsed
            add("elapsed_time_candidate", column, "Monotonic numeric sequence; unit and time role unverified")
        if 1.8 <= low <= high <= 5.5 and high - low > 1e-5:
            voltage_candidates.append(column)
            add(
                "voltage_candidate",
                column,
                "Values plausible for one Li-ion cell; no independent unit evidence",
            )
        if (
            high - low > 0.05
            and max(abs(low), abs(high)) < 1000
            and (
                low < -0.02 < high
                or (any(abs(v) < 0.02 for v in parsed) and any(abs(v) > 0.2 for v in parsed))
            )
        ):
            current_candidates.append(column)
            add("current_candidate", column, "Current-like zero, polarity or step changes; unit unknown")
        if 10 <= low <= high <= 100 and high - low < 40:
            add("temperature_candidate", column, "Range plausible in degC; other quantities remain possible")

    if len(sampled) < MIN_RELATION_POINTS:
        report["physics_checks"].append(
            {
                "check": "cross_column_relations",
                "status": "not_assessable",
                "reason": "At least six observations and an independent power/capacity candidate are needed",
            }
        )
        return report

    for v_col in voltage_candidates[:4]:
        for i_col in current_candidates[:4]:
            if v_col == i_col:
                continue
            for p_col, power in numeric.items():
                if p_col in {v_col, i_col} or p_col in time_candidates:
                    continue
                result = _power_relation(numeric[v_col], numeric[i_col], power)
                if result["status"] == "consistent_screen":
                    add("power_candidate", p_col, "Numerically matches V times I; sign and units unverified")
                    report["physics_checks"].append(
                        {
                            "check": "power_vs_voltage_current",
                            "columns": {"voltage": v_col, "current": i_col, "power": p_col},
                            **result,
                        }
                    )
                if len(report["physics_checks"]) >= 10:
                    break

    for t_col, time in list(time_candidates.items())[:4]:
        for i_col in current_candidates[:4]:
            if t_col == i_col:
                continue
            for q_col, capacity in numeric.items():
                if q_col in {t_col, i_col} or q_col in voltage_candidates:
                    continue
                result = _capacity_relation(time, numeric[i_col], capacity)
                if result["status"] == "consistent_screen":
                    add(
                        "capacity_candidate",
                        q_col,
                        "Matches current integration under assumed units/reset policy",
                    )
                    report["physics_checks"].append(
                        {
                            "check": "capacity_vs_integrated_current",
                            "columns": {"time": t_col, "current": i_col, "capacity": q_col},
                            **result,
                        }
                    )
                if len(report["physics_checks"]) >= 20:
                    break
    if not report["physics_checks"]:
        report["physics_checks"].append(
            {
                "check": "cross_column_relations",
                "status": "not_assessable",
                "reason": "No independent source relationship could be established from the sample",
            }
        )
    return report
