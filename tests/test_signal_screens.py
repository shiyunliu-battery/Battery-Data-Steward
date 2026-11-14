"""Clock-divergence and temperature-excursion screens (signal_screens.py).

The screens report events and never change a sample. These tests cover what each screen must find,
what it must not find (rounding of a minute-resolution wall clock, slow thermal ramps, fast-sampled
noise, a temperature change across a suspended interval), and how the events reach conversion
reports, inspection findings and audits with stable codes.
"""

from __future__ import annotations

import json

import numpy as np
import polars as pl
import pytest

import bds
from battery_data_standard.quality import quality_checks
from battery_data_standard.signal_screens import clock_divergence, screen_issues, temperature_excursions

T0 = 1_549_465_080.0  # 2019-02-06 15:58 UTC


def _frame(n=400, dt=30.0, *, minute_clock=True, pause_after=None, pause_s=2700.0, t1=None, ambient=None):
    test = np.arange(n) * dt
    wall = T0 + test.copy()
    if pause_after is not None:
        wall[pause_after + 1 :] += pause_s
    if minute_clock:
        wall = np.floor(wall / 60.0) * 60.0
    data = {
        "test_time_s": test,
        "unix_time_s": wall,
        "voltage_v": np.full(n, 3.6),
        "current_a": np.zeros(n),
        "record_index": np.arange(1, n + 1),
        "step_index": np.where(np.arange(n) < n // 2, 3, 4),
    }
    if t1 is not None:
        data["temperature_t1_deg_c"] = t1
    if ambient is not None:
        data["ambient_temperature_deg_c"] = ambient
    return pl.DataFrame(data)


# ------------------------------------------------------------------------------------------ clocks
def test_suspension_is_found_once_and_minute_rounding_is_not():
    result = clock_divergence(_frame(pause_after=199))
    assert result["status"] == "divergence-detected"
    assert result["wall_clock_resolution_s"] == 60.0 and result["threshold_s"] == 120.0
    assert result["events_total"] == 1
    event = result["events"][0]
    assert event["direction"] == "wall-ahead" and event["row_before"] == 199 and event["row_after"] == 200
    assert event["record_index_before"] == 200 and event["record_index_after"] == 201
    assert event["divergence_s"] == pytest.approx(2700.0, abs=60.0)
    assert result["uncounted_wall_time_s"] == pytest.approx(2700.0, abs=60.0)
    assert not event["possible_dst_shift"]


def test_no_suspension_means_no_event():
    result = clock_divergence(_frame())
    assert result["status"] == "no-divergence" and result["events"] == []


def test_clock_shift_back_is_reported_as_test_ahead_with_dst_hint():
    frame = _frame(minute_clock=False)
    wall = frame["unix_time_s"].to_numpy().copy()
    wall[250:] -= 3600.0
    result = clock_divergence(frame.with_columns(pl.Series("unix_time_s", wall)))
    assert result["events_total"] == 1 and result["test_ahead_events"] == 1
    assert result["events"][0]["direction"] == "test-ahead" and result["events"][0]["possible_dst_shift"]
    assert result["uncounted_wall_time_s"] == 0.0


def test_test_time_reset_is_left_to_the_time_axis_checks():
    frame = _frame(minute_clock=False)
    test = frame["test_time_s"].to_numpy().copy()
    test[300:] -= test[300]
    result = clock_divergence(frame.with_columns(pl.Series("test_time_s", test)))
    assert result["events_total"] == 0


def test_without_a_wall_clock_nothing_is_checked():
    result = clock_divergence(_frame().drop("unix_time_s"))
    assert result["status"] == "not-checked" and "unix_time_s" in result["reason"]


# ------------------------------------------------------------------------------------------ temperature
def _artefact(n=400):
    t1 = np.full(n, 26.0) + np.linspace(0.0, 1.0, n)
    ambient = np.full(n, 26.5)
    t1[100:150] -= 13.0  # cell channel drops at row 100, recovers at row 150
    ambient[101:149] -= 13.5  # chamber channel one sample later, recovers one earlier
    return t1, ambient


def test_coincident_drop_and_recovery_form_one_episode():
    t1, ambient = _artefact()
    result = temperature_excursions(_frame(t1=t1, ambient=ambient))
    assert result["status"] == "excursions-detected" and result["episodes_total"] == 1
    episode = result["episodes"][0]
    assert (episode["start_row"], episode["end_row"]) == (100, 149)
    assert (episode["start_record"], episode["end_record"]) == (101, 150)
    assert episode["rows"] == 50 and episode["direction"] == "drop"
    assert episode["coincident_channels"] and not episode["open_ended"]
    assert {c["channel"] for c in episode["channels"]} == {
        "temperature_t1_deg_c",
        "ambient_temperature_deg_c",
    }
    assert episode["onset_voltage_change_v"] == 0.0 and episode["onset_current_change_a"] == 0.0
    assert episode["steps"] == [3]
    assert all(c["recovered"] for c in episode["channels"])


def test_excursion_without_recovery_runs_to_the_last_record():
    n = 400
    t1 = np.full(n, 26.0)
    t1[380:] -= 13.0
    result = temperature_excursions(_frame(t1=t1))
    episode = result["episodes"][0]
    assert episode["open_ended"] and (episode["start_row"], episode["end_row"]) == (380, n - 1)


def test_multi_sample_onset_and_recovery_samples_are_inside():
    n = 400
    t1 = np.full(n, 26.0)
    t1[100] = 24.2  # first part of the onset (1.8 °C in 30 s)
    t1[101:150] = 13.0
    t1[150] = 22.0  # first part of the recovery
    result = temperature_excursions(_frame(t1=t1))
    episode = result["episodes"][0]
    assert (episode["start_row"], episode["end_row"]) == (100, 150)
    channel = episode["channels"][0]
    assert channel["onset_samples"] == 2 and channel["recovery_samples"] == 2


def test_slow_ramps_and_fast_noise_are_not_excursions():
    n = 400
    ramp = 25.0 + np.linspace(0.0, 30.0, n)  # 30 °C over ~3.3 h, like a high-rate discharge
    assert temperature_excursions(_frame(t1=ramp))["episodes_total"] == 0
    rng = np.random.default_rng(0)
    noise = 25.0 + rng.normal(0.0, 0.05, n)
    fast = _frame(n=n, dt=0.1, minute_clock=False, t1=noise)
    assert temperature_excursions(fast)["episodes_total"] == 0


def test_a_change_across_a_suspended_interval_uses_the_wall_clock():
    n = 400
    t1 = np.full(n, 25.0)
    t1[200:] = 35.0  # +10 °C between rows 199 and 200 ...
    frame = _frame(t1=t1, pause_after=199, pause_s=7200.0)
    assert temperature_excursions(frame)["episodes_total"] == 0  # ... over 2 h of wall time
    assert temperature_excursions(frame.drop("unix_time_s"))["episodes_total"] == 1


def test_without_temperature_nothing_is_checked():
    result = temperature_excursions(_frame())
    assert result["status"] == "not-checked"


def test_parameters_are_recorded_and_validated():
    t1, ambient = _artefact()
    result = temperature_excursions(_frame(t1=t1, ambient=ambient), min_step_c=20.0)
    assert result["episodes_total"] == 0 and result["parameters"]["min_step_c"] == 20.0
    with pytest.raises(ValueError):
        temperature_excursions(_frame(t1=t1), min_rate_c_per_s=-1)
    with pytest.raises(ValueError):
        clock_divergence(_frame(), min_divergence_s=0)


# ------------------------------------------------------------------------------------------ reporting
def test_quality_checks_carry_both_screens_and_issue_codes():
    t1, ambient = _artefact()
    checks = quality_checks(_frame(pause_after=299, t1=t1, ambient=ambient))
    assert checks["clock_divergence"]["events_total"] == 1
    assert checks["temperature_excursions"]["episodes_total"] == 1
    codes = [code for _, code, _, _ in screen_issues(checks)]
    assert codes == ["uncounted-wall-time", "abrupt-temperature-excursion"]
    assert all(level == "warning" for level, *_ in screen_issues(checks))


def _csv(tmp_path):
    n = 400
    frame = _frame(n=n, pause_after=299, t1=_artefact(n)[0], ambient=_artefact(n)[1])
    raw = tmp_path / "raw.csv"
    frame.rename(
        {
            "test_time_s": "t_s",
            "unix_time_s": "wall_s",
            "voltage_v": "E",
            "current_a": "I",
            "temperature_t1_deg_c": "T_cell",
            "ambient_temperature_deg_c": "T_chamber",
            "record_index": "rec",
            "step_index": "step",
        }
    ).write_csv(raw)
    profile = {
        "columns": {
            "test_time_s": "t_s",
            "unix_time_s": "wall_s",
            "voltage_v": "E",
            "current_a": "I",
            "temperature_t1_deg_c": "T_cell",
            "ambient_temperature_deg_c": "T_chamber",
            "record_index": "rec",
            "step_index": "step",
        }
    }
    return raw, profile


def test_events_reach_the_conversion_report_and_inspection(tmp_path):
    raw, profile = _csv(tmp_path)
    df, report = bds.read_with_report(raw, cycler="generic", profile=profile, strict=False)
    assert report.validation.valid, "the screens add warnings, never errors"
    codes = {issue.code for issue in report.validation.issues}
    assert {"uncounted-wall-time", "abrupt-temperature-excursion"} <= codes
    assert report.metadata["clock_divergence"]["events_total"] == 1
    assert report.metadata["temperature_excursions"]["episodes"][0]["start_record"] == 101
    assert df.height == 400, "no row was added, removed or masked"
    payload = json.loads(report.to_json())
    assert payload["metadata"]["temperature_excursions"]["episodes_total"] == 1

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    inspected = bds.inspect(raw, cycler="generic", profile=profile_path)
    findings = {f["code"]: f for f in inspected.findings}
    assert findings["uncounted-wall-time"]["severity"] == "review"
    assert findings["abrupt-temperature-excursion"]["severity"] == "review"
    assert inspected.clock_divergence["events_total"] == 1
    assert inspected.temperature_excursions["episodes_total"] == 1
    assert not inspected.source_file_modified and not inspected.repairs_applied


def test_events_reach_the_audit(tmp_path):
    raw, profile = _csv(tmp_path)
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    record = bds.audit(raw, cycler="generic", profile=profile_path).records[0]
    codes = {issue.code for issue in record.issues}
    assert {"uncounted-wall-time", "abrupt-temperature-excursion"} <= codes
