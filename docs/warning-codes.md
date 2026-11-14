# Warning and Issue Codes

BDS reports are machine-readable. Production pipelines should branch on
`valid`, `status`, and issue `code` values rather than parsing message text.

`bds inspect` carries validation codes into its `findings` list. Older
unstructured adapter warnings use the fallback code `conversion-warning`; its
message is explanatory text and is not a stable machine-readable subtype.
Inspection reports expose `findings_total` and `findings_truncated` so pipelines
can distinguish a complete finding list from the default bounded summary.

## Validation Codes

Common validation issue codes include:

| Code | Meaning | Typical action |
| --- | --- | --- |
| `missing-required-column` | A required BDS column is absent. | Check column aliases, use a profile, or file an adapter issue. |
| `null-required-values` | A required column contains nulls. | Inspect the source rows and repair policy. |
| `non-numeric-required` | A required numeric column has non-numeric values. | Check header-row detection and decimal formatting. |
| `non-finite-required` | A required numeric column contains NaN or infinity. | Remove or repair invalid rows before analysis. |
| `non-increasing-test-time` | `test_time_s` is not strictly increasing. | Use `repair_policy="repair"` only if shifting or sorting is scientifically acceptable. |
| `missing-sample-timepoints` | A regular `test_time_s` grid has one or more missing sample points. | Review `metadata["time_sampling"]`; use `time_sampling_policy="warn"` to avoid interpolation or set the expected interval explicitly. |
| `missing-optional-column` | Optional metadata or measurement columns are absent. | Informational for audits; not a quality-score penalty. |
| `uncounted-wall-time` | Between two consecutive records the wall clock (`unix_time_s`) advanced more than `test_time_s`; the test clock did not count that time (for example, a suspended test). Warning only. | Review `metadata["clock_divergence"]["events"]`; decide whether analyses spanning the interval (relaxation, self-discharge, thermal recovery) are affected. |
| `test-time-exceeds-wall-time` | `test_time_s` advanced more than the wall clock; the wall clock was corrected or shifted. Events of about one hour carry `possible_dst_shift`. Warning only. | Check the instrument's clock settings and time zone before using wall-clock time. |
| `abrupt-temperature-excursion` | A temperature channel stepped by at least the step threshold, faster than the rate threshold, and later stepped back (or never did before the end of the record). Episodes merge channels that step together. Warning only; no sample is masked. | Review `metadata["temperature_excursions"]["episodes"]`; compare the onset voltage/current change and the coincident channels before excluding samples from temperature statistics. |
| `unsupported-schema-version` | The requested schema is not supported by this release. | Pin a compatible package version or update the pipeline. |

## Audit Codes

Audit records may include additional issue codes:

| Code | Meaning |
| --- | --- |
| `duplicated-timestamps` | Duplicate elapsed-time values were detected. |
| `non-monotonic-time` | One or more elapsed-time transitions moved backward or stayed flat. |
| `suspicious-flat-voltage` | Voltage appears flat across enough points to be suspicious. |
| `suspicious-flat-current` | Current appears flat across enough points to be suspicious. |
| `current-sign-suspicious` | Current sign conflicts with adjacent voltage trends. |
| `cycle-anomalies` | Cycle index has decreases or negative values. |
| `step-anomalies` | Step index has decreases or negative values. |
| `repeated-step-segments` | The same step id appears in non-contiguous segments within one cycle. |
| `step-transition-discontinuity` | A step boundary has non-increasing test time or step time that does not reset. |
| `inferred-step-cycle-semantics` | A semantic field such as `test_time_s` was inferred rather than source-provided. |
| `temperature-semantics-ambiguous` | A raw temperature header was mapped as ambient/chamber temperature but may represent a surface or auxiliary sensor. |
| `uncounted-wall-time` | Wall clock advanced more than test time between consecutive records. |
| `test-time-exceeds-wall-time` | Test time advanced more than the wall clock between consecutive records. |
| `abrupt-temperature-excursion` | Abrupt temperature step(s) paired with a return, per channel, merged across channels. |
| `conversion-error` | Conversion failed during audit. |
| `unsupported-file` | The file was identified as helper content or unsupported data. |

Optional-column coverage is exposed as `record.completeness` in audit JSON and
HTML reports. It is useful for dataset profiling, but it does not mean a valid
minimal file is poor quality.
