<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Package format and contract (Plan 2)

`research-archive-in-a-box/generic-package-format-and-contract` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 12 of 15** → Sign off

PLAN1 built · PLAN2 built · PLAN3 building · 0 of 3 done

## Pick up next

- **PARK1 Protect main, allow auto-merge:** main has no branch protection and auto-merge is off for the repo: PR #1 merged before CI ran, and PR #2 had to be merged by hand after CI. Require the python and typescript checks on main and turn on auto-merge in the repo settings.
- **PARK2 EML code label delimiter:** The EML export writes a code's definition as 'label: description' and the import splits on ': ', so a label containing ': ' changes meaning on round trip. Pick an unambiguous encoding.
- **PARK3 schema.org rights statuses:** The schema.org export reads only licenses and ignores archive:rightsStatus (public-domain, third-party, all-rights-reserved). Map statuses where schema.org has a form.

## What was asked

> i think we got started incorrectly here.
> 
> the goal here is to build a research in abox.  we'll use the FEMC data as an example, but we want to build this generically.  once we have the correct format, we can work on a process to migrate FEMC data
> 
> [...]
> 
> yes, let's do that.  we can delete that plan 2 and restart fresh
> 
> (Brief: Plan 2 in docs/planning-handoff.md, revised 2026-11-12 to be generic first. Read the handoff, including the Decision log, before continuing.)

## Decisions

