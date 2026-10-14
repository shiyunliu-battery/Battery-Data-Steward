# Battery Data Steward: project direction

**Inspect. Validate. Trace. Reuse.**

Battery Data Steward is an open-source toolkit for battery data inspection,
quality assurance, and evidence-aware preprocessing. It helps researchers
review raw data and processing decisions before downstream analysis. Its
internal normalized schema is an implementation contract, not a claim to define
an industry standard or certify scientific fitness.

## Current capabilities

- Local, non-mutating inspection of supported time-series files with detection,
  mapping previews, validation findings, bounded diagnostics, and next actions.
- Diagnostics for time-axis, current-sign, cycle/step, and optional-field risks,
  subject to adapter scope and the evidence available in a source export.
- Time-series and EIS conversion, table validation, batch processing, mapping
  profiles, and reports with available provenance and repair metadata.
- JSON, HTML, XLSX, and PDF inspection/conversion reports and batch manifests.

EIS has dedicated readers and conversion functions; do not assume every
inspection diagnostic applies to impedance inputs. Adapter evidence tiers and
representative real exports must guide deployment. Preserve uncertainty and
review warnings; successful parsing alone is not evidence of scientific fitness.

## Planned capabilities

| Direction | Intended outcome | Status |
| --- | --- | --- |
| Scientific data inspection | Broader real-export coverage for risks that can change scientific results | Existing diagnostics; extension and validation planned |
| Transformation evidence | Link source identity, parameters, reasons, before/after changes, and unresolved issues | Existing report metadata; complete workflow planned |
| Research readiness | Assess explicit prerequisites for SOH, RUL, or EIS analysis and request missing evidence | Planned; no task-specific readiness gate implemented |

The proposed **Battery Data Quality & Readiness Package** would combine reviewed
outputs, a source manifest, transformation evidence, limitations, and a
purpose-specific readiness decision. Any future decision should name its
criteria and evidence, distinguish review-required from blocked cases, and
avoid automatic repairs when the interpretation is unresolved. This is a
roadmap deliverable, not the name of a currently implemented API or report.

## Complementary projects

| Project | Intended responsibility |
| --- | --- |
| Battery Data Steward | Input-data quality and preprocessing review |
| Battery-Feature-Lab | Feature extraction and diagnostics |
| Battery Context | Evidence packages and scientific sufficiency |

These boundaries describe architectural intent. This release does not add
runtime dependencies or automatic handoffs between the projects.
