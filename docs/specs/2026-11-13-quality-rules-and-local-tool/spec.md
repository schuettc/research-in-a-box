---
diazo: research-archive-in-a-box/quality-rules-and-local-tool
file: spec
status: approved
approved: 2026-11-13T15:09:15-06:00
hash: 684b0f9dd5c66ebc800f1822a2129b7a0ec813cd11c1b98c82b917e7b94aa4c9
rests_on: [AGNT7, DCSN1, DCSN2, AGNT2, DCSN3, AGNT1, AGNT3, AGNT4, AGNT8, AGNT5, AGNT6]
record: README.md
---

# Quality rules, cruise diagnose and cruise audit

## Goal

A researcher or curator runs `cruise diagnose` on a package folder and gets a clear list of what makes the data hard to use, each problem backed by evidence (which column, which rows, which values), plus a completeness score and whether anything blocks publishing. `cruise audit` runs the same checks over many packages and ranks them by what needs fixing. Everything runs on the user's own machine with no network.

This is the first useful piece of the local tool. Fixing problems (`tidy`), building packages (`package`) and sorting a messy folder (`inventory`, `profile`) are planned later in this folder, once diagnose has been used on real data.

**Risk.** Low. diagnose and audit only read: they never change a package, so a wrong rule produces a wrong finding, never lost data. A mistake is undone by fixing the rule. The two contract edits add optional fields, so existing packages still parse.

**Cost.** No new programs for the user and no steps they must do. One new Python dependency, DuckDB, in cruise.

## What diagnose and audit do

`cruise diagnose <package-folder>`:

1. Runs Plan 2's structure check (`validate_package`). If the manifest can't be read, it stops there and reports why.
2. Runs every quality rule that applies, skipping the data rules on any resource whose files failed the structure check.
3. Prints the findings grouped by the three questions below, each with its evidence and, where there is one, a suggested fix; then the score with its three parts; then a one-line verdict: "blocks publishing (3)" or "publishable, with 12 warnings".
4. With `--json`, prints the same as one JSON object: the structure verdict, the quality verdict with the score, and every finding in the contract's `Finding` shape.
5. Exits 1 when any finding blocks publishing, else 0, so scripts and CI can use it.

Which profiles apply comes from `--config <archive.yaml>` (the archive config, which names profiles and extra required fields) or from `--profile <name>`, repeatable. With neither, only core applies.

`cruise audit <folder>`:

1. Finds every `datapackage.json` under the folder and runs diagnose on each.
2. Prints one row per package, ranked by blockers (most first), then by score (lowest first): package, blockers, warnings, notes, score and its three parts, and the rule that fired most.
3. With `--json`, prints the rows plus every package's findings.

Neither command writes anything. Recording the verdict in a package's manifest belongs to `cruise package`, later.

Rests on: AGNT7, DCSN1, DCSN2

## The rules

The rules are grouped by the question a reader can't answer. Each is small, deterministic code with a stable id.

**Can I find, cite and reuse it?** (the package)

| Rule | Catches | Severity |
| --- | --- | --- |
| `package.core-missing` | A core field missing: title, a description of at least 50 characters, a creator, rights (a license or a stated rights status other than undetermined), a described resource. One finding per field, from Plan 2's `missing_core_fields`. | error |
| `package.profile-field-missing` | A field the selected profiles or the archive config require, such as methods or coverage under ecology. One finding per field. | error |

**Can I understand each column?** (every column of a table, and every attribute of a vector resource)

| Rule | Catches | Severity |
| --- | --- | --- |
| `field.description-missing` | No description. | warning |
| `field.description-repeats-name` | A description that only repeats the column's name or source name, ignoring case, spaces and punctuation. | warning |
| `field.unit-missing` | A number or integer column on an interval or ratio scale, or with no scale stated, that has no `archive:unit`. | warning |
| `field.codes-undocumented` | A column marked `archive:codeList: "undocumented"`. The evidence lists its distinct values, up to 20. | warning |

**Can I trust the values?** (table resources, read with DuckDB)

