---
diazo: research-archive-in-a-box/generic-package-format-and-contract
file: PLAN3
status: done
approved: 2026-11-13T11:41:31-06:00
hash: 436ec49749e1e54a5515f5aafd1bd24a936596a52cb1fb73afbdc34c415a2b80
rests_on: [DCSN7]
record: README.md
---

# PLAN3: The eight fields from the paper test

## Spec

`docs/specs/2026-11-12-generic-package-format-and-contract/spec.md`, section "Fields the paper test added" (DCSN7). PLAN1 and PLAN2 (merged in research-in-a-box#1 and #3) built the models, exports and EML import this plan extends.

## The change

Add the eight optional fields the spec lists, carry each through the exports and the EML import where its standard has a place, check `archive:attributes` against the `.dbf` in the validator, and use every new field in the sample package so its round trip covers them. Then mark each gap closed in the paper test.

Risk: low. Every field is optional, so existing packages stay valid; undone by reverting the PR.

## Left out

- Quality rules that use the new fields, such as "numeric column with no unit": Plan 3 (quality rules).
- A unit vocabulary: `archive:unit` is free text for now.
- Reading FEMC's non-standard EML into these fields: Plan 5.

## Where

Repo `schuettc/research-in-a-box`. Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-in-a-box/plan2-paper-test-fields`, branch `plan2-paper-test-fields` from `origin/main`, finishing with a PR merged once CI passes.

### Task 1: The eight fields on the models

**Does:** Adds to the models, each optional, with a test per rule: `end: "unknown"` on `TemporalCoverage` (exclusive with a real end and with `ongoing`); `archive:unit` and `archive:measurementScale` (nominal, ordinal, interval, ratio, dateTime) on `Field`; `archive:citation` and `archive:purpose` on `Manifest`; `keywords` on `Project`; `archive:ancillaryOf` (`field` naming another column in the same schema, `role` one of uncertainty, detection-limit, quality-flag) on `Field`; `archive:attributes` (a `TableSchema`) on `Resource`, allowed only when `archive:kind` is `vector`. Regenerates the committed JSON Schema.
**Files:** `packages/contract/src/archive_contract/manifest.py`, `fields.py`, `resources.py`, `project.py`, matching tests, `packages/web/src/schema/archive-contract.schema.json`
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN7

Tests: an ancillaryOf naming a missing column is refused; `archive:attributes` on a table resource is refused; `end: "unknown"` with `ongoing: true` is refused.

### Task 2: Validator check for attribute tables

**Does:** `validate_package` reads the `.dbf` header of a vector resource that has `archive:attributes` (with the standard library, from the member file listed in `archive:files`) and reports `structure.attributes-mismatch` for a column described but absent, or present but not described.
**Files:** `packages/contract/src/archive_contract/validate.py`, `packages/contract/tests/test_validate.py`, a fixture under `packages/contract/tests/fixtures/`
**Checks:** `uv run pytest packages/contract`; `just check`
**Serves:** DCSN7

Reading the `.dbf` keeps to the package folder and refuses symlinks, as the rest of the validator does.

### Task 3: Exports, import and the sample package

**Does:** Carries the new fields through: README (citation, purpose, units, scale, related columns, the vector resource's attribute columns, project keywords); EML 2.2.0 (unit in place of `unknown`, measurementScale from the field when set, purpose, project keywords, an attribute annotation for the related column, spatialVector attributeList, open-ended coverage for `end: "unknown"`); schema.org (`creditText`, open interval for unknown end); DataCite (purpose as a description of type Other). `from_eml` reads back units, scales, purpose, project keywords and the spatialVector attribute list, and drops their entries from `skipped`. Adds every new field to the sample package (a unit and scale on each logger column, a citation, a purpose, an uncertainty column for temperature, attribute columns on the sites shapefile) and extends the round-trip test to compare them.
**Files:** `packages/contract/src/archive_contract/exports/readme.py`, `exports/eml.py`, `exports/schemaorg.py`, `exports/datacite.py`, `imports/eml.py`, matching tests, `examples/sample-package/_build/make.py`, `examples/sample-package/` (regenerated)
**Checks:** `uv run pytest packages/contract`; `uv run python examples/sample-package/_build/make.py && git diff --exit-code examples/sample-package` (after commit); `just check`
**Serves:** DCSN7

The sample's EML export still validates against the EML 2.2.0 XSD. The paper test document gets a line under each of its eight gaps saying it is closed and by which field.
