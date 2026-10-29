"""EIS table normalization helpers."""

from __future__ import annotations

import math
import re
import warnings
from pathlib import Path
from typing import Any

import polars as pl

from .exceptions import ConversionError
from .io import read_table_with_metadata, write_dataframe
from .reports import ValidationIssue, ValidationReport

EIS_SCHEMA_VERSION = "eis-2026-05"
EIS_REQUIRED_COLUMNS = ("Frequency_Hz", "Zre_exp_Ohm", "Zim_exp_Ohm")
EIS_GENERATED_COLUMNS = (*EIS_REQUIRED_COLUMNS, "-Zim_exp_Ohm", "Phase_exp_deg")


def read_eis(
    path: str | Path, *, sheet: str | int | None = None, phase_unit: str | None = None
) -> pl.DataFrame:
    """Read CSV/Excel-like EIS data into an eisfit-compatible table."""
    input_path = Path(path)
    result = read_table_with_metadata(input_path, options={"sheet": sheet, "excel_sheets": "eis"})
    for key in ("empty_rows_skipped", "repeated_headers_skipped"):
        count = result.metadata.get(key, 0)
        if count:
            warnings.warn(f"EIS input cleanup: {key}={count}.", UserWarning, stacklevel=2)
    raw = _add_frequency_values_from_sibling(input_path, result.data)
    return normalize_eis_frame(raw, phase_unit=phase_unit)


def convert_eis(
    input_path: str | Path,
    output_path: str | Path,
    *,
    format: str = "csv",
    sheet: str | int | None = None,
    phase_unit: str | None = None,
) -> ValidationReport:
    """Convert an EIS file into the package EIS standard table."""
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always", UserWarning)
        df = read_eis(input_path, sheet=sheet, phase_unit=phase_unit)
    report = validate_eis(df)
    report.issues.extend(
        ValidationIssue("warning", "eis-normalization-notice", str(notice.message)) for notice in notices
    )
    if not report.valid:
        raise ConversionError(
            "EIS validation failed: "
            + "; ".join(issue.message for issue in report.issues if issue.level == "error")
        )
    write_dataframe(df, output_path, fmt=format)
    return report


def validate_eis(df: pl.DataFrame, *, schema_version: str = EIS_SCHEMA_VERSION) -> ValidationReport:
    issues: list[ValidationIssue] = []
    if schema_version != EIS_SCHEMA_VERSION:
        issues.append(
            ValidationIssue(
                "error", "unsupported-eis-schema-version", f"Unsupported EIS schema version {schema_version}."
            )
        )
    if df.is_empty():
        issues.append(ValidationIssue("error", "empty-eis-dataframe", "EIS dataframe has no rows."))
    for column in EIS_REQUIRED_COLUMNS:
        if column not in df.columns:
            issues.append(
                ValidationIssue(
                    "error",
                    "missing-required-eis-column",
                    f"Missing required EIS column {column}.",
                    column,
                )
            )

    for column in EIS_REQUIRED_COLUMNS:
        if column not in df.columns:
            continue
        values = df[column].cast(pl.Float64, strict=False).to_list()
        invalid = sum(value is None or not math.isfinite(float(value)) for value in values)
        if invalid:
            issues.append(
                ValidationIssue(
                    "error",
                    "invalid-eis-numeric-values",
                    f"{column} has {invalid} null or non-finite values.",
                    column,
                )
            )

    if "Frequency_Hz" in df.columns:
        values = df["Frequency_Hz"].cast(pl.Float64, strict=False).to_list()
        non_positive = sum(
            value is not None and math.isfinite(float(value)) and float(value) <= 0 for value in values
        )
        if non_positive:
            issues.append(
                ValidationIssue(
                    "error",
                    "non-positive-eis-frequency",
                    f"Frequency_Hz has {non_positive} non-positive values.",
                    "Frequency_Hz",
                )
            )

    return ValidationReport(
        valid=not any(issue.level == "error" for issue in issues),
        schema_version=schema_version,
        rows=df.height,
        columns=list(df.columns),
        issues=issues,
    )


