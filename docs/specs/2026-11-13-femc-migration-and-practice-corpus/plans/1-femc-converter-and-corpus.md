---
diazo: research-archive-in-a-box/femc-migration-and-practice-corpus
file: PLAN1
status: done
approved: 2026-11-13T22:26:53-06:00
hash: c76a9863dbd5dd3d22bea13a1c65ab2f7b351a2c1d1138d4f571c19cd93cc1be
rests_on: [AGNT1, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, AGNT8, AGNT9, DCSN1, DCSN2]
record: README.md
---

# PLAN1: The FEMC converter and the ten-dataset corpus

## Spec

`spec.md` in this folder, approved. This plan builds all of it: the `femc` package in `examples/femc/` with FEMC's `archive.yaml`, the ten conversions, and the audit counts.

## The change

A new uv workspace member, `examples/femc/`, holding:

- `archive.yaml`: FEMC's archive config.
- `src/femc/eml.py`: `standardize(xml: str) -> tuple[str, list[str]]`, which rewrites a FEMC record into standard EML and returns the lines of what it dropped.
- `src/femc/convert.py`: `convert(dataset: Path, sources: Path, out: Path) -> Path`, which writes one package from one `practice-data/femc/<dataset>/` folder and its row of `SOURCES.md`.
- `src/femc/cli.py`: `femc convert <dataset-folder> <out-folder>`, with `--sources` defaulting to the `SOURCES.md` beside the dataset folder.
- `tests/`, with invented records and files written in FEMC's shape. None of FEMC's own records or files are committed.

The root `pyproject.toml` gains the member, its `src` on `mypy_path`, `examples/femc` in pytest's `testpaths` and `femc` in isort's first-party list, so `just check` covers it. `archive_contract` and `cruise` are not changed.

The ten datasets are already on Court's machine: the four new ones were fetched on 2026-11-13 through FEMC's public pages (two downloads through the anonymous Download Data form, four EML records from `/eml_xmlview`), with rows in `SOURCES.md` and lines in `CHECKSUMS.sha256` (`shasum -a 256 -c` passes for every file). Facts found while fetching them that the converter must handle:

- Three of the four new records name their project `researchProject`, not `project`.
- Vegetation Class Raster is an ESRI ArcInfo binary grid: a zip of nine `.adf` and companion files that only work together.
- Mount Mansfield Quadrat Images is a zip of 88 JPEG photographs, 209 MB.
- The `dataTable`'s `shortName` holds the download's file name in some records and is empty in others.

## Left out

Everything in the spec's Left out, and:

- Any change to `archive_contract` or `cruise`. If a conversion shows the core can't hold something FEMC has, it goes to the coordinating session as a note for Plan 2, not into this plan.
- Reading the raster's cells or the photographs' contents: they are recorded as files with sizes and hashes, nothing more.
- A command that converts a whole folder at once: the ten are run one by one.

## Where

- Code: `examples/femc/` on a branch from `origin/main` in a worktree at `.worktrees/research-archive-in-a-box/plan5/femc-converter`, merged by pull request.
- Inputs: `practice-data/femc/` in the main clone, read only.
- Outputs: `practice-data/packages/<dataset>/` and `practice-data/audit/` in the main clone, git-ignored. The hand-made `practice-data/packages/ozone-bioindicators/` is replaced by the converted one, after moving the old folder to `practice-data/packages/_draft-ozone-bioindicators/` so nothing is lost.
- Counts for the FEMC report: `documents/femc-audit-counts.md` in this planning folder.

### Task 1: The femc package and FEMC's config

**Does:** Creates the `examples/femc/` workspace member with an empty `femc` package, its `femc` command (printing help), `py.typed`, and FEMC's `archive.yaml`; wires it into the root `pyproject.toml`; adds one test that `archive.yaml` loads with `archive_contract.config.load_config`.
**Files:** `examples/femc/pyproject.toml`, `examples/femc/archive.yaml`, `examples/femc/src/femc/__init__.py`, `examples/femc/src/femc/cli.py`, `examples/femc/src/femc/py.typed`, `examples/femc/tests/test_config.py`, `pyproject.toml`, `uv.lock`
**Checks:** `just check-python`; `uv run femc --help`
**Serves:** none (rests on calls AGNT1, AGNT6)

