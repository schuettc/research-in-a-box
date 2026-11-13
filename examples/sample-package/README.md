# Stream temperature at three invented sites

A small sample package for the research archive. Every site, reading and person in it is
invented. It is licensed [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/).

This README is written by hand for now; the generated README replaces it later.

## What is in it

| Resource          | Kind     | Files                                                          |
| ----------------- | -------- | -------------------------------------------------------------- |
| `logger`          | table    | `data/logger.csv`: 60 hourly readings at three sites           |
| `condition-codes` | table    | `data/codes/condition-codes.csv`: the condition column codes   |
| `sites`           | vector   | `data/sites/sites.shp` with its `.shx`, `.dbf` and `.prj`      |
| `depth`           | raster   | `data/depth.asc` with `data/depth.prj`                         |
| `logger-xlsx`     | table    | `data/logger.xlsx`, an alternate of `logger`                   |
| `logger-original` | file     | `original/logger-raw.csv`, the untouched export                |
| `methods`         | document | `docs/methods.md`                                              |
| `site-photo`      | media    | `docs/site-photo.png`                                          |
| `discharge`       | linked   | held at `https://example.org/stream-temperature/discharge.csv` |

The temporal coverage is ongoing. `changes.jsonl` records one accepted rename: the source
column `WTemp` became `water_temp_c`.

## Seeded gaps

These are left in on purpose, so the audit has findings to report:

- `battery_v` has no description.
- `depth_cm` has a description that only repeats its name.
- `qc_flag` holds codes with no code list, marked `archive:codeList: "undocumented"`.
- `logger_model` has the same value in every row.

## Rebuilding

Everything except this README is written by `_build/make.py`, which is deterministic:

```sh
uv run python examples/sample-package/_build/make.py
```
