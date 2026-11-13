---
diazo: research-archive-in-a-box/quality-rules-and-local-tool
file: PLAN1
status: done
approved: 2026-11-13T15:19:29-06:00
hash: e2a6dcc6162d53c12be673e1579c9c43c82692041224046fd16bac402459ea45
rests_on: [AGNT1, AGNT2, AGNT3, AGNT4, AGNT7, DCSN1, DCSN2]
record: README.md
---

# PLAN1: The rules, cruise diagnose and cruise audit

## Spec

`docs/specs/2026-11-13-quality-rules-and-local-tool/spec.md`, all of it: this plan builds everything the spec covers.

## The change

- Two small contract edits: `Evidence.count`, and the score on `QualityVerdict`. The ecology profile's three placeholder rules move into core.
- In cruise: a rules module with the 14 rules, one DuckDB-backed table reader, the score, `cruise diagnose` and `cruise audit`.
- A small messy test package that plants each value problem once.

**Risk.** Low. Both commands only read, and the contract edits add optional fields. A wrong rule gives a wrong finding and is undone by fixing the rule.

**Cost.** No steps for the user. One new dependency, `duckdb`, in cruise.

**Gates, sized to that risk.** CI's own commands (`just check-python` and `just check-schema`) and the tests each task names. One review at the end by a reviewer from the other provider family. No stress or fuzz runs.

## Left out

- `tidy`, `package`, `inventory` and `profile`: later plans in this folder (PARK3, PARK4).
- Species names against ITIS (PARK5), a taxonomic coverage field (PARK1), grid ids (PARK2).
- Writing the verdict into a manifest.
- Extra blocking rules per archive (DCSN1 options D and E).
- A run on Ozone or other FEMC data: Plan 5.

## Where

