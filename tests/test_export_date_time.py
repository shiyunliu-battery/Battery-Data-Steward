"""Exports keep the parsed instant when the source date text depends on a day/month order.

A Maccor file stamps rows ``06/02/2019 23:58`` (6 February). BDS parses it with the profile's
``date_order="dayfirst"``, but an export that copied the text would be read month-first (2 June)
by any reader without that profile, BDS itself included. These tests pin the round trip.
"""

from __future__ import annotations

import json

import polars as pl
import pytest

import bds
from battery_data_steward.adapters.normalization import _parse_unix_time
from battery_data_steward.export import iso_date_time_from_unix, to_export_frame


def _dayfirst_source(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "\n".join(
            [
                "t_s,E,I,stamp",
                "0,3.60,0.0,06/02/2019 23:58",
                "30,3.60,0.0,06/02/2019 23:59",
                "60,3.60,0.0,07/02/2019 00:00",
                "90,3.60,0.0,07/02/2019 00:00",
            ]
        ),
        encoding="utf-8",
    )
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "columns": {
                    "test_time_s": "t_s",
                    "voltage_v": "E",
                    "current_a": "I",
                    "date_time": "stamp",
                    "unix_time_s": "stamp",
                },
                "date_order": "dayfirst",
            }
        ),
        encoding="utf-8",
    )
    return raw, profile


@pytest.mark.parametrize("suffix", [".bds.csv", ".bds.parquet"])
def test_dayfirst_dates_survive_an_export_round_trip(tmp_path, suffix):
    raw, profile = _dayfirst_source(tmp_path)
    first = bds.read(raw, cycler="generic", profile=profile)
    output = tmp_path / f"out{suffix}"
    fmt = "csv" if suffix.endswith("csv") else "parquet"
    report = bds.convert(raw, output, cycler="generic", profile=profile, format=fmt)

    exported = pl.read_csv(output) if suffix.endswith("csv") else pl.read_parquet(output)
    assert exported["Date Time"].to_list() == [
        "2019-02-06T23:58:00",
        "2019-02-06T23:59:00",
        "2019-02-07T00:00:00",
        "2019-02-07T00:00:00",
    ]
    assert report.metadata["export_date_time"]["values_rewritten"] == 4

    again, again_report = bds.read_with_report(output, cycler="auto")
    assert again["unix_time_s"].to_list() == first["unix_time_s"].to_list()
    assert not any("month-first" in warning for warning in again_report.warnings)
    assert again_report.metadata["clock_divergence"]["events_total"] == 0


def test_year_first_text_and_rows_without_a_timestamp_are_left_as_they_are():
    texts = ["2019-02-06 23:58:00", "06/02/2019 23:59", "not a date", None]
    df = pl.DataFrame({"date_time": texts, "unix_time_s": _parse_unix_time(texts, date_order="dayfirst")})
    out, rewritten = iso_date_time_from_unix(df)
    assert rewritten == 1
    assert out["date_time"].to_list() == [
        "2019-02-06 23:58:00",
        "2019-02-06T23:59:00",
        "not a date",
        None,
    ]


def test_explicit_zones_are_written_in_utc_and_fractions_are_kept():
    texts = ["06/02/2019 23:58:30.250+01:00", "06/02/2019 23:58:31"]
    df = pl.DataFrame({"date_time": texts, "unix_time_s": _parse_unix_time(texts, date_order="dayfirst")})
    out, _ = iso_date_time_from_unix(df)
    assert out["date_time"].to_list() == ["2019-02-06T22:58:30.250Z", "2019-02-06T23:58:31"]


def test_every_target_that_writes_the_date_uses_the_same_text():
    texts = ["06/02/2019 23:58"]
    df = pl.DataFrame(
        {
            "date_time": texts,
            "unix_time_s": _parse_unix_time(texts, date_order="dayfirst"),
            "test_time_s": [0.0],
            "voltage_v": [3.6],
            "current_a": [0.0],
        }
    )
    assert to_export_frame(df, target="bds")["Date Time"].to_list() == ["2019-02-06T23:58:00"]
    bdf = to_export_frame(df, target="bdf")
    assert bdf["Date Time ISO"].to_list() == ["2019-02-06T23:58:00"]
    assert bdf["Unix Time / s"].to_list() == df["unix_time_s"].to_list()
    assert to_export_frame(df, target="cellpy")["datetime"].to_list() == ["2019-02-06T23:58:00"]
