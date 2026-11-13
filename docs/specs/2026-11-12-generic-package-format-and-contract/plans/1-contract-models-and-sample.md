---
diazo: research-archive-in-a-box/generic-package-format-and-contract
file: PLAN1
status: printed
hash: daafc8ef92d405db2ee99ac79d9d0d8440ee0e89b034693abf5895a761c2e465
rests_on: [AGNT1, AGNT10, AGNT11, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT8, AGNT9, DCSN1, DCSN2, DCSN3, DCSN4, DCSN5, DCSN6]
record: README.md
---

# PLAN1: The contract models, validation, schema and sample package

## Spec

`docs/specs/2026-11-12-generic-package-format-and-contract/spec.md`, approved 2026-11-13.

## The change

Fill `packages/contract` (the empty package from Plan 1's skeleton) with the Pydantic models the spec names, a structural validator, and the real JSON Schema in place of the skeleton's empty one. Then build the committed sample package under `examples/sample-package/` and prove it passes both our validator and the frictionless library.

Serialisation rule for every model: standard Frictionless properties are dropped when unset (never written as null); `archive:` properties are written under their prefixed names and may be null. Models accept unknown properties and keep them, since Frictionless allows extra properties.

Risk: low. New code and one example folder in a repo with no users; undone by editing or reverting the PR.

## Left out

- Exports and EML import: PLAN2.
- The quality rules and the publish check (Plans 3 and 7). The validator checks structure only.
- Anything under `practice-data/`.

## Where

The repo `schuettc/research-in-a-box` once Plan 1's skeleton is pushed. Work in a worktree at `/Users/courtschuett/GitHub/personal/.worktrees/research-in-a-box/plan2-contract-models`, branch `plan2-contract-models` from `origin/main`, and finish with a PR with auto-merge on.

### Task 1: Resource, field and rights models

**Does:** Adds `fields.py` (a Table Schema field with `archive:sourceName`, `archive:codeList` and `archive:sensitivity`, plus foreign keys on the schema), `resources.py` (a resource with `archive:kind`, `archive:files` member list, `archive:alternateOf`, and the linked rule: a URL path with no hash or bytes) and `rights.py` (licenses, `archive:rightsStatus` with its statement, and the four statuses) with one test per rule the spec states.
**Files:** `packages/contract/src/archive_contract/fields.py`, `resources.py`, `rights.py`, `packages/contract/tests/test_resources.py`, `test_fields.py`, `test_rights.py`
**Checks:** `uv run pytest packages/contract`; `just check-python`
**Serves:** DCSN1, DCSN2, DCSN3, DCSN6 (rests on calls AGNT1, AGNT2, AGNT3, AGNT5)

Tests cover: a resource with no kind reads as `file`; a linked resource with a hash is refused; `third-party` and `all-rights-reserved` need a statement; an unset standard property is absent from the dump while an unset `archive:` property may be null.

### Task 2: Manifest and project models

**Does:** Adds `manifest.py` (the package: core and recommended fields, `id`, integer-string `version`, `archive:project`, `archive:access`, `archive:legacyIdentifiers`, `archive:metadataHistory`, `archive:validation`, `archive:quality`, temporal coverage with `ongoing`, spatial coverage as a bounding box) and `project.py` (the `project.json` record) with tests.
**Files:** `packages/contract/src/archive_contract/manifest.py`, `project.py`, `packages/contract/tests/test_manifest.py`, `test_project.py`
**Checks:** `uv run pytest packages/contract`; `just check-python`
**Serves:** DCSN4, DCSN5 (rests on calls AGNT4, AGNT8)

The core fields are optional on the model (a package can be built and audited without them); a `missing_core_fields(manifest)` helper lists which are absent, for Plan 3's audit and Plan 7's publish check to call.

### Task 3: Change, Finding, Profile and ArchiveConfig

**Does:** Adds `changes.py` and `findings.py` with the drafted `Change` and `Finding` shapes, `profile.py` reading `profiles/core.yaml` and `profiles/ecology.yaml` into `Profile`, and `config.py` with `ArchiveConfig`, each with tests; adds PyYAML as a dependency.
**Files:** `packages/contract/src/archive_contract/changes.py`, `findings.py`, `profile.py`, `config.py`, `profiles/core.yaml`, `profiles/ecology.yaml`, `packages/contract/pyproject.toml`, `uv.lock`, matching tests
**Checks:** `uv run pytest packages/contract`; `just check-python`
**Serves:** DCSN2 (rests on calls AGNT6, AGNT10)

The ecology profile promotes temporal and spatial coverage and methods to required and names its rule ids; the rule ids are placeholders that Plan 3 owns, listed in a comment as such.

### Task 4: Structural validation

**Does:** Adds `validate.py` with `validate_package(path) -> list[Finding]`: the manifest parses; every foreign key, `archive:alternateOf` and `archive:files` entry points at something that exists; every file listed has the size and hash recorded; `checksums.sha256` matches the files. Each problem is a `Finding` with severity `error` and the rule id `structure.<name>`.
**Files:** `packages/contract/src/archive_contract/validate.py`, `packages/contract/tests/test_validate.py` and small fixture folders under `packages/contract/tests/fixtures/`
**Checks:** `uv run pytest packages/contract`; `just check-python`
**Serves:** DCSN3, DCSN6 (rests on call AGNT11)

One fixture per failure: a foreign key to a missing resource, a member file missing, a wrong hash, a stale checksums line.

### Task 5: The real JSON Schema

**Does:** Points `archive_contract.schema` at the manifest model (the skeleton's empty `ArchiveContract` model is removed) and also emits the `Project`, `Change`, `Finding` and `ArchiveConfig` schemas under `$defs`; regenerates the committed schema with `just schema`.
**Files:** `packages/contract/src/archive_contract/schema.py`, `packages/contract/tests/test_schema.py`, `packages/web/src/schema/archive-contract.schema.json`
**Checks:** `just check` (includes the drift check)
**Serves:** none (rests on calls AGNT6, AGNT11)

### Task 6: The sample package

**Does:** Builds `examples/sample-package/`, a stream temperature study at invented sites under CC-BY-4.0, from a committed build script, and adds a test that validates it with `validate_package` and with the frictionless library (a dev dependency, remote fetching off).
**Files:** `examples/sample-package/` (datapackage.json, data/, data/codes/, original/, docs/, changes.jsonl, checksums.sha256, README.md), `examples/sample-package/_build/make.py`, `packages/contract/tests/test_sample_package.py`, root `pyproject.toml` dev dependencies (frictionless, pyshp, openpyxl), `uv.lock`
**Checks:** `uv run python examples/sample-package/_build/make.py && git diff --exit-code examples/sample-package` (the build is reproducible); `uv run pytest packages/contract/tests/test_sample_package.py`; `just check`
**Serves:** DCSN3, DCSN6 (rests on calls AGNT1, AGNT2, AGNT3, AGNT9)

Contents, all small and invented:

- `data/logger.csv`: about 60 rows of water temperature at three sites, with a `condition` column linked to `data/codes/condition-codes.csv` by foreign key.
- `data/sites/`: a point shapefile set (`.shp`, `.shx`, `.dbf`, `.prj`) written with pyshp, as one `vector` resource with its members listed.
- `data/depth.asc` and `data/depth.prj`: a tiny ESRI ASCII grid as one `raster` resource.
- `data/logger.xlsx`: the logger table again, with `archive:alternateOf: logger`.
- `docs/methods.md` (`document`) and `docs/site-photo.png` (`media`, a small generated image).
- A `linked` resource pointing at `https://example.org/stream-temperature/discharge.csv`.
- Temporal coverage `ongoing`; one accepted rename in `changes.jsonl`.

Seeded gaps, listed in the README: one column with no description, one column whose description repeats its name, a coded column marked `archive:codeList: "undocumented"`, and a constant column. The README itself is hand-written for now and replaced by the generated one in PLAN2.
