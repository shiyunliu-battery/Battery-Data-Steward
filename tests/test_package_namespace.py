"""Public namespace and exception behavior after the Steward migration."""

import subprocess
import sys

import pytest

import battery_data_steward as steward
import bds
from battery_data_steward.exceptions import BatteryDataStewardError, ConversionError
from battery_data_steward.export import EXPORT_FORMAT_VERSION, normalize_export_target


def test_short_alias_preserves_public_object_identity():
    for name in steward.__all__:
        assert getattr(bds, name) is getattr(steward, name)
    with pytest.raises(steward.BatteryDataStewardError):
        raise ConversionError("conversion failed")
    assert steward.BatteryDataStewardError is BatteryDataStewardError


@pytest.mark.parametrize("module", ["battery_data_steward", "battery_data_steward.cli"])
def test_steward_module_commands(module):
    result = subprocess.run(
        [sys.executable, "-m", module, "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == f"bds {steward.__version__}"


@pytest.mark.parametrize("target", ["bds", "battery-data-steward", "battery_data_steward"])
def test_steward_export_target_names(target):
    assert normalize_export_target(target) == "bds"
    assert EXPORT_FORMAT_VERSION == "battery-data-steward-export-v1"
