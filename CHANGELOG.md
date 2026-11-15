# Changelog

## 0.7.0 - 2026-11-15

- **Breaking:** rename the Python package and source directory to
  `battery_data_steward`. Update imports and module commands to the new namespace;
  the previous namespace is no longer shipped. The `bds` import alias and command
  remain available and use the same public objects as the canonical package.
- Rename the public base exception to `BatteryDataStewardError`; existing specific
  exception names and their behavior are unchanged.
- Write `battery-data-steward-export-v1` as the report's `export_format` identifier.
  Export columns, schema versions, numerical values, and validation rules are
  unchanged. Use `bds`, `battery-data-steward`, or `battery_data_steward` for the
  default export target; obsolete product-name aliases are removed.
- Update notebooks, documentation, package metadata, typed-package markers, tests,
  and CI/release wheel checks to use the Steward namespace.
- Consumers with direct imports from BDS 0.6.x must migrate before upgrading.
  Battery Feature Lab 0.9.0 remains pinned to BDS 0.6.x; its EIS imports and
  dependency constraint need a coordinated update for BDS 0.7.x.

## 0.6.0 - 2026-11-15

- Add two non-mutating signal screens, run during conversion, inspection, explain and audit
  (`battery_data_standard.signal_screens`):
  - **Clock divergence**: compares `unix_time_s` with `test_time_s` between consecutive records
    and reports where the wall clock advanced more than the test clock (`uncounted-wall-time`, e.g.
    a suspended test) or less (`test-time-exceeds-wall-time`, e.g. a clock correction; about one
    hour is marked as a possible daylight-saving shift). The threshold is the larger of 120 s and
    twice the wall clock's resolution.
  - **Temperature excursions**: abrupt steps per temperature channel (at least 5 °C in runs of
    changes each at least 0.5 °C and 0.05 °C/s), paired with the step that returns the channel,
    merged across channels that step together, with the record interval, steps and the voltage
    and current change at the onset (`abrupt-temperature-excursion`).
  Results are in report metadata (`clock_divergence`, `temperature_excursions`) and in
  `InspectionReport` / `ExplainReport`; events are warning-level validation and audit issues and
  never make a table invalid. No sample is changed or masked.
- On the Chen et al. (2020) LG M50 files (Zenodo 4032561): the three 45 min suspensions in the
  rest after the C/10 discharge are found at the same records as the reference analysis, and all
  nine temperature episodes (three per cell, both channels) are found; seven have identical record
  intervals and two include one more sample that is part-way through a two-sample onset or
  recovery, which the reference analysis's fixed 20 °C limit excluded.
- Audit scores of files with such events fall by 5 points per issue code, as for other warning-level
  audit issues.
- Fix exports losing the day/month order of slash- and dot-separated dates. The export copied the
  source text (`06/02/2019 23:58`, parsed as 6 February with `date_order="dayfirst"`), so any reader
  without that profile, BDS included, read it month-first (2 June) and the re-read wall clock jumped
  by about a month at each change of day. Such text is now written as ISO 8601 rendered from the
  parsed timestamp (`2019-02-06T23:58:00`) in every target that writes the date column
  (`iso_date_time_from_unix`; report metadata `export_date_time`). Year-first text is unchanged,
  naive text stays naive, and text with an explicit zone is written in UTC with `Z`. Found when BFL,
  reading a BDS export of the Chen et al. (2020) files, reported month-long suspensions at midnight.

## 0.5.0 - 2026-10-29

- **Breaking:** Python 3.11 or newer is required (see the last entry below).
- Fix EIS normalization dropping source columns. `read_eis`, `convert_eis` and
  `normalize_eis_frame` kept a non-impedance column only when its name contained one of
  ten tokens (SOC, temperature, voltage, current, time, cycle, cell, battery, measure), so
  spectrum identifiers, excitation amplitude, instrument, protocol and sequence columns were
  silently removed and a multi-spectrum table lost which spectrum each row belonged to. Every
  column other than the frequency/impedance inputs is now kept with its parsed type. A source
  column named like a generated column (`-Zim_exp_Ohm`, `Phase_exp_deg`) is omitted only when
  its values equal the generated ones; otherwise it is kept as `raw:<name>` with a warning.
