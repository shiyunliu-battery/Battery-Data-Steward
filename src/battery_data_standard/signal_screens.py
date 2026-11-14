"""Non-mutating screens for clock and temperature-channel integrity.

Two screens run on a normalized time-series frame, in source row order, and report events with
row and record references. Neither screen changes, masks or interpolates a sample; whether an
event is an acquisition artefact, a suspended test or a real change is a review decision.

``clock_divergence``
    Compares the wall clock (``unix_time_s``) with the test clock (``test_time_s``) between
    consecutive records. When the wall clock advances more than the test clock, the test clock
    did not count that time (for example, a suspended or paused test); when the test clock
    advances more, the wall clock was corrected or shifted (for example, a daylight-saving
    change). The threshold is at least twice the wall clock's resolution, so a clock that
    records whole minutes does not produce events from rounding.

``temperature_excursions``
    Finds abrupt steps in each temperature channel — a run of consecutive same-sign changes,
    each faster than a rate threshold, together larger than a step threshold — and pairs a step
    with the later opposite step that returns the channel. The interval between them is an
    excursion; an excursion that never returns ends at the last record. Excursions in different
    channels that overlap or start within a coincidence window are merged into one episode, and
    the voltage and current changes at the onset are reported so a reviewer can see whether the
    electrical channels moved with the temperature.

The defaults are screening thresholds, not physical limits: a 5 °C change at 0.05 °C/s or faster
is several times faster than the surface temperature of a cell changes under load in the
datasets this was developed on, but a smaller cell, a fast thermocouple or a chamber with forced
convection can be faster. Pass other values when the instrument warrants it; the values used are
recorded in every result.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import polars as pl

CLOCK_DIVERGENCE_MIN_S = 120.0
TEMPERATURE_STEP_MIN_C = 5.0
TEMPERATURE_RATE_MIN_C_PER_S = 0.05
TEMPERATURE_COMPONENT_MIN_C = 0.5
TEMPERATURE_COINCIDENCE_WINDOW_S = 300.0
MAX_REPORTED_EVENTS = 50
DST_SHIFT_S = 3600.0


def clock_divergence(df: pl.DataFrame, *, min_divergence_s: float = CLOCK_DIVERGENCE_MIN_S) -> dict[str, Any]:
    """Intervals where the wall clock and the test clock advance by different amounts."""
    if min_divergence_s <= 0 or not math.isfinite(min_divergence_s):
        raise ValueError("min_divergence_s must be a positive finite number")
    result: dict[str, Any] = {
        "method": "consecutive_record_wall_minus_test_time_v1",
        "min_divergence_s": float(min_divergence_s),
        "events": [],
        "events_total": 0,
        "events_truncated": False,
    }
    missing = [column for column in ("unix_time_s", "test_time_s") if column not in df.columns]
    if missing:
        result.update(status="not-checked", reason=f"missing column(s): {', '.join(missing)}")
        return result
    wall = _numbers(df["unix_time_s"])
    test = _numbers(df["test_time_s"])
    rows = np.flatnonzero(np.isfinite(wall) & np.isfinite(test))
    if rows.size < 2:
        result.update(status="not-checked", reason="fewer than two records with both clocks")
        return result

    wall_step = np.diff(wall[rows])
    test_step = np.diff(test[rows])
    positive = wall_step[wall_step > 0]
    resolution = float(positive.min()) if positive.size else None
    threshold = (
        max(float(min_divergence_s), 2.0 * resolution) if resolution is not None else float(min_divergence_s)
    )
    divergence = wall_step - test_step
    # A test-time reset or reversal is reported by the time-axis checks; it is not uncounted time.
    candidates = np.flatnonzero((np.abs(divergence) > threshold) & (test_step >= 0))
    result.update(wall_clock_resolution_s=resolution, threshold_s=threshold)

    events = []
    for k in candidates:
        before, after = int(rows[k]), int(rows[k + 1])
        value = float(divergence[k])
        event: dict[str, Any] = {
            "direction": "wall-ahead" if value > 0 else "test-ahead",
            "row_before": before,
            "row_after": after,
            "divergence_s": value,
            "test_time_before_s": float(test[before]),
            "test_time_after_s": float(test[after]),
            "unix_time_before_s": float(wall[before]),
            "unix_time_after_s": float(wall[after]),
            "possible_dst_shift": bool(abs(abs(value) - DST_SHIFT_S) <= max(resolution or 0.0, 1.0)),
        }
        event.update(_row_context(df, before, after))
        events.append(event)
    uncounted = sum(e["divergence_s"] for e in events if e["direction"] == "wall-ahead")
    result.update(
        status="divergence-detected" if events else "no-divergence",
        events=events[:MAX_REPORTED_EVENTS],
        events_total=len(events),
        events_truncated=len(events) > MAX_REPORTED_EVENTS,
        uncounted_wall_time_s=float(uncounted),
        test_ahead_events=sum(1 for e in events if e["direction"] == "test-ahead"),
    )
    return result


def temperature_excursions(
    df: pl.DataFrame,
    *,
    min_step_c: float = TEMPERATURE_STEP_MIN_C,
    min_rate_c_per_s: float = TEMPERATURE_RATE_MIN_C_PER_S,
    min_component_c: float = TEMPERATURE_COMPONENT_MIN_C,
    coincidence_window_s: float = TEMPERATURE_COINCIDENCE_WINDOW_S,
) -> dict[str, Any]:
    """Abrupt temperature excursions per channel, merged into episodes across channels."""
    for name, value in (
        ("min_step_c", min_step_c),
        ("min_rate_c_per_s", min_rate_c_per_s),
        ("min_component_c", min_component_c),
        ("coincidence_window_s", coincidence_window_s),
    ):
        if value < 0 or not math.isfinite(value):
            raise ValueError(f"{name} must be a non-negative finite number")
    result: dict[str, Any] = {
        "method": "abrupt_step_pairing_v1",
        "parameters": {
            "min_step_c": float(min_step_c),
            "min_rate_c_per_s": float(min_rate_c_per_s),
            "min_component_c": float(min_component_c),
            "coincidence_window_s": float(coincidence_window_s),
            "time_base": "test_time_s step; unix_time_s step where it exceeds it by more than the clock-divergence threshold",
        },
        "channels_checked": [],
        "episodes": [],
        "episodes_total": 0,
        "episodes_truncated": False,
    }
    channels = [c for c in df.columns if c.endswith("_deg_c") and "temperature" in c]
    if not channels:
        result.update(status="not-checked", reason="no temperature column")
        return result
    if "test_time_s" not in df.columns:
        result.update(status="not-checked", reason="missing column: test_time_s")
        return result
    test = _numbers(df["test_time_s"])
    wall = _numbers(df["unix_time_s"]) if "unix_time_s" in df.columns else None
    result["channels_checked"] = channels

    excursions: list[dict[str, Any]] = []
    for column in channels:
        excursions.extend(
            _channel_excursions(
                column,
                _numbers(df[column]),
                test,
                wall,
                min_step_c=min_step_c,
                min_rate_c_per_s=min_rate_c_per_s,
                min_component_c=min_component_c,
            )
        )
    episodes = _merge_episodes(df, excursions, test, wall, coincidence_window_s=coincidence_window_s)
    result.update(
        status="excursions-detected" if episodes else "no-excursion",
        episodes=episodes[:MAX_REPORTED_EVENTS],
        episodes_total=len(episodes),
        episodes_truncated=len(episodes) > MAX_REPORTED_EVENTS,
        rows_in_episodes=int(sum(e["rows"] for e in episodes)),
        coincident_episodes=sum(1 for e in episodes if e["coincident_channels"]),
    )
    return result


def screen_issues(checks: dict[str, Any]) -> list[tuple[str, str, str, str | None]]:
    """(level, code, message, column) for the events found by the screens."""
    issues: list[tuple[str, str, str, str | None]] = []
    clocks = checks.get("clock_divergence") or {}
    events = list(clocks.get("events") or [])
    total = int(clocks.get("events_total") or 0)
    wall_ahead = [e for e in events if e["direction"] == "wall-ahead"]
    if total and (clocks.get("uncounted_wall_time_s") or 0) > 0:
        largest = max(e["divergence_s"] for e in wall_ahead) if wall_ahead else 0.0
        issues.append(
            (
                "warning",
                "uncounted-wall-time",
                f"The wall clock advanced more than test_time_s at {total - int(clocks.get('test_ahead_events') or 0)} "
                f"record transition(s) ({clocks['uncounted_wall_time_s']:.0f} s in total, largest {largest:.0f} s); "
                "the test clock did not count that time, for example during a suspended test. "
                f"Threshold {clocks['threshold_s']:g} s; wall clock resolution {clocks.get('wall_clock_resolution_s')} s. "
                "No samples were changed.",
                "test_time_s",
            )
        )
    if clocks.get("test_ahead_events"):
        dst = sum(1 for e in events if e["direction"] == "test-ahead" and e["possible_dst_shift"])
        issues.append(
            (
                "warning",
                "test-time-exceeds-wall-time",
                f"test_time_s advanced more than the wall clock at {clocks['test_ahead_events']} record transition(s)"
                + (f", {dst} of them by about one hour (possible daylight-saving shift)" if dst else "")
                + "; the wall clock may have been corrected or shifted. No samples were changed.",
                "unix_time_s",
            )
        )
    temperature = checks.get("temperature_excursions") or {}
    if temperature.get("episodes_total"):
        parameters = temperature["parameters"]
        issues.append(
            (
                "warning",
                "abrupt-temperature-excursion",
                f"{temperature['episodes_total']} abrupt temperature excursion(s) "
                f"({temperature['rows_in_episodes']} rows; {temperature['coincident_episodes']} coincident across "
                f"temperature channels): steps of at least {parameters['min_step_c']:g} °C at "
                f"{parameters['min_rate_c_per_s']:g} °C/s or faster. Review before using temperature statistics; "
                "no samples were changed or masked.",
                ",".join(temperature.get("channels_checked") or []) or None,
            )
        )
    return issues


# ------------------------------------------------------------------------------------------ helpers
def _numbers(series: pl.Series) -> np.ndarray:
    """Float values with nulls and non-numeric entries as NaN (no row is dropped or reordered)."""
    return series.cast(pl.Float64, strict=False).fill_null(float("nan")).to_numpy().astype(float)


def _value(df: pl.DataFrame, column: str, row: int) -> Any:
    if column not in df.columns:
        return None
    value = df[column][row]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _row_context(df: pl.DataFrame, before: int, after: int) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for column in ("record_index", "cycle_index", "step_index"):
        if column in df.columns:
            context[f"{column}_before"] = _value(df, column, before)
            context[f"{column}_after"] = _value(df, column, after)
    for column in ("voltage_v", "current_a"):
        if column in df.columns:
            context[f"{column}_before"] = _value(df, column, before)
            context[f"{column}_after"] = _value(df, column, after)
    return context


def _channel_excursions(
    column: str,
    values: np.ndarray,
    test: np.ndarray,
    wall: np.ndarray | None,
    *,
    min_step_c: float,
    min_rate_c_per_s: float,
    min_component_c: float,
) -> list[dict[str, Any]]:
    rows = np.flatnonzero(np.isfinite(values) & np.isfinite(test))
    if rows.size < 2:
        return []
    change = np.diff(values[rows])
    elapsed = np.diff(test[rows])
    if wall is not None:
        # Wall time replaces test time only where it shows time the test clock did not count; a
        # coarse wall clock (whole minutes) would otherwise distort the elapsed time of every sample.
        wall_step = np.diff(wall[rows])
        positive = np.diff(wall[np.isfinite(wall)])
        positive = positive[positive > 0]
        threshold = (
            max(CLOCK_DIVERGENCE_MIN_S, 2.0 * float(positive.min()))
            if positive.size
            else CLOCK_DIVERGENCE_MIN_S
        )
        uncounted = np.isfinite(wall_step) & (wall_step - elapsed > threshold)
        elapsed = np.where(uncounted, wall_step, elapsed)
    with np.errstate(divide="ignore", invalid="ignore"):
        rate = np.where(elapsed > 0, np.abs(change) / elapsed, np.inf)
    fast = (np.abs(change) >= min_component_c) & (rate >= min_rate_c_per_s)

    # runs of consecutive fast changes with the same sign
    steps: list[dict[str, Any]] = []
    k = 0
    while k < change.size:
        if not fast[k]:
            k += 1
            continue
        sign = np.sign(change[k])
        end = k
        while end + 1 < change.size and fast[end + 1] and np.sign(change[end + 1]) == sign:
            end += 1
        magnitude = float(values[rows[end + 1]] - values[rows[k]])
        if abs(magnitude) >= min_step_c:
            steps.append({"first": k, "last": end, "magnitude": magnitude})
        k = end + 1

    excursions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for step in steps:
        sign = 1 if step["magnitude"] > 0 else -1
        if current is None:
            current = {
                "sign": sign,
                "depth": abs(step["magnitude"]),
                "onset": step,
                "level_before": float(values[rows[step["first"]]]),
            }
            continue
        if sign == current["sign"]:
            current["depth"] += abs(step["magnitude"])
            continue
        if abs(step["magnitude"]) >= 0.5 * current["depth"]:
            excursions.append(_excursion(column, current, step, values, rows))
            current = None
    if current is not None:
        excursions.append(_excursion(column, current, None, values, rows))
    return excursions


def _excursion(
    column: str,
    current: dict[str, Any],
    recovery: dict[str, Any] | None,
    values: np.ndarray,
    rows: np.ndarray,
) -> dict[str, Any]:
    onset = current["onset"]
    # A multi-sample onset or recovery is inside the excursion: the excursion starts at the first
    # sample after the onset's first change and ends at the last sample before the recovery completes.
    start = int(rows[onset["first"] + 1])
    end = int(rows[recovery["last"]]) if recovery is not None else int(rows[-1])
    inside = values[start : end + 1]
    inside = inside[np.isfinite(inside)]
    extreme = float(inside.min() if current["sign"] < 0 else inside.max()) if inside.size else None
    return {
        "channel": column,
        "start_row": start,
        "end_row": end,
        "direction": "drop" if current["sign"] < 0 else "rise",
        "onset_step_c": float(onset["magnitude"]),
        "onset_samples": int(onset["last"] - onset["first"] + 1),
        "level_before_c": current["level_before"],
        "extreme_c": extreme,
        "recovered": recovery is not None,
        "recovery_step_c": float(recovery["magnitude"]) if recovery is not None else None,
        "recovery_samples": int(recovery["last"] - recovery["first"] + 1) if recovery is not None else None,
        "onset_row": int(rows[onset["first"]]),
    }


def _merge_episodes(
    df: pl.DataFrame,
    excursions: list[dict[str, Any]],
    test: np.ndarray,
    wall: np.ndarray | None,
    *,
    coincidence_window_s: float,
) -> list[dict[str, Any]]:
    def time_at(row: int) -> float:
        if wall is not None and math.isfinite(wall[row]):
            return float(wall[row])
        return float(test[row])

    groups: list[list[dict[str, Any]]] = []
    for item in sorted(excursions, key=lambda e: (e["start_row"], e["channel"])):
        if groups:
            last = groups[-1]
            last_end = max(e["end_row"] for e in last)
            last_onset = min(time_at(e["start_row"]) for e in last)
            if (
                item["start_row"] <= last_end
                or abs(time_at(item["start_row"]) - last_onset) <= coincidence_window_s
            ):
                last.append(item)
                continue
        groups.append([item])

    episodes = []
    for group in groups:
        start = min(e["start_row"] for e in group)
        end = max(e["end_row"] for e in group)
        first = min(group, key=lambda e: (e["start_row"], e["channel"]))
        onsets = [time_at(e["start_row"]) for e in group]
        episode: dict[str, Any] = {
            "start_row": start,
            "end_row": end,
            "rows": end - start + 1,
            "direction": group[0]["direction"] if len({e["direction"] for e in group}) == 1 else "mixed",
            "channels": [{k: v for k, v in e.items() if k != "onset_row"} for e in group],
            "coincident_channels": len({e["channel"] for e in group}) > 1
            and (max(onsets) - min(onsets)) <= coincidence_window_s,
            "open_ended": any(not e["recovered"] for e in group),
            "test_time_start_s": float(test[start]),
            "test_time_end_s": float(test[end]),
        }
        if wall is not None:
            episode["unix_time_start_s"] = float(wall[start]) if math.isfinite(wall[start]) else None
            episode["unix_time_end_s"] = float(wall[end]) if math.isfinite(wall[end]) else None
        if "record_index" in df.columns:
            episode["start_record"] = _value(df, "record_index", start)
            episode["end_record"] = _value(df, "record_index", end)
        for column in ("step_index", "cycle_index"):
            if column in df.columns:
                values = df[column][start : end + 1].drop_nulls().unique(maintain_order=True).to_list()
                episode[column.replace("_index", "s")] = sorted(values)
        # the electrical channels across the earliest onset: last sample before the step, first after it
        before, after = first["onset_row"], first["start_row"]
        episode["onset_rows"] = [before, after]
        for column, unit in (("voltage_v", "v"), ("current_a", "a")):
            if column in df.columns and after < df.height:
                left, right = _value(df, column, before), _value(df, column, after)
                episode[f"onset_{column.split('_')[0]}_change_{unit}"] = (
                    float(right) - float(left) if left is not None and right is not None else None
                )
        if "step_index" in df.columns and after < df.height:
            episode["onset_step_change"] = _value(df, "step_index", before) != _value(df, "step_index", after)
        episodes.append(episode)
    return episodes
