# BDF Compatibility

BDS exports to the Battery Data Format (BDF), the open standard published by
the Battery Data Alliance:

```bash
bds convert raw_export.csv normalized.bdf.csv --target bdf
```

This writes BDF preferred labels (`Test Time / s`, `Voltage / V`,
`Current / A`, `Cycle Count / 1`, `Step ID`, `Record Index / 1`, ...).

The cycler's step column (Arbin `Step_Index`, NEWARE or Maccor `Step ID`,
BioLogic `Ns`) is written as BDF `Step ID`: the program step identifier, which
may recur in successive cycles. BDS does not write `Step Count / 1`, because BDF
defines it as a counter that never repeats and BDS does not derive one. The
source record or data-point number is written as `Record Index / 1`, and the
first auxiliary temperature channel as `Temperature T1 / degC`.

`bds validate normalized.bdf.csv` maps the BDF labels back to the canonical BDS
columns and validates them against the BDS schema. Files written by BDS 0.7.0 and earlier, which used
`Step Count / 1`, `Step Index / 1` and `Surface Temperature T1 / degC`, are still
read and validated.

## Scope

`--target bdf` aligns column labels and units with the BDF table schema. It
does not emit ontology bindings, JSON-LD/CSVW metadata, or a conformance
report, so this output is BDF-aligned rather than BDF-conformant. Where BDS
and the BDA specification differ, the specification is authoritative.