- Fix EIS normalization failing with a Polars `ComputeError` when a column is empty in the
  first 100 rows and filled later. The output is now assembled column by column from the
  parsed table instead of from per-row dictionaries.
- Sort EIS output by frequency with a stable sort, so rows with equal frequency (for example
  from different spectra) keep their source order and repeated conversions are identical.
- Add advisory physics-informed inspection: unapproved candidate columns for
  unknown headerless tables and non-mutating power/capacity consistency screens
  for independently sourced measured fields. No automatic column assignment
  or conversion acceptance is introduced.
- Stabilize one-based positional field labels across Polars/pandas versions
  for unlabeled CSV inputs, and correct the two-row headerless regression mapping
  (time/voltage/current columns 4/9/10).
- Require Python 3.11 or newer. `reportlab`, a core dependency, installs Pillow, and the
  fixes for the Pillow advisories reported by `pip-audit` (Pillow 13.0.0) require Python
  3.11. On Python 3.10 users could only install a vulnerable Pillow, and the 3.10 CI jobs
  failed the dependency audit. Removed 3.10 from the CI matrix and classifiers, moved the
  ruff and mypy targets to 3.11, and applied the two resulting `datetime.UTC` lint fixes.

## 0.4.0 - 2026-10-14

- Rename the project and PyPI distribution to Battery Data Steward
  (`battery-data-steward`) and position it around inspection, quality assurance,
  and evidence-aware preprocessing.
- Preserve `bds`, the `battery_data_standard` module, public exception classes,
  schema versions, and serialized export identifiers for compatibility.
- Update installation guidance, optional-extra errors, CLI branding,
  integration documentation, and the example notebook.
- Document PyPI publishing migration and distinguish current capabilities from
  planned research-readiness assessment. The new distribution must be published
  before its PyPI installation command is available.

- Follow up on preprocessing integrity: count only eligible interpolations
  against row limits, preserve interpolation dtypes, and report partial repairs.
- Align explain sampling defaults with conversion; report boundary-skipped points.
- Skip and report empty/repeated-header EIS rows; expose explicit phase units and
  warn for unspecified units. Preserve per-sheet batch results across failures.
- Remove first-letter current-state guesses; warn when source power is preserved
  after current-sign changes.
- Fix formatted duration scaling, extended durations, legacy microamp decoding,
  dotted dates and configurable slash-date ordering.
- Preserve and split undirected accumulators by explicit status; remove incorrect
  BioLogic flag/capacity fallbacks and support NEWARE Chinese headers/states.
- Require explicit mappings for headerless wide inputs and explicit multi-channel
  workbook selection. Reject ambiguous comma numeric strings.
- Use discharge-positive current by default for PyBaMM conversion targets.
- Require declared reset semantics for capacity totals and use one-pass repeated
  step detection rather than a full table scan for every cycle.

- Compute derived power after current-sign normalization.
- Change conversion and batch sampling defaults to warning-only; interpolation
  requires explicit opt-in and skips known cycle/step boundaries and timer resets.
- Honor explicit EIS degree/radian phase units; conventional unitless phase
  headers use degrees rather than guessing from value magnitude.
- Reject nonempty invalid EIS source rows instead of silently writing a partial spectrum.
- Reject empty EIS tables and unsupported EIS schema versions during validation.

- Write the Unicode milliohm regression fixture explicitly as UTF-8 for Windows.

- Added the unified `bds inspect` command and `bds.inspect()` API for
  non-mutating single-file detection, mapping, validation findings, and next
  steps.
- Added bounded inspection findings plus JSON, HTML, Excel, and PDF inspection
  report writers. Target output is explicitly labeled as a mapping preview, not
  a conformance result.