`archive.yaml`: `publisher: Forest Ecosystem Monitoring Cooperative`, `profiles: [core, ecology]`, `themes: [air, climate change, forest, soil, water, wildlife]`. No `infrastructure` section: FEMC is not deployed by this plan. The package depends on `archive-contract` only (workspace source).

### Task 2: Reading FEMC's EML

**Does:** Writes `femc.eml.standardize`, which rewrites a FEMC record into standard EML so the unchanged `from_eml` reads it, and returns what it dropped.
**Files:** `examples/femc/src/femc/eml.py`, `examples/femc/tests/test_eml.py`, `examples/femc/tests/fixtures/eml/*.xml`
**Checks:** `just check-python`
**Serves:** none (rests on calls AGNT2, AGNT7)

The rewrites, each with a test on an invented record:

- `researchProject` becomes `project`.
- The `dataTable`'s `title`, `description` (as `abstract/para`), `purpose` (as `purpose/para`) and `coverage` move up to the dataset; the table gets `entityName` from its title and `entityDescription` from its description. An empty `purpose` or `shortName` is dropped silently; the `dataTable`'s non-empty `shortName` is dropped and reported.
- Project `personnel` children named for a role (`principalInvestigator`, `contentProvider`, any other) become `personnel` elements with `individualName` (`givenName`, `surName`) and `role` set to the element's name. An empty `personnel` is removed.
- `publisher/metadataProvider`'s children move up into `publisher`.
- `measurementType` becomes `measurementScale`; an `enumeratedDomain` directly on an attribute moves into its scale's `nonNumericDomain`; an empty scale element is left for `from_eml` to report.
- `distibution` becomes `distribution`.
- A `rangeOfDates` with a `beginDate` and no `endDate` gets the end marker the EML export writes for `end: unknown` (`archive_contract.exports.eml.END_UNKNOWN`), so `from_eml` reads it back as unknown.
- `physical/citation` is removed from the record and returned separately, for `archive:citation`.

The test for the whole: `from_eml(standardize(record))` on an invented record in FEMC's full shape gives a title, a description, a temporal coverage, a project with its people, one resource with its fields, and the code list, and every line `from_eml` skips is in the returned list.

### Task 3: Writing a package

**Does:** Writes `femc.convert.convert` and the `femc convert` command: reads the record through `standardize` and `from_eml`, lays out the files, matches columns, sets rights and access, and writes the manifest, `checksums.sha256`, `README.md` and `_build/not-imported.txt`.
**Files:** `examples/femc/src/femc/convert.py`, `examples/femc/src/femc/cli.py`, `examples/femc/tests/test_convert.py`, `examples/femc/tests/fixtures/datasets/**`
**Checks:** `just check-python`
**Serves:** DCSN1 (rests on calls AGNT3, AGNT4, AGNT7, AGNT8)

What it writes:

- **Identity.** `name` and `id` are the dataset folder's name; `version` is `"1"`; `archive:legacyIdentifiers` holds the EML package id (from `from_eml`) and FEMC's object name (`femc-object`, such as `VMC.23.214`); `homepage` is the source page from `SOURCES.md`; `archive:citation` is the record's citation.
- **Rights and access** from the `SOURCES.md` row: "CC0 - Public domain" becomes license `CC0-1.0`, "CC BY-NC-SA 4.0" becomes `CC-BY-NC-SA-4.0` (the only two the corpus shows; any other text stops the conversion with a clear message), "Linked - third party determines data license" becomes `third-party` with those words as the statement, "None shown on the overview page" becomes `undetermined`. Access: a "none (By request)" data file is `by-request`, "none (Description only)" is `description-only`, everything else `open`.
- **Files.** A CSV goes to `data/` unchanged as a `table`. A zip is unpacked into `data/<zip stem>/` and not copied: a shapefile set becomes one `vector` resource with `archive:files` (every part, `.shp.xml`, `.sbn` and `.sbx` included) and `archive:attributes` naming the `.dbf` columns as the `.dbf` header spells them; a CSV beside it becomes its own `table`, and an `.xlsx` of the same name an alternate of that CSV; an ArcInfo grid (a folder or zip holding `hdr.adf`) becomes one `raster` resource with `archive:files` for every file; each JPEG becomes its own `media` resource named from its file stem. `eml.xml` goes to `original/eml.xml` as a `file` resource. Every file gets `bytes` and a `sha256` hash.
- **Columns.** For a table, the columns are read from the file's header row; each becomes a field. The record's attributes are matched to columns by exact name, then case-insensitively, then by a 10-character truncation for a shapefile's columns; a match carries the attribute's description, its declared type and its code list, and the attribute's name goes in `archive:sourceName` when it differs. Where the record declares no type, the type is inferred from the column's values (integer, number, date, otherwise string) with the standard library, and the inference is listed. Attributes with no column, and columns with no attribute, are listed.
- **Linked records.** When there is no data file and the citation contains "Available online at:" followed by a URL, a `linked` resource points at that URL with no format.
- **The not-imported list**, `_build/not-imported.txt`: the lines `standardize` dropped, the lines `from_eml` skipped, attributes with no column, columns with no attribute, and inferred types, one per line, each with its reason.
- `checksums.sha256` and `README.md` are written with `archive_contract.validate.package_files` and `archive_contract.exports.readme.render_readme`, as the sample package's build does.

