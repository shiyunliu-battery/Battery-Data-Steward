"""Regression coverage for value-changing normalization and validation paths."""

import math

import polars as pl
import pytest

import bds
from battery_data_standard.cli import main
from battery_data_standard.eis import normalize_eis_frame, validate_eis
from battery_data_standard.exceptions import ConversionError
from battery_data_standard.time_sampling import apply_time_sampling_policy


@pytest.mark.parametrize("convention, expected", [("charge-positive", -1.0), ("discharge-positive", 1.0)])
def test_derived_power_uses_normalized_current(tmp_path, convention, expected):
    source = tmp_path / "discharge.csv"
    source.write_text("Time,Voltage,Current,Status\n0,4,1,D\n1,4,1,D\n")
    frame, report = bds.read_with_report(source, cycler="generic", current_sign=convention)
    assert report.validation.valid
    assert frame["current_a"].to_list() == [expected, expected]
    assert frame["power_w"].to_list() == [4 * expected, 4 * expected]


def test_default_sampling_preserves_measured_rows_in_api_and_cli(tmp_path):
    source = tmp_path / "gap.csv"
    source.write_text("Time,Voltage,Current\n0,4,1\n1,4,1\n2,4,1\n4,4,1\n")
    frame, report = bds.read_with_report(source, cycler="generic")
    assert frame["test_time_s"].to_list() == [0, 1, 2, 4]
    assert report.metadata["time_sampling"]["status"] == "gaps-detected"
    output = tmp_path / "out.csv"
    bds.convert(source, output, cycler="generic")
    assert pl.read_csv(output).height == 4
    assert main(["convert", str(source), str(output)]) == 0
    assert pl.read_csv(output).height == 4
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    batch_source = input_dir / "gap.csv"
    batch_source.write_bytes(source.read_bytes())
    output_dir = tmp_path / "batch-out"
    assert main(["batch", str(input_dir), str(output_dir)]) == 0
    assert pl.read_csv(next(output_dir.glob("*.csv"))).height == 4


@pytest.mark.parametrize("boundary", ["step_index", "cycle_index"])
def test_explicit_sampling_repair_skips_segment_boundaries(boundary):
    frame = pl.DataFrame(
        {
            "test_time_s": [0.0, 1.0, 2.0, 5.0, 6.0, 7.0],
            "voltage_v": [4.0] * 6,
            "current_a": [1.0, 1.0, 1.0, -1.0, -1.0, -1.0],
            boundary: [1, 1, 1, 2, 2, 2],
        }
    )
    result = apply_time_sampling_policy(frame, policy="repair")
    assert result.data.equals(frame)
    assert result.metadata["missing_points"] == 2
    assert result.metadata["boundary_skipped_points"] == 2
    assert result.metadata["status"] == "boundary-gaps-not-repaired"
    assert result.repair_operations == []


def test_sampling_can_repair_within_step_while_skipping_boundary():
    frame = pl.DataFrame(
        {
            "test_time_s": [0.0, 2.0, 5.0],
            "current_a": [1.0, 1.0, -1.0],
            "step_index": [1, 1, 2],
        }
    )
    result = apply_time_sampling_policy(frame, policy="repair", expected_interval_s=1)
    assert result.data["test_time_s"].to_list() == [0, 1, 2, 5]
    assert result.metadata["inserted_rows"] == 1
    assert result.metadata["boundary_skipped_points"] == 2
    assert result.metadata["status"] == "partially-repaired"


def test_sampling_does_not_interpolate_across_step_timer_reset():
    frame = pl.DataFrame({"test_time_s": [0.0, 1.0, 4.0], "step_time_s": [0.0, 1.0, 0.0]})
    result = apply_time_sampling_policy(frame, policy="repair", expected_interval_s=1)
    assert result.data.equals(frame)


@pytest.mark.parametrize(
    "header, value", [("Phase(deg)", -5.0), ("Phase(rad)", math.radians(-5)), ("Zphz", -5.0)]
)
def test_eis_phase_units_are_independent_of_value_magnitude(header, value):
    frame = normalize_eis_frame(pl.DataFrame({"Frequency_Hz": [1000.0], "Zmod": [1.0], header: [value]}))
    assert frame["Phase_exp_deg"][0] == pytest.approx(-5)
    assert frame["Zre_exp_Ohm"][0] == pytest.approx(math.cos(math.radians(-5)))
    assert frame["Zim_exp_Ohm"][0] == pytest.approx(math.sin(math.radians(-5)))


@pytest.mark.parametrize("polar", [False, True])
def test_eis_rejects_invalid_source_rows_without_writing_partial_output(tmp_path, polar):
    source = tmp_path / "invalid.csv"
    headers = "Zmod,Phase(deg)" if polar else "Zreal,Zimag"
    source.write_text(f"Frequency_Hz,{headers}\n1000,0.1,-5\n100,,0\n10,0.3,-5\n")
    output = tmp_path / "output.csv"
    with pytest.raises(ConversionError, match="parsed table row 2"):
        bds.convert_eis(source, output)
    assert not output.exists()


def test_empty_eis_and_unknown_schema_fail_validation():
    frame = pl.DataFrame(
        schema={"Frequency_Hz": pl.Float64, "Zre_exp_Ohm": pl.Float64, "Zim_exp_Ohm": pl.Float64}
    )
    assert not bds.validate_eis(frame).valid
    nonempty = pl.DataFrame({"Frequency_Hz": [1000.0], "Zre_exp_Ohm": [0.1], "Zim_exp_Ohm": [-0.01]})
    assert not validate_eis(nonempty, schema_version="unknown").valid