def normalize_eis_frame(raw: pl.DataFrame, *, phase_unit: str | None = None) -> pl.DataFrame:
    if phase_unit not in {None, "deg", "rad"}:
        raise ConversionError("phase_unit must be deg or rad.")
    raw = _clean_columns(raw)
    nonempty = (
        pl.any_horizontal(
            [
                pl.col(column).cast(pl.String, strict=False).str.strip_chars().fill_null("") != ""
                for column in raw.columns
            ]
        )
        if raw.columns
        else pl.lit(False)
    )
    filtered = raw.filter(nonempty)
    if filtered.height != raw.height:
        warnings.warn(
            f"Skipped {raw.height - filtered.height} entirely empty EIS table rows.",
            UserWarning,
            stacklevel=2,
        )
    raw = filtered
    raw = _expand_complex_impedance_column(raw)
    freq_col = _find_column(
        raw.columns,
        (
            "Frequency_Hz",
            "Frequency (Hz)",
            "Frequency(Hz)",
            "Frequency/Hz",
            "Frequency_Hz",
            "Frequency",
            "Data: Frequency",
            "Fit: Frequency",
            "freq/Hz",
            "freq",
            "Freq",
        ),
    )
    zmod_col = _find_column(
        raw.columns,
        (
            "Zmod",
            "Zmod_Ohm",
            "Zmod (Ohm)",
            "|Z|",
            "|Z|/Ohm",
            "|Z| (Ohm)",
            "Magnitude",
            "Magnitude_Ohm",
            "Mod(Z)",
        ),
    )
    phase_col = _find_column(
        raw.columns,
        (
            "Zphase_deg",
            "Phase(deg)",
            "Phase (deg)",
            "Phase_exp_deg",
            "Phase(rad)",
            "Phase (rad)",
            "Phase_rad",
            "Zphase_rad",
            "Zphz",
            "Zphase",
            "Phase",
        ),
    )
    zre_col = _find_column(
        raw.columns,
        (
            "Zre_exp_Ohm",
            "Zreal_Ohm",
            "Zreal",
            "Zre",
            "Z'",
            "Data: Z'",
            "Fit: Z'",
            "Re(Z)/Ohm",
            "Re(Z)",
            "impedance_R/Ohm",
            "impedance_R",
            "R(ohm)",
            "Z1 /Ohm",
            "Z1",
            "Real_Ohm",
        ),
    )
    zim_col = _find_column(
        raw.columns,
        (
            "Zim_exp_Ohm",
            "Zimag_Ohm",
            "Zimag",
            "Zim",
            "Z''",
            "Data: Z''",
            "Fit: Z''",
            "Im(Z)/Ohm",
            "Im(Z)",
            "-Im(Z)/Ohm",
            "-Im(Z)",
            "impedance_I/Ohm",
            "impedance_I",
            "X(ohm)",
            "Z2 /Ohm",
            "Z2",
            "Imag_Ohm",
        ),
    )
    if freq_col is None or zre_col is None or zim_col is None:
        if freq_col is not None and zmod_col is not None and phase_col is not None:
            return _normalize_eis_magnitude_phase_frame(
                raw, freq_col, zmod_col, phase_col, phase_unit=phase_unit
            )
        raise ConversionError(
            "Could not infer EIS frequency, real impedance, and imaginary impedance columns. "
            f"Raw columns: {raw.columns}"
        )

    freq = _float_values(raw[freq_col])
    zre = _float_values(raw[zre_col])
    zim = _float_values(raw[zim_col])
    if _is_negative_imaginary_column(zim_col):
        zim = [None if value is None else -value for value in zim]

    computed: dict[str, list[float]] = {name: [] for name in EIS_GENERATED_COLUMNS}
    for index, (f_value, zr_value, zi_value) in enumerate(zip(freq, zre, zim, strict=True)):
        if (
            f_value is None
            or zr_value is None
            or zi_value is None
            or not math.isfinite(f_value)
            or not math.isfinite(zr_value)
            or not math.isfinite(zi_value)
            or f_value <= 0
        ):
            raise ConversionError(
                f"Invalid EIS row at parsed table row {index + 1}; no rows were silently discarded."
            )
        computed["Frequency_Hz"].append(f_value)
        computed["Zre_exp_Ohm"].append(zr_value)
        computed["Zim_exp_Ohm"].append(zi_value)
        computed["-Zim_exp_Ohm"].append(-zi_value)
        computed["Phase_exp_deg"].append(math.degrees(math.atan2(zi_value, zr_value)))

    if not computed["Frequency_Hz"]:
        raise ConversionError("No valid EIS rows found after normalization.")
    return _assemble_eis_frame(computed, raw, used_columns={freq_col, zre_col, zim_col})


