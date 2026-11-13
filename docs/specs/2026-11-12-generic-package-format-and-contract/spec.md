---
diazo: research-archive-in-a-box/generic-package-format-and-contract
file: spec
status: approved
approved: 2026-11-13T00:16:25-06:00
hash: ba5b481fc01fb3105ca6a42cb0ce62dca3f3ea0b68b4e626d6e4a8c20b476011
rests_on: [AGNT1, AGNT11, AGNT8, DCSN1, AGNT2, AGNT3, DCSN6, DCSN2, DCSN3, AGNT5, DCSN4, DCSN5, AGNT4, AGNT6, AGNT10, AGNT7, AGNT9, DCSN7]
record: README.md
---

# The package format and the archive_contract package

## Goal

A written package format and a Python contract package, `archive-contract` (import `archive_contract`) at `packages/contract`, that the local tool, the backend, the web app's schema and the agent layer all build on. The format is designed from Frictionless Data Package v2, EML, DataCite and schema.org and from what any research group's data looks like. A committed, invented sample package exercises all of it, and FEMC's six practice datasets are written down in it afterwards as a test.

## The package folder

A package is a plain folder that is also a valid Frictionless v2 Data Package:

```
my-dataset/
  datapackage.json   the manifest
  data/              tidy tables (CSV now, Parquet later)
  data/codes/        code-list tables
  original/          untouched source files
  docs/              methods, protocols, field sheets
  changes.jsonl      every cleaning step, with evidence
  checksums.sha256   one line per file in the package
  README.md          generated from the manifest, never edited
```

Rules that hold everywhere:

- Standard Frictionless properties are left out when unknown, never set to null.
- Our additions sit under the `archive:` prefix and may be null.
- A resource's `format` (and `mediatype`) is the only place a file type appears. Columns are described by logical type, so adding Parquet later changes no field definitions.

Rests on: AGNT1, AGNT11

## The manifest's fields

Core fields, required before a package can be published: a `title`; a `description` of at least 50 characters; at least one creator (a contributor with the creator role); rights (next section); and at least one described resource. This is the union of what DataCite, Google Dataset Search and Frictionless require.

The archive fills in publisher, publication year, identifier and resource type at publish, from its config.

Recommended fields, following DataCite's and Google's recommended lists: keywords, other contributors, temporal coverage (an end date or `ongoing`), spatial coverage (a bounding box), related identifiers, funding and methods. A profile can promote any of them to required.

Two separate verdicts are recorded in the manifest and never merged: `archive:validation` (structurally valid or not, by which contract version, when) and `archive:quality` (the counts of findings by severity from the last audit). Valid structure says nothing about quality, and the reverse.

`archive:legacyIdentifiers` holds any identifiers the data had elsewhere, as a list of `{scheme, value}`, such as `{scheme: "eml-package-id", value: "knb-lter-xyz.12.3"}`.

Rests on: AGNT8

## Rights

A package states its rights in one of two ways: one or more licenses in Frictionless `licenses` (an SPDX id or a license URL), or `archive:rightsStatus` with a statement. The statuses are:

- `public-domain`
- `third-party`, with where the terms are set
- `all-rights-reserved`, with the statement
- `undetermined`

The local tool packages and audits data with `undetermined`, and the audit reports it. Publishing (Plan 7) refuses a package until it has a license or a stated status other than `undetermined`.

Rests on: DCSN1

## Resources and their kinds

Every resource has `archive:kind`, one of `table`, `vector`, `raster`, `document`, `media`, `file` or `linked`. A resource with no kind is read as `file`. Frictionless's own `type` stays `table` for tables and is left out otherwise.

- **Several files that only work together** (a shapefile set, a raster with its world file) are one resource. `path` names the main file (the `.shp`), and `archive:files` lists every member file with its size and hash. Checksums, previews and the web app's file list read the member list.
- **The same data in several formats** (a table as CSV and XLSX): the copy is its own resource with `archive:alternateOf` naming the primary. Only the primary carries the schema.
- **Data held elsewhere**: `archive:kind: linked`, `path` is the remote URL, and there is no hash or size. Compatibility tests run the frictionless library with remote fetching off.

Rests on: AGNT1, AGNT2, AGNT3, DCSN6

## Columns

A table's columns use Frictionless Table Schema, with three additions.

- **Names.** Source column names are kept. Frictionless `title` holds a readable label, `description` the definition. The local tool may propose a rename; when the person accepts, the new name goes into the tidy table, the old one into `archive:sourceName` on the field, and the rename into `changes.jsonl`.
- **Code lists.** Each code list is a CSV table under `data/codes/` with `code`, `label` and `description` columns. A column that uses one points at it with a Frictionless foreign key, so one list serves many columns and Frictionless validation checks every code. A column that holds codes with no list is marked `archive:codeList: "undocumented"`.
- **Sensitivity.** `archive:sensitivity` on a field is one of `personal`, `sensitive-location` or `confidential`. No flag means not sensitive.

Rests on: DCSN2, DCSN3, AGNT5

## Versions and identifiers

A package has one stable `id` across all its versions, and a `version` of `1`, `2`, `3` and so on. Changing, adding or removing a file makes the next version. A metadata edit updates the current version in place, and each edit is appended to `archive:metadataHistory` (when, who, which fields). When DOIs are on, each version gets its own DOI.

Rests on: DCSN4

## Projects

A project (a monitoring program, a grant, a long-term study) is its own small record, `project.json`, with an `id`, `title`, `abstract`, `people` and `links`. A package names its project with `archive:project: <id>`, or leaves it out. A package never copies the project's text and never sits inside a project folder.