| Rule | Catches | Severity |
| --- | --- | --- |
| `values.not-declared-type` | Values that don't read as the column's declared type and aren't declared missing, such as `n/a` in an integer column. | warning |
| `values.placeholder` | A number column holding a placeholder that isn't declared missing: one of -9999, -999, -99, 9999, 99999, or a negative value that repeats in a column whose other values are all zero or more (the aerial survey's `-1` in HOST1). | warning |
| `values.constant` | A column with one value in every row (more than one row). | warning |
| `values.mixed-date-formats` | A string column whose values parse as dates in more than one pattern, such as `2024-06-01` and `06/01/2024`. | warning |
| `values.dates-outside-coverage` | Values in a date, datetime or year column outside the package's temporal coverage. | warning |
| `values.coverage-gap` | A whole year inside the temporal coverage with no rows (Ozone's 1998). | note |
| `values.coordinates-out-of-range` | Latitudes beyond ±90 or longitudes beyond ±180, in a geopoint column or in columns named for latitude and longitude; when the values fit the other axis's range, the finding says they look swapped. Also values outside the package's spatial coverage box. | warning |
| `values.duplicate-key` | Rows that repeat the table's primary key. | warning |

Every finding names its target (resource and column) and carries evidence: row numbers (up to 20), the values, and how many rows show it.

Species-name matching against ITIS is not in this set: every species column in the practice data holds numeric codes, which the code-list rule covers.

Rests on: AGNT2, DCSN1, DCSN3

## What blocks publishing

Severity has one meaning everywhere:

- **error** blocks publishing: Plan 2's structure errors, `package.core-missing` and `package.profile-field-missing`.
- **warning** makes the data hard to use: every column and value rule.
- **note** is worth knowing: `values.coverage-gap`.

No column or value rule is ever an error, so legacy data with gaps it can't fill can still be published, with the gaps shown. diagnose's verdict and exit code follow from this; Plan 7's ingest uses the same rule.

Rests on: DCSN1

## The completeness score

A check is one rule applied to one target: `field.description-missing` on a 17-column table is 17 checks; `package.core-missing` is 5 checks, one per core field. A check passes when the rule finds nothing on that target. Value rules count one check per column they look at.

The score is the share of checks passed, as a whole percent rounded down, with no weights, overall and for each of the three questions. diagnose shows it as `61% (find 4 of 7, understand 21 of 51, trust 30 of 34)`, so anyone can recount it. Structure errors are not in the score: they block, and are shown on their own.

audit ranks by blockers first, then by lowest score, so packages of different sizes compare fairly: a 207-column table isn't ranked worse just for having more columns.

Rests on: DCSN2

## How the rules are built

- The rules live in a `cruise.rules` module that imports without the command line, so the archive's ingest (Plan 7) and the MCP server (Plan 9) can run the same rules by depending on cruise as a library.
- A rule is a Python function registered with its id, its question (find, understand or trust), what it looks at (the package, each column, or each table's rows) and its severity. It returns findings.
- Core rules always run. A profile can switch on extra rules by id through its `rules` list; no profile has any yet.
- Tables are read through one function backed by DuckDB, given a resource. It is the only place a file format appears, so Parquet later is one more branch there. CSV files are read as text and each value rule tests casts in SQL, so a bad value becomes a finding rather than a failed read.
- No rule touches the network. A test runs diagnose with network access disabled.

Rests on: AGNT1, AGNT2

## Changes to the contract

- `Evidence` gains `count`: how many rows show the problem, since a finding like "18,104 rows hold -1" can't list them all. `Finding` and `Change` are otherwise confirmed as Plan 2 drafted them.
- `QualityVerdict` gains the score: `score` (0 to 100) and, for each of find, understand and trust, the checks passed and applicable. All optional, so manifests without them still parse.
- `ecology.yaml`'s three placeholder rules become core rules (`field.unit-missing`, `values.dates-outside-coverage`, `values.coordinates-out-of-range`), since none is specific to ecology, and its `rules` list is emptied.
- The web app's JSON Schema is regenerated from the changed models, as Plan 2's check requires.

Rests on: AGNT2, AGNT3, DCSN2

## Test data

- **The sample package** (Plan 2) must give exactly its 4 planted findings and no others: `field.description-missing` on battery_v, `field.description-repeats-name` on depth_cm, `field.codes-undocumented` on qc_flag, `values.constant` on logger_model.
- **A messy test package**, new, beside cruise's tests: small, invented, structurally valid, with each value problem planted once and listed in its GAPS.md (a placeholder, a value of the wrong type, two date formats, a date outside coverage, a missing year, swapped and out-of-range coordinates, a duplicate key, a measurement with no unit), plus a missing license and missing methods under ecology so the blockers show.
- **Ozone** is checked on paper: the rule list catches 26 of its 36 hand-made findings; the other 10 are about building the package or FEMC's EML (8), a field the contract lacks (1) and a judgement call (1). A real diagnose run on Ozone waits on Plan 5 converting it, since the hand-made package uses an early draft of the format.

Rests on: AGNT4, AGNT8

## Left out

- `cruise tidy` and `cruise package`: the next plan in this folder, planned after diagnose has been used (follow-up PARK3). Calls AGNT5 (types inferred when packaging) and AGNT6 (tidy proposals wait in `_build/`) are its starting point.
- `cruise inventory` and `cruise profile`, and how far inventory groups files without an agent: after that (PARK4).
- Species-name matching against ITIS (PARK5).
- A taxonomic coverage field in the contract (PARK1), and spotting a grid id with no grid described, which is a judgement call for the agent layer (PARK2).
- Writing the verdict into a package's manifest: `cruise package` does it later.
- A per-archive or new-submissions-only list of extra blocking rules (options D and E of DCSN1): addable later on top of this.
- Running on Ozone and the other FEMC data: Plan 5.

Rests on: AGNT5, AGNT6, AGNT7, DCSN1, DCSN3

## How we'll know it works

1. `cruise diagnose examples/sample-package` prints exactly the 4 planted findings, no blockers, a score, and exits 0.
2. `cruise diagnose` on the messy test package prints one finding for each planted problem in its GAPS.md and no others, reports 2 blockers, and exits 1.
3. `cruise audit` over a folder holding both packages ranks the messy package first.
4. `--json` output from both commands validates against the contract's `Finding` model.
5. The diagnose tests pass with network access disabled.
6. The repo's existing checks (`just check`, as CI runs it) pass, including the regenerated JSON Schema.

Rests on: AGNT4, AGNT8