def looks_like_eis_columns(columns: list[str]) -> bool:
    slugs = {_slug(column) for column in columns}
    has_freq = any("freq" in slug or "frequency" in slug for slug in slugs)
    has_real = any(
        token in slug
        for slug in slugs
        for token in ("zre", "zreal", "rez", "realohm", "impedancer", "roh", "rohm")
    ) or any("z'" in str(column).lower() and "z''" not in str(column).lower() for column in columns)
    has_imag = any(
        token in slug for slug in slugs for token in ("zim", "zimag", "imz", "imagohm", "impedancei", "xohm")
    ) or any("z''" in str(column).lower() for column in columns)
    has_magnitude = any(token in slug for slug in slugs for token in ("zmod", "modz", "magnitude"))
    has_phase = any(token in slug for slug in slugs for token in ("zphz", "zphase", "phase"))
    return has_freq and ((has_real and has_imag) or (has_magnitude and has_phase))


def _normalize_eis_magnitude_phase_frame(
    raw: pl.DataFrame, freq_col: str, zmod_col: str, phase_col: str, *, phase_unit: str | None = None
) -> pl.DataFrame:
    freq = _float_values(raw[freq_col])
    zmod = _float_values(raw[zmod_col])
    phase = _float_values(raw[phase_col])
    phase_slug = _slug(phase_col)
    if phase_unit is not None:
        phase_in_degrees = phase_unit == "deg"
    elif "deg" in phase_slug:
        phase_in_degrees = True
    elif "rad" in phase_slug:
        phase_in_degrees = False
    elif phase_slug in {"zphz", "phase", "zphase"}:
        phase_in_degrees = True
        warnings.warn(
            "EIS phase unit is unspecified; degrees were assumed. Use phase_unit='rad' for radians or label the phase column explicitly.",
            UserWarning,
            stacklevel=2,
        )
    else:
        raise ConversionError("EIS phase unit is ambiguous; label the column Phase(deg) or Phase(rad).")

    computed: dict[str, list[float]] = {name: [] for name in EIS_GENERATED_COLUMNS}
    for index, (f_value, mag_value, phase_value) in enumerate(zip(freq, zmod, phase, strict=True)):
        if (
            f_value is None
            or mag_value is None
            or phase_value is None
            or not math.isfinite(f_value)
            or not math.isfinite(mag_value)
            or not math.isfinite(phase_value)
            or f_value <= 0
        ):
            raise ConversionError(
                f"Invalid EIS row at parsed table row {index + 1}; no rows were silently discarded."
            )
        angle = math.radians(phase_value) if phase_in_degrees else phase_value
        zre = mag_value * math.cos(angle)
        zim = mag_value * math.sin(angle)
        computed["Frequency_Hz"].append(f_value)
        computed["Zre_exp_Ohm"].append(zre)
        computed["Zim_exp_Ohm"].append(zim)
        computed["-Zim_exp_Ohm"].append(-zim)
        computed["Phase_exp_deg"].append(math.degrees(angle))

    if not computed["Frequency_Hz"]:
        raise ConversionError("No valid EIS rows found after magnitude/phase normalization.")
    return _assemble_eis_frame(computed, raw, used_columns={freq_col, zmod_col, phase_col})