- Kept `doctor` and `explain` behavior and public APIs compatible.

## 0.3.1 - 2026-06-10

- Removed notebooks that contained local/private path outputs.
- Updated release metadata and public version checks for the 0.3.1 release.

## 0.3.0 - 2026-06-10

- Added Repower and PEC public fixture coverage.
- Added current-sign sanity and step/cycle semantic diagnostics to conversion
  metadata and audit reports.
- Switched current-sign sanity to an opt-in adjacent-point check for files that
  need extra sign review.
- Added a fixture contribution guide for privacy-preserving regression files.
- Added `bds doctor`, adapter `evidence_tier` metadata, and ambiguous
  temperature-semantics warnings.

## 0.2.2 - 2026-06-05

- Added Arbin auxiliary temperature aliases for encoded `Aux_Temperature(... )_1`
  workbook headers so they export as `Ambient Temperature (degC)`.

## 0.2.1 - 2026-06-04

- Added `bds explain` diagnostics and report writers for JSON, HTML, Excel, and
  PDF outputs.
- Added `report_path="auto"` and regular time-sampling gap diagnostics for
  conversion reports.
- Added public API exports for export frames, file validation, and report-writing
  helpers.
- Improved audit filtering, optional-column scoring, data-kind detection aliases,
  and current-sign evidence reuse.

## 0.2.0 - 2026-06-01

- Added export targets for DuckDB, Polars, cellpy, BEEP, PyBaMM, PyProBE, and Battery Archive workflows.
- Added `bds audit` and API support for intake quality scoring across raw folders.
- Added Repower and PEC adapters, BioLogic `.mpr` support through the optional `mpr` extra, and Gamry `.DTA` EIS reading.
- Lowered the supported Python floor to Python 3.10 and expanded CI coverage to Python 3.10 through 3.13.

## 0.1.2 - 2026-05-30

- Documented how to preserve raw current sign and apply explicit time-axis
  repairs for real experimental datasets.
- Documented how to display user-facing export labels such as `Test Time (s)`,
  `Voltage (V)`, and `Current (A)` from the internal normalized dataframe.
- Added Arbin Excel workbook hardening so `Channel_*` sheets are preferred
  over duplicate/raw `RawData_*` sheets during automatic time-series reading.
- Added EIS Excel workbook hardening for Arbin/Gamry-style `ACIM_*` sheets
  with `Freq`, `Zmod`, and `Zphz` magnitude/phase columns.
- Added MATLAB vector mapping improvements for Novonix-style
  `CurrentData`/`VoltageData`/`TimeData` files and struct fields such as
  `Dataset.U` and `Dataset.I`.

## 0.1.1 - 2026-05-27

- Improved CSV header detection for Novonix exports that place protocol and
  step-limit sections before the `[Data]` table.
- Preserved Novonix attribution for files with `Date and Time`, `Run Time (h)`,
  `Step Time (h)`, `Current (A)`, and `Potential (V)` columns after a structured
  preamble.

## 0.1.0 - 2026-05-01

- Published the initial public package for battery cycler data conversion.
- Added the `battery_data_standard` Python package and the `bds` import alias.
- Added the `bds` command-line interface for format detection, conversion, validation,
  schema inspection, and batch processing.
- Added adapters for NEWARE, Arbin, Maccor, BioLogic, Novonix, BaSyTec, LANDT,
  and generic tabular exports.
- Added support for CSV, text, Excel, MATLAB, and Parquet input families where
  time, voltage, and current data can be mapped to the standard schema.
- Added standardized BDS time-series outputs with validation reports,
  column provenance, source metadata, and optional sidecar reports.
- Added EIS detection, reading, conversion, and validation entry points.
- Added archive-aware batch conversion with JSONL manifests for directories and
  supported archive files.
- Added step-level and cycle-level summary helpers for normalized time-series
  data.
- Set the normalized current convention to charge-positive and discharge-negative
  by default.