- Repo: `schuettc/research-in-a-box`, base branch `main`.
- Branch `plan3/diagnose-and-audit`, in the worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan3/diagnose-and-audit`. The branch already holds this planning folder's commit.
- Contract: `packages/contract/src/archive_contract/`.
- Tool: `packages/tool/src/cruise/`, tests in `packages/tool/tests/`.
- One pull request for the whole plan, with auto-merge on once CI is green.

### Task 1: Contract edits

**Does:** Adds `count` to `Evidence` and the score to `QualityVerdict`, and moves the ecology profile's placeholder rules into core. Then regenerates the web app's JSON Schema.
**Files:** `packages/contract/src/archive_contract/findings.py`, `manifest.py`, `profiles/ecology.yaml`, `packages/contract/tests/test_findings.py`, `test_manifest.py`, `test_profile.py`, `packages/web/src/schema/archive-contract.schema.json`
**Checks:** `just check-python`, `just check-schema`
**Serves:** DCSN2 (rests on calls AGNT2, AGNT3)

- `Evidence.count: NonNegativeInt | None`.
- A `CheckCount` model (`passed`, `applicable`, both non-negative ints, passed ≤ applicable).
- `QualityVerdict` gains `score: int | None` (0 to 100) and `find`, `understand` and `trust`, each a `CheckCount | None`. All optional, so existing manifests still parse. Add a test that the sample package's manifest still loads.
- `ecology.yaml`: empty its `rules` list and replace the placeholder comment with one line saying the units, coverage-date and coordinate checks are core rules.
- Regenerate the schema with `just schema`.

### Task 2: Rules engine, package and column rules, cruise diagnose

**Does:** Builds the rule registry, the table reader, the 6 package and column rules, the score and `cruise diagnose`, proven on the sample package.
**Files:** `packages/tool/pyproject.toml` (add `duckdb`), `uv.lock`, `packages/tool/src/cruise/rules/__init__.py`, `rules/registry.py`, `rules/package.py`, `rules/fields.py`, `tables.py`, `score.py`, `diagnose.py`, `cli.py`, `packages/tool/tests/test_rules_package.py`, `test_rules_fields.py`, `test_diagnose.py`, `test_cli.py`
**Checks:** `just check-python`; `uv run cruise diagnose examples/sample-package` exits 0
**Serves:** DCSN1, DCSN2 (rests on calls AGNT1, AGNT2, AGNT7)

- **Registry.** A rule is a function registered with a decorator giving its id, its question (`find`, `understand`, `trust`), what it looks at (`package`, `field` or `table`) and its severity. It receives a context (the package root, the `Manifest`, the required fields from the selected profiles and config, and the table reader) and returns `Finding`s plus the number of checks it applied, so the score can count passes.
- **Required fields** are the union of each selected profile's `required` and the archive config's `required`, minus the core fields, which `package.core-missing` covers.
- **Profiles.** Core rules always run; a profile's `rules` list switches on extra registered rules by id, and an unknown id is an error.
- **`cruise.rules` imports without the CLI** (no argparse in it), so Plan 7 and Plan 9 can import it.
- **The rules this task builds:** `package.core-missing` (one finding per id from `missing_core_fields`), `package.profile-field-missing`, `field.description-missing`, `field.description-repeats-name`, `field.unit-missing` and `field.codes-undocumented`, exactly as the spec's tables define them. Field rules run over every table column and every vector attribute.
- **`tables.py`.** One function: given the root and a table resource, return a DuckDB relation over its file read as text (`all_varchar`), with the schema's missing values known. It refuses any format but `csv` with a clear error. It is the only place a format appears.
- **`score.py`.** The share of checks passed, rounded down to a whole percent, overall and per question, as in the spec. Structure findings are excluded.
- **`diagnose.py`.**
  - Runs `validate_package` first and stops if the manifest can't be read.
  - Skips table rules on resources with structure findings.
  - Returns the findings (structure first) and a `QualityVerdict` with the score.
- **CLI.** `cruise diagnose <folder> [--json] [--profile NAME]... [--config FILE]`.
  - Text output is grouped by question, each finding with its target, evidence and suggested fix, then the score line and the verdict line.
  - `--json` prints `{"validation": ..., "quality": ..., "findings": [...]}` from the contract models.
  - Exit 1 when any finding is an error, else 0.
- **Tests.**
  - The sample package gives exactly 4 findings: battery_v, depth_cm and qc_flag here, and logger_model's `values.constant` in Task 3. Until then, assert the 3 column findings and no others from this task's rules.
  - A test runs diagnose with `socket.socket` patched to raise, and it still passes.
  - `--json` output round-trips through `Finding`.

### Task 3: The messy test package and the value rules

**Does:** Adds the messy test package and the 8 value rules. diagnose then gives exactly the planted findings on both packages.
**Files:** `packages/tool/tests/fixtures/messy-package/` (`datapackage.json`, `data/*.csv`, `checksums.sha256`, `_build/GAPS.md`, `_build/make.py`), `packages/tool/src/cruise/rules/values.py`, `packages/tool/tests/test_rules_values.py`, `test_diagnose.py`
**Checks:** `just check-python`; `uv run cruise diagnose packages/tool/tests/fixtures/messy-package --profile ecology` exits 1
**Serves:** DCSN1 (rests on calls AGNT4, AGNT2)

- **The value rules:** `values.not-declared-type`, `values.placeholder`, `values.constant`, `values.mixed-date-formats`, `values.dates-outside-coverage`, `values.coverage-gap` (note), `values.coordinates-out-of-range` and `values.duplicate-key`.
  - Each works as the spec's table says, in DuckDB SQL over the text relation from `tables.py`, testing casts with `TRY_CAST`.
  - Evidence gives up to 20 row numbers (1-based data rows), the values, and `count`.
  - Coordinates are found by a `geopoint` type or by column names (`lat`, `latitude`, `lon`, `long`, `longitude`, any case).
  - Dates are checked against `archive:temporalCoverage`; with `ongoing`, only the start bounds them.
- **The messy package:**
  - Invented and small: one table of about 40 rows, one code list. It must be structurally valid (`validate_package` returns nothing); `_build/make.py` writes the files, sizes, hashes and checksums, as the sample package's own `make.py` does.
  - Plant exactly once each: a `-999` in a number column; an `n/a` in an integer column; a string date column with two formats; a date before the coverage start; a year inside the coverage with no rows; one row with latitude and longitude swapped and one latitude of 95; a repeated primary key; a ratio column with no unit.
  - No license and no `archive:methods`, so under `--profile ecology` there are exactly 2 blockers. Every other column is described and has a unit, so nothing unplanted fires.
  - `_build/GAPS.md` lists each planted problem with the rule id it must trigger.
- **Tests.**
  - The messy package gives exactly the GAPS.md findings: rule id and target, no more and no fewer.
  - The sample package now gives exactly its 4 planted findings.
  - Each value rule has a focused unit test on a tiny in-memory table.

### Task 4: cruise audit

**Does:** Builds `cruise audit`: diagnose over every package under a folder, ranked.
**Files:** `packages/tool/src/cruise/audit.py`, `cli.py`, `packages/tool/tests/test_audit.py`
**Checks:** `just check-python`; `uv run cruise audit packages/tool/tests/fixtures examples` lists the messy package first
**Serves:** DCSN2 (rests on call AGNT7)

- Finds every `datapackage.json` under the folders given, skipping `_build/` and `node_modules/`, and runs diagnose on each, with the same `--profile` and `--config` options.
- Text output: one row per package, ranked by error count (most first), then score (lowest first), then path. Columns: path, errors, warnings, notes, score with its three parts, and the rule that fired most.
- `--json` prints the rows and each package's findings. Exit 0 unless a folder doesn't exist.
- A package whose manifest can't be read is listed first, with its structure error.
- Tests: the ranking order on the two packages plus a broken copy made in a temp folder; `--json` round-trips through `Finding`.

### Task 5: Show the runs

**Does:** Records the real output of the three sign-off runs, so the user can see how they worked without running them: in this folder's `documents/cruise-runs-4f023dd.txt` and in PR #9's description. Added at sign-off, after the user asked to see the runs.
**Files:** `docs/specs/2026-11-13-quality-rules-and-local-tool/documents/cruise-runs-4f023dd.txt`, PR #9's body
**Checks:** `uv run cruise diagnose examples/sample-package` exits 0; `uv run cruise diagnose packages/tool/tests/fixtures/messy-package --profile ecology` exits 1; `uv run cruise audit packages/tool/tests/fixtures examples` exits 0
**Serves:** none (rests on call AGNT4)

- Run the three commands from the worktree at the PR's head and save their output, each with its command and exit code.
- Run the audit a second time with `--profile ecology`, so its row for the messy package matches the diagnose run (2 errors).
- Put the same output in PR #9's description.
