<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# FEMC migration and practice corpus (Plan 5)

`research-archive-in-a-box/femc-migration-and-practice-corpus` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → ✓ Build → ✓ Sign off

Signed off 2026-11-13 22:59.

PLAN1 built

## Wrap-up

### Any dataset downloaded from FEMC's archive can now be turned into a package and audited.

#### How it works now

Download a dataset from FEMC's public archive with its EML record, add its row to `practice-data/femc/SOURCES.md`, and run `uv run femc convert <dataset-folder> <out-folder>`. The converter reads FEMC's non-standard EML through the shared importer, takes the columns from the real files, sets rights and access from what FEMC's page shows, and writes a package the contract accepts, with `_build/not-imported.txt` listing everything it could not carry over and `_build/project.json` keeping the project record. `cruise diagnose` and `cruise audit --config examples/femc/archive.yaml` then show what each dataset needs before it could be published. Ten FEMC datasets are converted this way on your machine: tables, a shapefile set, a raster, photographs, a linked record, and records FEMC shares only on request or holds only as a description.

#### Results

- The `femc` converter and FEMC's archive config in `examples/femc/`, with the shared contract and cruise unchanged: PLAN1, schuettc/research-in-a-box#23
- All ten practice datasets converted with no structure findings; the counts for the FEMC report (errors, warnings, notes, score and rules fired, with no data values) in `documents/femc-audit-counts.md`: PLAN1, schuettc/research-in-a-box#23
- The approved spec and three Decision log lines in `docs/planning-handoff.md` (the FEMC contact moves to Plan 10b, the converter's place, the ten-dataset corpus): PLAN1, schuettc/research-in-a-box#18

#### Different from the plan

The four new datasets were downloaded by the agent at your word rather than by hand. The final review found that each project's description and people were used only in the README, so the converter now keeps the project record in `_build/project.json`. CI's formatting check failed once on a test fixture that the local Python checks don't cover, and was fixed in the same PR.

## Pick up next

- **PARK1 Unzipped raster folders:** femc convert finds an ArcInfo grid only inside a zip; a grid delivered as an unpacked folder is ignored. FEMC delivers zips, so no real case yet (final review, finding 2).
- **PARK2 Keyword thesaurus kept:** The project keywordSet rewrite keeps only keyword text; a keywordThesaurus or other child would be dropped without a not-imported line. None of the ten FEMC records has one (final review, finding 3).
- **PARK3 Where project records live:** Each converted package keeps its project record in _build/project.json. Plan 7 has decided project records live at projects/&lt;projectId>/project.json in the archive bucket (its AGNT8, in the handoff Decision log); when FEMC packages are first submitted through Plan 7, write their project records in that layout.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 2, folder 8da653f233f9, and Plan 3, the quality rules and local tool.)
> 
> Brief: Plan 5 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md` and `practice-data/femc/SOURCES.md`. Plan the conversion of the FEMC practice corpus (Plan 5). One dataset is already converted by hand. Plan the other five in order of what each will teach us, and propose which datasets to add to reach 10 to 20.

## Decisions

- **DCSN1 Datasets to add.** Which FEMC datasets should we add to the six, to reach 10 to 20? The user chose A: Four, one per missing shape (reach 10).
- **DCSN2 Approaching the FEMC contact.** When should we approach your FEMC contact, and with what? The user chose C: Not in this plan.
- **AGNT1 Converter location.** `examples/femc/`: FEMC's `archive.yaml` and a small uv workspace package `femc` (src layout, its own tests), so ruff, mypy and pytest in `just check` cover it. It depends on archive-contract only. The user kept it.
- **AGNT2 Read FEMC through from_eml.** It rewrites FEMC's shape into standard EML (title and description up from the dataTable, entityName from the table, role-named personnel to individualName plus role, measurementType to measurementScale, distibution to distribution, enumeratedDomain into its scale) and passes the result to the unchanged `from_eml`. The user kept it.
- **AGNT3 Columns from the file.** The file's. Each real column becomes a field; an EML attribute is matched to it by exact name, then case-insensitively, then by the shapefile's 10-character truncation, and the EML's spelling goes in `archive:sourceName`. Described columns not in the file are listed as not imported. The user kept it.
- **AGNT4 Rights from SOURCES.md.** From the license each dataset page shows, as recorded in SOURCES.md: a Creative Commons license becomes a license, 'Linked - third party determines data license' becomes `third-party` with FEMC's words as the statement, and no license shown becomes `undetermined`. The user kept it.
- **AGNT5 Conversion order.** 1 Ozone (small, the baseline). 2 Data Rescue (EML lists columns the file lacks, personal columns, short description). 3 IMPROVE (239 columns, day-first dates, value/uncertainty/flag groups). 4 Camels Hump (linked, URL only in the citation). 5 Aerial survey (shapefile set, code lists, attribute table, renamed columns). 6 FIA (155 MB, 49 undescribed columns). Then the additions DCSN1 settles. The user kept it.
- **AGNT6 Themes in the config.** publisher, profiles [core, ecology] and FEMC's six themes as its own project listing names them (air, climate change, forest, soil, water, wildlife). Access is set per dataset on each package (`archive:access`), since FEMC sets it per dataset, not per theme. A per-package theme field is Plan 2's follow-up (its PARK5, archive:themes checked against the config's themes); when it lands, the converter can fill it. The user kept it.
- **AGNT7 Gaps stay gaps.** Writes what the record says and nothing more: a 21-character description stays, coverage keeps the record's dates (with `end: unknown` where only a start is given), and the citation goes in `archive:citation`. cruise reports the gaps. The user kept it.
- **AGNT8 Files and the not-imported list.** Downloaded files go under data/ as downloaded (the aerial survey's zip unpacked, nothing else changed, since tidying is Plan 3's later work). FEMC's eml.xml goes under original/ as a file resource, so the source record travels with the package. The zip itself isn't copied again, since every member sits unchanged in data/ and SOURCES.md checksums the zip. The not-imported list goes in the package's _build/not-imported.txt, which the contract treats as outside the package content. The user kept it.
- **AGNT9 Audit counts only in public.** Only counts with no evidence values: per dataset its errors, warnings, notes, completeness score and the rule ids that fired. The full diagnose and audit output stays under practice-data/audit/, which is git-ignored. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The converter](spec.md#the-converter): rests on AGNT1, AGNT8
- [Reading FEMC's EML](spec.md#reading-femcs-eml): rests on AGNT2, AGNT7
- [Columns and files](spec.md#columns-and-files): rests on AGNT3, AGNT8
- [Rights and access](spec.md#rights-and-access): rests on AGNT4
- [The corpus and its order](spec.md#the-corpus-and-its-order): rests on DCSN1, AGNT5
- [FEMC's archive config](spec.md#femcs-archive-config): rests on AGNT6
- [The audit](spec.md#the-audit): rests on DCSN2, AGNT9
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN1, AGNT1
- [Left out](spec.md#left-out): rests on DCSN2, AGNT7
- [How we'll know it works](spec.md#how-well-know-it-works): rests on AGNT3, AGNT8, AGNT9

## Plans

- [PLAN1](plans/1-femc-converter-and-corpus.md) The FEMC converter and the ten-dataset corpus: built
  - TASK1 Task 1: The femc package and FEMC's config: done. 6ef20e7; just check-python exit 0; femc --help exit 0
  - TASK2 Task 2: Reading FEMC's EML: done. e703a5f; 16 EML tests; just check-python exit 0
  - TASK3 Task 3: Writing a package: done. c3c3944; 10 convert tests; just check-python exit 0 (370 passed)
  - TASK4 Task 4: Convert the ten: done. All ten converted (exit 0), 0 structure findings each (jq check exit 0); no converter fix needed; old Ozone moved to _draft-ozone-bioindicators
  - TASK5 Task 5: The audit and its counts: done. cruise audit exit 0, 10 packages (jq check true); counts in documents/femc-audit-counts.md, no evidence values; full output in practice-data/audit/

## Steps

- STEP1 Download Vegetation Class Raster from FEMC: done
- STEP2 Download Mount Mansfield Quadrat Images from FEMC: done

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `wrap-up.md` | the agent, header by diazo | What was built, how it works now, and what went differently from the plan. |
| `plans/` | the agent, header by diazo | One file per plan. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
| `documents/` | the agent and the user | Every other file the plan holds, of any type: CSV, PDF, Markdown, transcripts. |
| `diagrams/` | diazo | The drawn picture (SVG) of each mermaid diagram in the folder. |

## Ids

Every card has an id: its prefix, then a number.

- `DCSN`: a decision the user makes
- `AGNT`: a call the agent made, which the user may reverse
- `PRIN`: a principle
- `PARK`: a follow-up, for later
- `STEP`: a step only the user can do
- `ASK`: an ask of someone other than the user
- `PLAN`: a plan
- `TASK`: a task of a plan

The full record is `decisions.json`; its schema is [schema/record.json](https://github.com/subaud-tools/diazo/blob/main/schema/record.json).
