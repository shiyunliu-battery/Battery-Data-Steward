# Ecosystem Integrations

These pages show how to use `battery-data-steward` (BDS) as the first
normalization step before downstream battery, data engineering, or modelling
tools.

The common pattern is:

1. Start with raw cycler exports.
2. Convert with BDS to a validated CSV or Parquet table.
3. Load that table into the downstream tool, or reshape it with the small
   mapping shown in the integration page.

## Data Engineering

- [battery-data-steward + DuckDB](integrations/duckdb.md)
- [battery-data-steward + Polars](integrations/polars.md)

## Battery Analysis Tools

- [battery-data-steward + cellpy](integrations/cellpy.md)
- [battery-data-steward + BEEP](integrations/beep.md)

## Modelling And Diagnostic Workflows

- [battery-data-steward + PyBaMM](integrations/pybamm.md)
- [battery-data-steward + PyProBE](integrations/pyprobe.md)

## Repositories

- [battery-data-steward + Battery Archive](integrations/battery-archive.md)

## BDS Export Labels

For public handoff, use `bds convert` or `bds.convert(...)`. The default BDS
export uses labels such as `Test Time (s)`, `Voltage (V)`, and `Current (A)`.
Integration pages prefer those export labels and target presets over internal
adapter labels.