Tests run `convert` on invented dataset folders, each a few rows: a CSV table whose record describes one extra attribute and misses one column and uses a different case for another; a linked record with the URL only in its citation; a zip holding a three-feature shapefile set with a CSV and an `.xlsx` (written in the test with `pyshp` and `openpyxl`, already dev dependencies); a metadata-only By-request record. Each test asserts the manifest's resources, fields and rights, that `archive_contract.validate.validate_package` returns no findings, and the exact lines of `_build/not-imported.txt`.

### Task 4: Convert the ten

**Does:** Runs `femc convert` on each of the ten datasets in the spec's order and `cruise diagnose` on each result, fixing the converter until no package has a structure error. Every fix that a real dataset forces gets a test on an invented record or file showing the same case.
**Files:** `examples/femc/src/femc/*.py` and `examples/femc/tests/**` for fixes; outputs under `practice-data/packages/` (not committed)
**Checks:** `just check-python`; for each dataset, `uv run femc convert ../../../research-archive-in-a-box/practice-data/femc/<dataset> <out>` exits 0, then `uv run cruise diagnose <package> --json | jq -e '[.findings[] | select(.ruleId | startswith("structure."))] | length == 0'` exits 0
**Serves:** DCSN1 (rests on call AGNT5)

The order: ozone-bioindicators, data-rescue-inventory, improve-fine-aerosol, camels-hump-census, aerial-detection-survey, fia-tree-level, vegetation-class-raster, mount-mansfield-quadrat-images, development-related-te-species, white-clover-biomonitor. Before the first run, move the hand-made `practice-data/packages/ozone-bioindicators/` to `practice-data/packages/_draft-ozone-bioindicators/`. A blocking quality error (a missing creator, an undetermined license) is expected and is not a failure: only `structure.*` findings fail this check. If a dataset needs something the core can't hold, stop and bring it to Court with the evidence rather than working around it.

### Task 5: The audit and its counts

**Does:** Runs `cruise audit` over the ten with FEMC's config, keeps the full output under `practice-data/audit/`, and writes the counts the FEMC report needs, with no evidence values, to this folder's `documents/femc-audit-counts.md`.
**Files:** `docs/specs/2026-11-13-femc-migration-and-practice-corpus/documents/femc-audit-counts.md`; `practice-data/audit/audit.json` and `practice-data/audit/<dataset>.json` (not committed)
**Checks:** `uv run cruise audit --config examples/femc/archive.yaml --json <packages-folder> > <audit>/audit.json` exits 0; `jq -e '.packages | length == 10' <audit>/audit.json` exits 0
**Serves:** DCSN2 (rests on call AGNT9)

`femc-audit-counts.md` has one table row per dataset: its name, errors, warnings, notes, completeness score, and the find, understand and trust counts; then, per dataset, the rule ids that fired with how many times each. It is built from `audit.json` with `jq` and holds no `evidence`, `values` or `message` text, since messages can quote data. Its header says which commit of the converter and of cruise produced it and when. It is committed with the planning folder's next commit.
