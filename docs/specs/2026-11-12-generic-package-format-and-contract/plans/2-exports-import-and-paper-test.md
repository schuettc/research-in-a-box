---
diazo: research-archive-in-a-box/generic-package-format-and-contract
file: PLAN2
status: approved
approved: 2026-11-13T10:46:53-06:00
hash: 79c66f8263b96913a9fceaaacec3bb350f7e630b8d8c1263a9777079a2de19e3
rests_on: [AGNT1, AGNT11, AGNT3, AGNT7, AGNT8, DCSN1, DCSN3, DCSN4, DCSN5, DCSN6]
record: README.md
---

# PLAN2: Exports, EML import and the FEMC paper test

## Spec

`docs/specs/2026-11-12-generic-package-format-and-contract/spec.md`, approved 2026-11-13. PLAN1 (merged in research-in-a-box#1) built the models this plan reads: `Manifest`, `Resource`, `Field`, `TableSchema`, `Project`, `RightsStatus`, `License` in `archive_contract`.

## The change

Add the four exports the spec names (EML 2.2.0, DataCite, schema.org JSON-LD, README) and EML import (2.1.1 and 2.2.0), all generated from the manifest and never edited by hand. Prove them on the sample package: EML export validates against the EML 2.2.0 schema and imports back to the same manifest fields; DataCite validates against DataCite's JSON Schema; schema.org carries every field Google requires. Then write each of FEMC's six practice datasets down in the format on paper, listing anything the format can't express.

Risk: low. New code and one document in a repo with no users; undone by reverting the PR. The paper test describes FEMC's public metadata and commits no FEMC data files.

## Left out

- Tolerating FEMC's non-standard EML (the misspelled `distibution` tag and others): Plan 5.
- Converting FEMC's data into packages: Plan 5.
- A DataCite XML export: the JSON form is what DataCite's REST API takes, and Plan 7 mints DOIs through it.
- Exporting a whole project on its own: a project appears inside each package's exports.

## Where

Repo `schuettc/research-in-a-box`. Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-in-a-box/plan2-exports-import`, branch `plan2-exports-import` from `origin/main`, finishing with a PR merged once CI passes.

### Task 1: README export

**Does:** Adds `exports/readme.py` with `render_readme(manifest, project=None) -> str`: title, description, citation line, creators, rights, project title, access level, coverage, and one section per resource with its kind and, for tables, the column dictionary (name, title, type, description, code list). Switches the sample build to write the generated README, and moves the sample's list of seeded gaps to `examples/sample-package/_build/GAPS.md`.
**Files:** `packages/contract/src/archive_contract/exports/__init__.py`, `exports/readme.py`, `packages/contract/tests/test_export_readme.py`, `examples/sample-package/_build/make.py`, `examples/sample-package/_build/GAPS.md`, `examples/sample-package/README.md`, `examples/sample-package/checksums.sha256`
**Checks:** `uv run pytest packages/contract`; `uv run python examples/sample-package/_build/make.py && git diff --exit-code examples/sample-package`; `just check`
**Serves:** DCSN3, DCSN5 (rests on call AGNT11)

Tests: the sample's README names every resource and every column; a field marked `archive:codeList: "undocumented"` is shown as undocumented; a missing standard property prints nothing, not "None".

### Task 2: DataCite export

**Does:** Adds `exports/datacite.py` with `to_datacite(manifest, project=None, publisher=..., year=..., identifier=None) -> dict` producing DataCite 4.x JSON: creators, titles, publisher, publicationYear, types (resourceTypeGeneral Dataset), descriptions (Abstract, plus Methods when present), subjects from keywords, dates (Collected from temporal coverage), geoLocations from the bounding box, rightsList from licenses or the rights statement, relatedIdentifiers (including IsPartOf the project), fundingReferences and version. Validates against DataCite's JSON Schema, vendored as a test fixture with its source URL and licence noted.
**Files:** `packages/contract/src/archive_contract/exports/datacite.py`, `packages/contract/tests/test_export_datacite.py`, `packages/contract/tests/fixtures/schemas/datacite/`, root `pyproject.toml` dev dependency jsonschema, `uv.lock`
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN1, DCSN4, DCSN5 (rests on call AGNT11)

Tests: the sample's record validates; an `undetermined` rights status is refused with a clear error (it can't be published); `third-party` writes its statement into rightsList.

### Task 3: schema.org export

**Does:** Adds `exports/schemaorg.py` with `to_schemaorg(manifest, project=None, url=None) -> dict`, a schema.org `Dataset` JSON-LD: name, description, creator, license, keywords, temporalCoverage (an open interval `start/..` when ongoing), spatialCoverage as a GeoShape box, distribution (one DataDownload per non-linked resource with encodingFormat), isPartOf the project, version and identifier.
**Files:** `packages/contract/src/archive_contract/exports/schemaorg.py`, `packages/contract/tests/test_export_schemaorg.py`
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN5 (rests on call AGNT11)

Tests: Google's required name and 50-to-5000-character description are present; ongoing coverage gives `2024-06-01/..`; a linked resource appears with its remote URL as contentUrl.

### Task 4: EML 2.2.0 export

**Does:** Adds `exports/eml.py` with `to_eml(manifest, project=None) -> str`: dataset title, creators, abstract, keywords, intellectual rights, coverage (temporal and geographic), methods, project, one `dataTable` per table resource with its attributes (code lists as `enumeratedDomain`, read from the code-list table; `archive:codeList: "undocumented"` as a text domain with a note), and `otherEntity` for every other local resource. Validates against the EML 2.2.0 XSD with lxml; the XSDs are vendored as a test fixture with their source and licence noted.
**Files:** `packages/contract/src/archive_contract/exports/eml.py`, `packages/contract/tests/test_export_eml.py`, `packages/contract/tests/fixtures/schemas/eml-2.2.0/`, root `pyproject.toml` dev dependency lxml, `uv.lock`
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN3, DCSN5 (rests on call AGNT7)

The export uses only the standard library's XML writer at run time; lxml is test-only, to validate.

### Task 5: EML import

**Does:** Adds `imports/eml.py` with `from_eml(xml: str) -> Manifest` reading standard EML 2.1.1 and 2.2.0: title, creators, abstract, keywords, rights (a recognised licence URL or name becomes a license, other text becomes a `third-party` or `all-rights-reserved` status with the text as its statement), coverage, methods, project, and each `dataTable`'s attributes as fields (an `enumeratedDomain` becomes a code list, returned alongside the manifest as table rows to write under `data/codes/`). The original package id goes into `archive:legacyIdentifiers` with scheme `eml-package-id`. Round trip: `from_eml(to_eml(sample))` gives the same title, creators, description, keywords, rights, coverage, fields and code lists as the sample.
**Files:** `packages/contract/src/archive_contract/imports/__init__.py`, `imports/eml.py`, `packages/contract/tests/test_import_eml.py`, `packages/contract/tests/fixtures/eml/` (one small invented 2.1.1 record and one 2.2.0 record)
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN1, DCSN3 (rests on calls AGNT7, AGNT8)

Standard EML only: a record with a non-standard tag imports what is standard and returns a list of what it skipped, rather than failing.

### Task 6: The FEMC paper test

**Does:** Writes `docs/specs/2026-11-12-generic-package-format-and-contract/documents/femc-paper-test.md`: for each of the six practice datasets in `practice-data/femc/`, which resources it becomes and of which kind, how its rights are stated, its code lists, its legacy identifiers, its project, and what `from_eml` reads from its EML record and what it skips. Ends with a list of anything the format cannot express, each with the dataset that showed it. Runs `from_eml` on each record locally to fill in what is read and skipped; nothing from `practice-data/` is committed.
**Files:** `docs/specs/2026-11-12-generic-package-format-and-contract/documents/femc-paper-test.md`
**Checks:** `git status --porcelain --ignored practice-data` shows only `!! practice-data/`; `just check`
**Serves:** DCSN1, DCSN3, DCSN5, DCSN6 (rests on calls AGNT1, AGNT3, AGNT8)

Anything the paper test finds the format can't express is brought to the user as a decision before changing the contract.
