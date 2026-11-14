<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# FEMC migration and practice corpus (Plan 5)

`research-archive-in-a-box/femc-migration-and-practice-corpus` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans** → Build → Sign off

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

None yet.

## Steps

- STEP1 Download Vegetation Class Raster from FEMC: needs the user
- STEP2 Download Mount Mansfield Quadrat Images from FEMC: needs the user

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
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
