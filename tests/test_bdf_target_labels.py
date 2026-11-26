"""The bdf export target must use Battery Data Format labels with their BDF meanings.

BDF defines 'Step ID' as the program step identifier, which may recur in successive
cycles, and 'Step Count / 1' as a counter that never repeats. A cycler's step column
(Arbin Step_Index, NEWARE/Maccor Step ID, BioLogic Ns) is a step identifier.
"""

from __future__ import annotations

import polars as pl

import bds
from battery_data_steward.diagnostics import _export_column
from battery_data_steward.export import _BDF_EXPORT_RENAMES, from_bdf_export_frame, to_export_frame


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "record_index": [1, 2, 3, 4],
            "test_time_s": [0.0, 1.0, 2.0, 3.0],
            "voltage_v": [3.6, 3.7, 3.6, 3.7],
            "current_a": [-1.0, 1.0, -1.0, 1.0],
            "cycle_index": [1, 1, 2, 2],
            "step_index": [1, 2, 1, 2],
            "temperature_t1_deg_c": [25.0, 25.1, 25.2, 25.3],
        }
    )


def test_repeating_protocol_step_is_written_as_step_id():
    exported = to_export_frame(_frame(), target="bdf")

    assert exported["Step ID"].to_list() == [1, 2, 1, 2]
    assert "Step Count / 1" not in exported.columns


def test_record_index_and_t1_use_bdf_labels():
    exported = to_export_frame(_frame(), target="bdf")

    assert exported["Record Index / 1"].to_list() == [1, 2, 3, 4]
    assert exported["Temperature T1 / degC"].to_list() == [25.0, 25.1, 25.2, 25.3]
    assert "Step Index / 1" not in exported.columns
    assert "Surface Temperature T1 / degC" not in exported.columns


def test_bdf_export_reads_back_with_the_same_steps(tmp_path):
    raw = tmp_path / "raw.csv"
    raw.write_text(
        "Test Time (s),Voltage (V),Current (A),Cycle Index,Step Index,Data Point\n"
        "0,3.6,-1,1,1,1\n1,3.7,1,1,2,2\n2,3.6,-1,2,1,3\n3,3.7,1,2,2,4\n",
        encoding="utf-8",
    )
    exported = tmp_path / "out.bdf.csv"
    bds.convert(raw, exported, cycler="generic", target="bdf")

    assert pl.read_csv(exported)["Step ID"].to_list() == [1, 2, 1, 2]
    back = bds.read(exported, cycler="generic")
    assert back["step_index"].to_list() == [1, 2, 1, 2]
    assert back["record_index"].to_list() == [1, 2, 3, 4]
    report = bds.validate_file(exported)
    assert report.valid, [issue.message for issue in report.issues if issue.level == "error"]


def test_validate_file_accepts_bdf_files_written_by_earlier_releases(tmp_path):
    legacy = tmp_path / "legacy.bdf.csv"
    legacy.write_text(
        "Test Time / s,Voltage / V,Current / A,Cycle Count / 1,Step Count / 1,Step Index / 1\n"
        "0,3.6,-1,1,1,1\n1,3.7,1,1,2,2\n",
        encoding="utf-8",
    )
    assert bds.validate_file(legacy).valid


def test_validate_file_still_rejects_an_invalid_bdf_file(tmp_path):
    broken = tmp_path / "broken.bdf.csv"
    broken.write_text("Test Time / s,Voltage / V,Current / A\n0,3.6,x\n1,3.7,1\n", encoding="utf-8")
    assert not bds.validate_file(broken).valid


def test_bdf_labels_map_back_to_canonical_columns():
    frame = _frame()
    restored = from_bdf_export_frame(to_export_frame(frame, target="bdf"))
    for column in frame.columns:
        assert restored[column].to_list() == frame[column].to_list()


def test_current_label_wins_when_a_file_has_both_step_labels():
    both = pl.DataFrame({"Step ID": [1, 2, 1], "Step Count / 1": [1, 2, 3]})
    restored = from_bdf_export_frame(both)
    assert restored["step_index"].to_list() == [1, 2, 1]
    assert restored["Step Count / 1"].to_list() == [1, 2, 3]


def test_inspect_preview_uses_the_export_labels():
    for column, label in _BDF_EXPORT_RENAMES.items():
        assert _export_column(column, target="bdf") == label