When a package is exported, the project's current title goes into its README, its DataCite record as a related identifier of type IsPartOf, and its EML project element.

Rests on: DCSN5

## Access levels

Each package has one `archive:access` level: `open`, `restricted`, `by-request` or `description-only`. Unpublished is a state of the package in the archive, not an access level.

Rests on: AGNT4

## Profiles and the archive config

A profile is a YAML file in the contract (`profiles/core.yaml`, `profiles/ecology.yaml`), read into a `Profile` model. It lists the recommended fields it promotes to required, its vocabularies and the ids of the rules it switches on. The rules themselves are code in Plan 3. The core profile holds only the core fields above.

The archive config file, read into an `ArchiveConfig` model, is the one file an adopter edits. It picks the profiles and sets required fields, vocabularies, themes, licenses and the access levels offered, plus the publisher name the archive fills in at publish. How it maps to the CDK construct is Plan 4's.

Rests on: AGNT6

## The change log and findings

Both formats are models in the contract, drafted here and confirmed by Plan 3 when it starts.

- **`Change`**, one line of `changes.jsonl`: an id, when, who made it (person, tool or agent) and who accepted it, its kind (such as `rename`, `retype`, `recode`, `fix-value`), its target (resource and field), before and after, the reason, and the evidence (row numbers or values).
- **`Finding`**: the rule id, a severity (`error`, `warning` or `note`), a message, the target, the evidence, and an optional suggested fix.

Rests on: AGNT10, DCSN2

## Exports and import

Generated from the manifest, never edited by hand:

- EML 2.2.0, with code lists as enumerated domains and the project as the project element.
- A DataCite record and schema.org Dataset JSON-LD.
- `README.md`.

Import reads standard EML 2.1.1 and 2.2.0 into a manifest. Tolerating one archive's non-standard EML is Plan 5's.

Rests on: AGNT7, DCSN3, DCSN5

## The contract package

`packages/contract/src/archive_contract/`:

| Module | Holds |
| --- | --- |
| `manifest.py` | the package model and its `archive:` additions |
| `resources.py`, `fields.py` | resources, member files, columns |
| `rights.py`, `project.py` | rights statuses, the project record |
| `changes.py`, `findings.py` | `Change` and `Finding` |
| `profile.py`, `config.py`, `profiles/*.yaml` | profiles and the archive config |
| `validate.py` | structural validation |
| `schema.py` | JSON Schema generation (from Plan 1) |
| `exports/` | `eml.py`, `datacite.py`, `schemaorg.py`, `readme.py` |
| `imports/eml.py` | EML import |

The JSON Schema generated from the models replaces the skeleton's empty one under `packages/web/`, and Plan 1's drift check keeps it current. The frictionless library is a test-only dependency.

Rests on: AGNT11

## The sample package

`examples/sample-package/`: a small stream temperature study at invented sites, licensed CC-BY-4.0. It has a logger table with a code-list table, a site shapefile set, a small raster, a methods document, a site photo, the logger table again as XLSX, a linked resource and ongoing coverage. Known gaps are seeded in and listed in its README, so Plan 3's rules have predictable findings.

Rests on: AGNT9, DCSN3, DCSN6

## Fields the paper test added

Writing FEMC's six datasets down in the format found eight things it couldn't hold. Each is now an optional field:

- **A start with no known end:** temporal coverage takes `end: "unknown"` beside a real end date or `ongoing`.
- **Units:** `archive:unit` on a field, free text such as `degC` or `mg/L`. EML writes it in place of `unknown`.
- **Measurement scale:** `archive:measurementScale` on a field, one of `nominal`, `ordinal`, `interval`, `ratio` or `dateTime` (EML's list). EML uses it instead of guessing from the type.
- **Preferred citation:** `archive:citation` on the package, the citation the data's authors ask for. The README and schema.org (`creditText`) show it.
- **Purpose:** `archive:purpose` on the package, why the data was collected. EML writes it as `purpose`, DataCite as a description of type Other.
- **Project keywords:** `keywords` on the project record, written into EML's project.
- **Related columns:** `archive:ancillaryOf: {field, role}` on a column that qualifies another, with role `uncertainty`, `detection-limit` or `quality-flag`. Shown in the README's column dictionary and EML's attribute definition.
- **A vector resource's attribute table:** `archive:attributes`, a Table Schema on a `vector` resource describing its attribute table. EML writes it as the spatialVector's attribute list, and the validator checks its columns against the `.dbf`.

The EML import reads each of these back where EML has a place for it.

Rests on: DCSN7

## Risk and cost

Risk: low. The work adds code, docs and one example folder to a repo with no users yet. A mistake is undone by editing the contract; nothing is published or deployed, and no data from `practice-data/` is committed.

Cost: no steps for you beyond reviewing. No new programs: the frictionless library is a test-only Python dependency, and PyYAML reads the profiles.

Rests on: AGNT11

## Left out

- The quality rules and the commands that run them (Plan 3).
- Tolerating FEMC's EML quirks, and converting FEMC's data (Plan 5).
- Storage, tables and the API (Plans 4 and 6), and the publish check that enforces rights (Plan 7).
- Parquet: only the room for it.
- Per-resource access levels: one level per package for now.

Rests on: DCSN1, AGNT4

## How we'll know it works

- The sample package passes the frictionless library's validation and our own structural validation.
- Its EML export imports back to the same manifest fields; its DataCite and schema.org exports validate against their schemas.
- Each of FEMC's six practice datasets is written down in the format on paper, with anything it can't express listed.
- `just check` passes with the generated JSON Schema committed.

Rests on: AGNT7, AGNT9
