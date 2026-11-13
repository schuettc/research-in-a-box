# Seeded gaps in the sample package

These are left in on purpose, so the audit has findings to report:

- `battery_v` has no description.
- `depth_cm` has a description that only repeats its name.
- `qc_flag` holds codes with no code list, marked `archive:codeList: "undocumented"`.
- `logger_model` has the same value in every row.

The package's `README.md` is generated from the manifest by `make.py`; this list lives here
because it describes the sample, not the data.