- **DCSN1 Packages without a license.** What does a package need on rights before the pipeline will publish it? The user chose A: Publish needs a license or a stated rights status.
- **DCSN2 Column names.** Do tidy tables keep the source's column names, or rename them to a house style? The user chose C: Keep by default, rename as a recorded change.
- **DCSN3 Where code lists live.** Where does a package keep the list of what each code in a column means? The user chose B: A small code-list table, linked by foreign key.
- **DCSN4 Version numbers.** What makes a new version of a package, and how are versions numbered? The user chose B: File changes make a version, metadata edits in place.
- **DCSN5 Projects and their packages.** How does a project record relate to the packages under it? The user chose A: Its own small record, packages point to it.
- **DCSN6 Multi-file resources.** How does a package describe something made of several files that only work together, such as a shapefile set? The user chose A: One resource, member files listed.
- **DCSN7 Gaps the paper test found.** The paper test found eight things the format can't express. Which do we add to the format now? The user chose B: Add all eight.
- **AGNT1 Resource kinds vocabulary.** table, vector, raster, document, media, file and linked. Code-list tables are tables. A resource with no kind is read as file. The user kept it.
- **AGNT2 Same data, several formats.** The copy is its own resource with archive:alternateOf: &lt;name of the primary resource>. Only the primary carries the schema. The user kept it.
- **AGNT3 Linked resources.** A resource with archive:kind linked whose path is the remote URL (allowed by Frictionless), with no hash or bytes. Compatibility tests run frictionless with remote fetching off. The user kept it.
- **AGNT4 Access levels per package.** One level per package: open, restricted, by-request or description-only. Unpublished is a state of the package, not an access level. The user kept it.
- **AGNT5 Column sensitivity flags.** archive:sensitivity on a field, one of personal, sensitive-location or confidential. No flag means not sensitive. The user kept it.
- **AGNT6 Profiles as data files.** As a data file in the contract (YAML, read into a Pydantic Profile model) listing the fields it promotes to required, its vocabularies and the ids of the rules it switches on. Rule code lives in Plan 3. The user kept it.
- **AGNT7 EML versions.** Export EML 2.2.0. Import standard EML 2.1.1 and 2.2.0. The user kept it.
- **AGNT8 Legacy identifiers as a list.** archive:legacyIdentifiers as a list of {scheme, value}, such as {scheme: eml-package-id, value: knb-lter-xyz.12.3}. The user kept it.
- **AGNT9 Sample package subject.** A small stream temperature study at invented sites, licensed CC-BY-4.0. It has a logger table with a code-list table, a site shapefile set, a small raster, a methods document, a site photo, the table again as XLSX, a linked resource and ongoing coverage. Its seeded gaps are listed in its README. The user kept it.
- **AGNT10 Change log and findings shapes.** The contract defines both models (Change and Finding), drafted in this spec. Plan 3 has no planning folder yet, so it confirms or changes them when its session starts, and this folder sends it a diazo note then. A change from Plan 3 is an edit to the contract, not a reopened decision here. The user kept it.
- **AGNT11 Contract module layout.** One module per record under `src/archive_contract/`: `manifest.py` (package and its archive: additions), `resources.py`, `fields.py`, `rights.py`, `project.py`, `changes.py`, `findings.py`, `profile.py`, `config.py`; `profiles/core.yaml` and `profiles/ecology.yaml`; `validate.py` (structural validation); `schema.py` (JSON Schema generation, from Plan 1); `exports/` (`eml.py`, `datacite.py`, `schemaorg.py`, `readme.py`); `imports/eml.py`. The user kept it.
- **AGNT12 Branch from local main.** The local main at 7789d37: origin/main plus one commit of planning records, which the PR then carries. The user kept it.
- **AGNT13 Drop the DataCite schema.** Remove the vendored DataCite JSON Schema. A test checks DataCite 4.x's mandatory properties and their shapes instead; Plan 7 confirms real acceptance when it mints test DOIs through DataCite's API. The user kept it.
- **AGNT14 Only DataCite refuses rights.** No: only DataCite refuses, as the plan says. EML and schema.org also serve previews and hand-offs before publishing; Plan 7's publish check is where unpublishable rights are stopped. The user kept it.
- **PRIN1** FEMC is only the test afterwards. It is never the example on a card or the reason for a design choice; examples and reasons come from the standards and from any research group's data.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The package folder](spec.md#the-package-folder): rests on AGNT1, AGNT11
- [The manifest's fields](spec.md#the-manifests-fields): rests on AGNT8
- [Rights](spec.md#rights): rests on DCSN1
- [Resources and their kinds](spec.md#resources-and-their-kinds): rests on AGNT1, AGNT2, AGNT3, DCSN6
- [Columns](spec.md#columns): rests on DCSN2, DCSN3, AGNT5
- [Versions and identifiers](spec.md#versions-and-identifiers): rests on DCSN4
- [Projects](spec.md#projects): rests on DCSN5
- [Access levels](spec.md#access-levels): rests on AGNT4
- [Profiles and the archive config](spec.md#profiles-and-the-archive-config): rests on AGNT6
- [The change log and findings](spec.md#the-change-log-and-findings): rests on AGNT10, DCSN2
- [Exports and import](spec.md#exports-and-import): rests on AGNT7, DCSN3, DCSN5
- [The contract package](spec.md#the-contract-package): rests on AGNT11
- [The sample package](spec.md#the-sample-package): rests on AGNT9, DCSN3, DCSN6
- [Fields the paper test added](spec.md#fields-the-paper-test-added): rests on DCSN7
- [Risk and cost](spec.md#risk-and-cost): rests on AGNT11
- [Left out](spec.md#left-out): rests on DCSN1, AGNT4
- [How we'll know it works](spec.md#how-well-know-it-works): rests on AGNT7, AGNT9

## Plans

- [PLAN1](plans/1-contract-models-and-sample.md) The contract models, validation, schema and sample package: built
  - TASK1 Task 1: Resource, field and rights models: done. 6c1fac9 + 03cf2b6 (null extras kept, type/kind enforced) · just check exit 0
  - TASK2 Task 2: Manifest and project models: done. a6d3803 + 03cf2b6 (coverage needs end or ongoing) · just check exit 0
  - TASK3 Task 3: Change, Finding, Profile and ArchiveConfig: done. 6d94716 · contract tests exit 0 · just check exit 0 · uv lock --check exit 0
  - TASK4 Task 4: Structural validation: done. 37b3cf9 + 03cf2b6 (symlinks refused, checksums all but _build, hash allowlist) · 158 tests pass
  - TASK5 Task 5: The real JSON Schema: done. 0a38fa1 · just schema exit 0 · just check (with drift check) exit 0
  - TASK6 Task 6: The sample package: done. 1064ecf · merged in PR #1 as c7ba8fc · CI run 43449582602 on main success (python, typescript)
- [PLAN2](plans/2-exports-import-and-paper-test.md) Exports, EML import and the FEMC paper test: built
  - TASK7 Task 1: README export: done. 3714348 · README generated from the manifest · just check exit 0
  - TASK8 Task 2: DataCite export: done. 7fd9c1d · validates against DataCite's JSON Schema · refuses undetermined or missing rights
  - TASK9 Task 3: schema.org export: done. bec8b93 · Google's required fields · ongoing as start/..
  - TASK10 Task 4: EML 2.2.0 export: done. da9963e · validates against the EML 2.2.0 XSD (a broken document fails)
  - TASK11 Task 5: EML import: done. 7b692fd + a204e7a · reads EML 2.1.1 and 2.2.0, lists what it skips · sample round-trips
  - TASK12 Task 6: The FEMC paper test: done. c2c058d + 0906808 (review fixes) · 198 tests · PR #3 CI green (runs 43470879322, 43470887680) · merged as 90e1a0b
- [PLAN3](plans/3-fields-from-the-paper-test.md) The eight fields from the paper test: building · 0 of 3 done
  - TASK13 Task 1: The eight fields on the models: not started
  - TASK14 Task 2: Validator check for attribute tables: not started
  - TASK15 Task 3: Exports, import and the sample package: not started

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |

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