def _assemble_eis_frame(
    computed: dict[str, list[float]], raw: pl.DataFrame, *, used_columns: set[str]
) -> pl.DataFrame:
    """Join the computed impedance columns with every other source column.

    Source columns other than the frequency/impedance inputs are kept unchanged, with their
    parsed types: spectrum identifiers, measurement conditions, instrument and protocol
    fields are part of the record. A source column named like a generated column is
    omitted only when its values equal the generated ones; otherwise it is kept as
    ``raw:<name>`` with a warning. The frequency sort is stable, so rows with the same
    frequency (for example from different spectra) keep their source order.
    """
    df = pl.DataFrame(computed, schema=dict.fromkeys(EIS_GENERATED_COLUMNS, pl.Float64))
    kept: list[pl.Series] = []
    for column in raw.columns:
        if column in used_columns:
            continue
        series = raw[column]
        if column in df.columns:
            if _same_numeric_values(series, df[column]):
                continue
            renamed = f"raw:{column}"
            warnings.warn(
                f"Source column {column!r} differs from the generated {column!r}; kept as {renamed!r}.",
                UserWarning,
                stacklevel=3,
            )
            series = series.alias(renamed)
        kept.append(series)
    return df.hstack(kept).sort("Frequency_Hz", descending=True, maintain_order=True)


def _same_numeric_values(source: pl.Series, generated: pl.Series) -> bool:
    for left, right in zip(_float_values(source), generated.to_list(), strict=True):
        if left is None or right is None or not math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-12):
            return False
    return True


def _add_frequency_values_from_sibling(path: Path, raw: pl.DataFrame) -> pl.DataFrame:
    if "Frequency_Hz" in raw.columns or "FREQUENCY_VALUE" in raw.columns:
        return raw
    if "FREQUENCY_ID" not in raw.columns or "IMPEDANCE_VALUE" not in raw.columns:
        return raw
    frequency_path = path.parent / "frequencies.csv"
    if not frequency_path.exists():
        return raw
    frequencies = read_table_with_metadata(frequency_path).data
    if "FREQUENCY_ID" not in frequencies.columns or "FREQUENCY_VALUE" not in frequencies.columns:
        return raw
    mapping = {
        str(key): _parse_float(value)
        for key, value in zip(
            frequencies["FREQUENCY_ID"].to_list(),
            frequencies["FREQUENCY_VALUE"].to_list(),
            strict=False,
        )
    }
    values = [mapping.get(str(value)) for value in raw["FREQUENCY_ID"].to_list()]
    return raw.with_columns(pl.Series("Frequency_Hz", values, dtype=pl.Float64))


def _expand_complex_impedance_column(raw: pl.DataFrame) -> pl.DataFrame:
    if "IMPEDANCE_VALUE" not in raw.columns:
        return raw
    parsed = [_parse_complex(value) for value in raw["IMPEDANCE_VALUE"].to_list()]
    if not any(value is not None for value in parsed):
        return raw
    zre = [None if value is None else value.real for value in parsed]
    zim = [None if value is None else value.imag for value in parsed]
    return raw.with_columns(
        pl.Series("Zre_exp_Ohm", zre, dtype=pl.Float64),
        pl.Series("Zim_exp_Ohm", zim, dtype=pl.Float64),
    )


def _clean_columns(df: pl.DataFrame) -> pl.DataFrame:
    rename = {col: str(col).strip().replace("\t", "") for col in df.columns}
    rename = {old: new for old, new in rename.items() if old != new}
    return df.rename(rename) if rename else df


def _find_column(columns: list[str], candidates: tuple[str, ...]) -> str | None:
    exact = {str(column).strip().lower(): column for column in columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in exact:
            return exact[key]
    slugs = {_slug(column): column for column in columns}
    for candidate in candidates:
        key = _slug(candidate)
        if key in slugs:
            return slugs[key]
    return None


def _float_values(series: pl.Series) -> list[float | None]:
    values: list[float | None] = []
    for value in series.to_list():
        values.append(_parse_float(value))
    return values


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _parse_complex(value: Any) -> complex | None:
    if value is None:
        return None
    text = str(value).strip().strip("()").replace("i", "j")
    try:
        number = complex(text)
    except ValueError:
        return None
    if not math.isfinite(number.real) or not math.isfinite(number.imag):
        return None
    return number


def _is_negative_imaginary_column(column: str) -> bool:
    text = column.strip().lower()
    return text.startswith("-") or "-im" in text or "minus" in text


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())
