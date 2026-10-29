"""EIS normalization keeps every source column and does not depend on early-row types."""

from __future__ import annotations

import csv
import warnings
from pathlib import Path

import polars as pl
import pytest

import bds

CONTEXT = [
    "Spectrum_ID",
    "Cell_ID",
    "Temperature_degC",
    "SOC_fraction",
    "Rest_Time_s",
    "AC_Amplitude_A",
    "Instrument",
    "Protocol_ID",
    "Sequence_Index",
    "Elapsed_Time_s",
]


def _write_long_table(path: Path, spectra: int = 4, points: int = 40, sparse_until: int = 3) -> None:
    fields = ["Spectrum_ID", "Frequency_Hz", "Real_Ohm", "Imag_Ohm", *CONTEXT[1:]]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for spectrum in range(spectra):
            for k in range(points):
                writer.writerow(
                    {
                        "Spectrum_ID": f"S{spectrum}",
                        "Frequency_Hz": 5000 * 10 ** (-k / 6),
                        "Real_Ohm": 0.02 + 0.001 * k + 0.0001 * spectrum,
                        "Imag_Ohm": -0.001 * (k % 7),
                        "Cell_ID": "cell-A",
                        "Temperature_degC": 25.0,
                        "SOC_fraction": 0.5,
                        "Rest_Time_s": 3600.0,
                        "AC_Amplitude_A": 0.1,
                        "Instrument": "BioLogic MPG205",
                        "Protocol_ID": "GEIS-5kHz-10mHz",
                        "Sequence_Index": spectrum,
                        "Elapsed_Time_s": "" if spectrum < sparse_until else 50.0 + k,
                    }
                )


def test_read_eis_keeps_identifier_and_condition_columns(tmp_path: Path) -> None:
    source = tmp_path / "long.csv"
    _write_long_table(source, sparse_until=0)

    frame = bds.read_eis(source)

    assert frame.columns[:5] == [
        "Frequency_Hz",
        "Zre_exp_Ohm",
        "Zim_exp_Ohm",
        "-Zim_exp_Ohm",
        "Phase_exp_deg",
    ]
    assert frame.columns[5:] == CONTEXT
    assert frame["Sequence_Index"].dtype == pl.Int64
    assert frame["Instrument"].unique().to_list() == ["BioLogic MPG205"]
    assert sorted(frame["Spectrum_ID"].unique().to_list()) == ["S0", "S1", "S2", "S3"]
    assert frame.group_by("Spectrum_ID").len()["len"].to_list() == [40] * 4
    assert bds.validate_eis(frame).valid


def test_condition_column_empty_in_first_rows_is_read(tmp_path: Path) -> None:
    source = tmp_path / "sparse.csv"
    _write_long_table(source, sparse_until=3)

    frame = bds.read_eis(source)

    assert frame["Elapsed_Time_s"].dtype == pl.Float64
    assert frame["Elapsed_Time_s"].null_count() == 120
    filled = frame.filter(pl.col("Spectrum_ID") == "S3")
    assert sorted(filled["Elapsed_Time_s"].to_list()) == [50.0 + k for k in range(40)]


def test_rows_with_equal_frequency_keep_source_order(tmp_path: Path) -> None:
    source = tmp_path / "ties.csv"
    _write_long_table(source, sparse_until=0)

    first = bds.read_eis(source)
    second = bds.read_eis(source)

    assert first.equals(second)
    top = first.filter(pl.col("Frequency_Hz") == first["Frequency_Hz"].max())
    assert top["Spectrum_ID"].to_list() == ["S0", "S1", "S2", "S3"]


def test_reading_converted_output_does_not_duplicate_generated_columns(tmp_path: Path) -> None:
    source = tmp_path / "long.csv"
    _write_long_table(source, sparse_until=0)
    converted = tmp_path / "normalized.eis.csv"
    bds.convert_eis(source, converted)

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        reread = bds.read_eis(converted)

    assert reread.columns == bds.read_eis(source).columns
    assert not any(column.startswith("raw:") for column in reread.columns)


def test_conflicting_generated_column_is_kept_as_raw(tmp_path: Path) -> None:
    source = tmp_path / "phase.csv"
    source.write_text(
        "Frequency_Hz,Zre_exp_Ohm,Zim_exp_Ohm,Phase_exp_deg,Cell_ID\n"
        "1000,0.02,-0.001,99,A\n"
        "10,0.05,-0.02,99,A\n",
        encoding="utf-8",
    )

    with pytest.warns(UserWarning, match="Phase_exp_deg"):
        frame = bds.read_eis(source)

    assert frame["raw:Phase_exp_deg"].to_list() == [99, 99]
    assert frame["Phase_exp_deg"][0] == pytest.approx(-2.862405226)
    assert frame["Cell_ID"].to_list() == ["A", "A"]
