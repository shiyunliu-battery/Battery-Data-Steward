# Export Template

CSV and Parquet exports use a consistent user-facing BDS column template across
cycler adapters. Exported files use labels with units in parentheses.

## Required Export Columns

The exported time-series table requires:

| Column | Meaning |
| --- | --- |
| `Record Index` | Sequential source record index. If no source record index is available, it is generated from row order. |
| `Test Time (s)` | Elapsed test time in seconds. |
| `Voltage (V)` | Instantaneous voltage in volts. |
| `Current (A)` | Instantaneous current in amperes. |

## Preferred Column Order

When present, columns are written in this order:

1. `Record Index`
2. `Date Time`
3. `Test Time (s)`
4. `Voltage (V)`
5. `Current (A)`
6. `Cycle Count`
7. `Step Index`
8. `Step Time (s)`
9. `Power (W)`
10. `Charging Capacity (Ah)`
11. `Discharging Capacity (Ah)`
12. `Charging Energy (Wh)`
13. `Discharging Energy (Wh)`
14. `Step Type`

Additional adapter-specific or auxiliary columns are appended after the
preferred columns. Vendor prefixes are removed where possible, and slash-style
units are rewritten as parenthesized units.

Lower-level adapter-only fields are retained in conversion reports when useful,
but the default BDS file template above is the public handoff format.

## Export Targets

The default `bds` target writes the standard export table above. Downstream
target presets can be selected from the CLI or Python API:

```bash
bds convert raw.mpt normalized.csv --target bds
bds convert raw.mpt pybamm_drive_cycle.csv --target pybamm
bds convert raw.mpt pyprobe_staging.parquet --target pyprobe --format parquet
```

```python
import bds

bds.convert("raw.mpt", "cellpy_staging.csv", target="cellpy")
bds.convert("raw.mpt", "duckdb_ready.parquet", target="duckdb", format="parquet")
```

Supported targets are:

| Target | Recommended format | Columns |
| --- | --- | --- |
| `bds` | CSV | Standard export columns. |
| `bdf` | CSV | Legacy BDF-style export with slash-unit column names; not a formal BDF conformance certificate. |
| `duckdb` | Parquet | Standard export columns. |
| `polars` | Parquet | Standard export columns. |
| `battery-archive` | Parquet | Standard export columns. |
| `cellpy` | CSV | `data_point`, `test_time`, `current`, `voltage`, plus optional cycle, step, capacity, and energy columns. |
| `beep` | CSV | `test_time`, `current`, `voltage`, plus optional cycle, step, capacity, and energy columns. |
| `pybamm` | CSV | `time_s`, `current_a`. |
| `pyprobe` | Parquet | `time_s`, `voltage_v`, `current_a`, plus optional cycle, step, and capacity columns. |

Use `bds export-targets` or `bds.list_export_targets()` to inspect the registry.

See [BDF compatibility status](bdf-compatibility.md) for the boundary between
the current legacy BDF-style target and a future formal conformance report.

## Time Semantics

`Date Time` is the absolute sample timestamp when the source file provides one,
or when an adapter can derive it from a source start timestamp and elapsed test
time. If the source file does not include timezone information, the timestamp is
preserved as local or unspecified time; the package does not assert UTC.

Date text that starts with a four-digit year is copied unchanged. Other layouts
(`06/02/2019 23:58`, `06.02.2019 23:58`) depend on a day/month order that an
export file cannot carry, so they are written as ISO 8601 rendered from the
timestamp BDS parsed with the profile's `date_order` (`2019-02-06T23:58:00`). A
reader without the profile then reads the same instant. Naive text stays naive;
text with an explicit zone is written in UTC with a `Z` suffix. The conversion
report records the rule and the number of rewritten values under
`export_date_time`. Text BDS could not parse is copied unchanged.

`Test Time (s)` is elapsed time from the start of the full test.

`Step Time (s)` is elapsed time within the active step.

## Validation

Use:

```bash
bds validate normalized.bds.csv
```

or:

```python
from battery_data_steward.api import validate_file

report = validate_file("normalized.bds.csv")
```

Export validation accepts the user-facing export labels. Internal dataframe
validation uses canonical labels.
