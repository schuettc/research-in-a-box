---
diazo: research-archive-in-a-box/femc-migration-and-practice-corpus
file: spec
status: approved
approved: 2026-11-13T22:07:37-06:00
hash: b0e4d1f91b32fa7afade457651148613482bfb2a5f13fb1cd1a113799dc91119
rests_on: [AGNT1, AGNT8, AGNT2, AGNT7, AGNT3, AGNT4, DCSN1, AGNT5, AGNT6, DCSN2, AGNT9]
record: README.md
---

# FEMC migration and practice corpus

## Goal

A converter that turns a dataset downloaded from FEMC's public archive (its EML record plus its download) into a package the contract accepts. It runs on a practice corpus of ten FEMC datasets, and `cruise audit` over the result gives the FEMC report (Plan 10b) its counts. FEMC's quirks are handled beside FEMC's own config, so `archive_contract` and `cruise` stay unchanged and generic.

## The converter

The converter lives in `examples/femc/`, beside FEMC's `archive.yaml`, as a small uv workspace package named `femc` with a `src/` layout and its own tests. It depends on `archive-contract` only, and `just check` covers it with ruff, mypy and pytest like every other package.

It takes one dataset folder from `practice-data/femc/<dataset>/` (the `eml.xml`, the download if there is one, and that dataset's row of `SOURCES.md`) and writes one package folder under `practice-data/packages/<dataset>/`. It is run as `uv run femc convert <dataset-folder> <out-folder>`. It writes the manifest, `checksums.sha256` and the generated `README.md` with the contract's own functions, and nothing in `practice-data/` is committed.

Rests on: AGNT1, AGNT8

## Reading FEMC's EML

All FEMC records share one non-standard shape, so the converter reads them in two steps. First it rewrites the record into standard EML:

- the `dataTable`'s `title`, `description`, `purpose` and `coverage` move up to the dataset, and the table gets an `entityName`;
- role-named personnel (`principalInvestigator`, `contentProvider`) become `individualName` plus `role`;
- `publisher`'s inner `metadataProvider` becomes the publisher party itself;
- `measurementType` becomes `measurementScale`, and an `enumeratedDomain` sitting directly on an attribute moves into its scale;
- the misspelled `distibution` becomes `distribution`;
- a coverage with only a begin date gets `end: unknown`.

Then it passes the rewritten record to the unchanged `from_eml`, which maps every standard element to the manifest, project and code lists. FEMC's preferred citation goes in `archive:citation`. For a linked record, the data's URL is taken from the citation's "Available online at:" text, the only place FEMC records it. Anything neither step reads goes on the package's not-imported list.

The converter writes what the record says and nothing more. A description shorter than the core 50 characters stays as it is; coverage keeps the record's dates even where the file name disagrees; a record with no creator gets none. The audit reports each gap.

Rests on: AGNT2, AGNT7

## Columns and files

The file is the truth about its columns. Each real column becomes a field, typed from the file. An EML attribute is matched to a column by exact name, then without regard to case, then by the shapefile's 10-character truncation; the EML's spelling, when it differs, goes in `archive:sourceName`. An attribute with no column is listed as not imported, and a column with no attribute gets a field with no description. The core validator's case-sensitive check is left as it is, since field names are written exactly as the file spells them.

Downloaded files go under `data/` as downloaded, with nothing changed: tidying is Plan 3's later work. A zip is unpacked and not copied again; the aerial survey's shapefile parts become one `vector` resource with `archive:files` and an `archive:attributes` schema naming its `.dbf` columns as the `.dbf` spells them; its CSV (the attribute table without geometry) becomes its own `table` resource, and its XLSX an alternate of the CSV. FEMC's `eml.xml` goes under `original/` as a `file` resource. The not-imported list, one line per element or attribute with the reason, goes in the package's `_build/not-imported.txt`, which the contract treats as outside the package content.

Rests on: AGNT3, AGNT8

## Rights and access

No FEMC record states rights, so rights come from the license each dataset page shows, as recorded in `SOURCES.md` at download:

- a Creative Commons license becomes a license with its SPDX id;
- "Linked - third party determines data license" becomes `archive:rightsStatus: third-party`, with FEMC's words as the statement;
- no license shown becomes `undetermined`, so the package can be audited but not published.

Access follows FEMC's own label for the dataset: Downloadable is `open`, By request is `by-request`, Description only is `description-only`. A linked record is `open`, with a `linked` resource.

Rests on: AGNT4

## The corpus and its order

Ten datasets, converted in this order, each adding one problem the converter has not met yet:

| # | Dataset | What it teaches |
| --- | --- | --- |
| 1 | Ozone Bioindicators | The baseline: a small table. Converted again, since the hand-made package uses a draft format the contract rejects. |
| 2 | Data Rescue Inventory | The record describes 25 columns the file lacks; personal columns; a 21-character description. |
| 3 | IMPROVE fine aerosol | 239 columns, day-first dates, value, uncertainty, detection limit and flag per analyte. |
| 4 | Camels Hump census_data | A linked record whose URL is only in the citation. |
| 5 | Aerial detection survey | A shapefile set, code lists on attributes, an attribute table, renamed columns. |
| 6 | FIA tree-level | 155 MB and 49 undescribed columns. |
| 7 | Vegetation Class Raster | A raster, licensed CC0. |
| 8 | Mount Mansfield Quadrat Images | Photographs, licensed CC BY-NC-SA 4.0. |
| 9 | Development Related Projects with Threatened or Endangered Species | By request, ongoing, protected species: metadata only. |
| 10 | 1991 White clover clones as a biomonitor | Description only: metadata only. |

Datasets 7 to 10 are new. Their EML records are saved from each page's `/eml_xmlview`; datasets 7 and 8 are downloaded through FEMC's public pages (done by the agent at Court's word, through each page's anonymous Download Data form); each gets a row in `SOURCES.md` with the license its page shows and a line in `CHECKSUMS.sha256`. The raster and image files' exact formats are read when they are downloaded, and they map to the contract's existing `raster` and `media` kinds.

Rests on: DCSN1, AGNT5

## FEMC's archive config

`examples/femc/archive.yaml` holds FEMC's config: the publisher (the Forest Ecosystem Monitoring Cooperative), the profiles `core` and `ecology`, and FEMC's six themes as its own project listing names them: air, climate change, forest, soil, water and wildlife. Access is set per package, not per theme. A per-package theme field is Plan 2's follow-up (its PARK5); the converter fills it once it exists.

Rests on: AGNT6

## The audit

Once the ten are converted, `cruise diagnose` runs on each and `cruise audit` over `practice-data/packages/`. Their full output, whose evidence quotes data values, stays under `practice-data/audit/`, which is not committed. This folder's `documents/` gets only the counts the FEMC report needs, with no evidence values: per dataset its errors, warnings, notes, completeness score and the rule ids that fired. Plan 5 makes no contact with FEMC and drafts no request to them: the contact and any bulk-export ask belong to Plan 10b, which takes the audit numbers from here.

Rests on: DCSN2, AGNT9

## Risk and cost

Risk: low. The converter writes only new package folders under `practice-data/packages/` on Court's machine and adds new code under `examples/femc/`; nothing in the core changes and nothing is deployed. A wrong conversion is undone by deleting the package folder and running the converter again. The one thing that must not happen is committing FEMC's data, since `practice-data/` is git-ignored and licenses vary.

Cost: two downloads through FEMC's public pages (the raster and the images), done by the agent at Court's word. No new programs: the converter uses the contract and the standard library.

Rests on: DCSN1, AGNT1

## Left out

- Contacting FEMC, and the bulk-export request: Plan 10b.
- Tidying the data (renaming columns, fixing values, writing `changes.jsonl` steps): `cruise tidy`, a Plan 3 follow-up.
- A generic `cruise package` command: a Plan 3 follow-up. The FEMC converter is not its first draft.
- A per-package theme field (Plan 2's PARK5) and taxonomic coverage (Plan 2's PARK6).
- Code lists published outside a record, such as the FIA database manual's codes: those columns stay `undocumented`.
- Growing the corpus past ten, and any scrape of FEMC's archive.
- Uploading the packages to an archive: Plan 7.

Rests on: DCSN2, AGNT7

## How we'll know it works

- Each of the ten packages passes `cruise diagnose` with no structure error. Quality findings are expected; they are the point.
- Every package's `_build/not-imported.txt` accounts for each element and attribute the converter did not map, so nothing is dropped silently.
- The converter's tests, on invented records written in FEMC's shape (none of FEMC's own records are committed), cover each rewrite and the column matching, and `just check` exits 0.
- `cruise audit` over the ten runs to the end; its full output is under `practice-data/audit/`, and the counts with no evidence values are in this folder's `documents/`.

Rests on: AGNT3, AGNT8, AGNT9
