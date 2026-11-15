"""Step and cycle summary helpers for normalized time-series data."""

from __future__ import annotations

import warnings

import polars as pl


def summarize_steps(df: pl.DataFrame) -> pl.DataFrame:
    """Summarize a normalized dataframe by cycle and step when available."""
    group_cols = [col for col in ("cycle_index", "step_index") if col in df.columns]
    if not group_cols:
        if "record_index" in df.columns:
            group_cols = ["record_index"]
        else:
            return _summary_for_whole_table(df, label="all")
    return _group_summary(df, group_cols)


def summarize_cycles(df: pl.DataFrame, *, capacity_reset: str = "unknown") -> pl.DataFrame:
    """Summarize a normalized dataframe by cycle when available."""
    if capacity_reset not in {"unknown", "step", "cycle"}:
        raise ValueError(
            "capacity_reset must be unknown, step or cycle; test-wide accumulators require a separate baseline-aware calculation."
        )
    result = (
        _group_summary(df, ["cycle_index"])
        if "cycle_index" in df.columns
        else _summary_for_whole_table(df, label="all")
    )
    accumulators = {
        "charge_capacity_ah": "Charging Capacity End / Ah",
        "discharge_capacity_ah": "Discharging Capacity End / Ah",
        "charge_energy_wh": "Charging Energy End / Wh",
        "discharge_energy_wh": "Discharging Energy End / Wh",
    }
    present = {key: value for key, value in accumulators.items() if key in df.columns}
    if capacity_reset == "unknown" and present:
        warnings.warn(
            "Accumulator reset scope is unknown; cycle summaries show recorded maxima, not total transferred charge or energy. Set capacity_reset='step' or 'cycle' after reviewing the protocol.",
            UserWarning,
            stacklevel=2,
        )
        return result.rename(
            {label: label.replace(" End", " Recorded Maximum") for label in present.values()}
        )
    if capacity_reset == "step" and present:
        if "step_index" not in df.columns or "cycle_index" not in df.columns:
            raise ValueError("Step-reset summaries require cycle_index and step_index.")
        segmented = df.with_columns(
            (pl.struct("cycle_index", "step_index") != pl.struct("cycle_index", "step_index").shift(1))
            .fill_null(True)
            .cast(pl.Int64)
            .cum_sum()
            .alias("__segment")
        )
        maxima = segmented.group_by(["cycle_index", "__segment"], maintain_order=True).agg(
            [pl.col(key).max().alias(label) for key, label in present.items()]
        )
        totals = maxima.group_by("cycle_index", maintain_order=True).agg(
            [pl.col(label).sum() for label in present.values()]
        )
        result = result.drop(list(present.values())).join(totals, on="cycle_index", how="left")
    return result


def _group_summary(df: pl.DataFrame, group_cols: list[str]) -> pl.DataFrame:
    return df.group_by(group_cols, maintain_order=True).agg(_summary_exprs(df))


def _summary_for_whole_table(df: pl.DataFrame, *, label: str) -> pl.DataFrame:
    summary = df.select(_summary_exprs(df))
    return summary.with_columns(pl.lit(label).alias("Group")).select(["Group", *summary.columns])


def _summary_exprs(df: pl.DataFrame) -> list[pl.Expr]:
    exprs: list[pl.Expr] = [
        pl.len().alias("Rows / 1"),
    ]
    if "test_time_s" in df.columns:
        exprs.extend(
            [
                pl.col("test_time_s").min().alias("Start test_time_s"),
                pl.col("test_time_s").max().alias("End test_time_s"),
                (pl.col("test_time_s").max() - pl.col("test_time_s").min()).alias("Duration / s"),
            ]
        )
    if "voltage_v" in df.columns:
        exprs.extend(
            [
                pl.col("voltage_v").min().alias("Min voltage_v"),
                pl.col("voltage_v").max().alias("Max voltage_v"),
            ]
        )
    if "current_a" in df.columns:
        exprs.extend(
            [
                pl.col("current_a").min().alias("Min current_a"),
                pl.col("current_a").max().alias("Max current_a"),
            ]
        )
    if "charge_capacity_ah" in df.columns:
        exprs.append(pl.col("charge_capacity_ah").max().alias("Charging Capacity End / Ah"))
    if "discharge_capacity_ah" in df.columns:
        exprs.append(pl.col("discharge_capacity_ah").max().alias("Discharging Capacity End / Ah"))
    if "charge_energy_wh" in df.columns:
        exprs.append(pl.col("charge_energy_wh").max().alias("Charging Energy End / Wh"))
    if "discharge_energy_wh" in df.columns:
        exprs.append(pl.col("discharge_energy_wh").max().alias("Discharging Energy End / Wh"))
    return exprs
