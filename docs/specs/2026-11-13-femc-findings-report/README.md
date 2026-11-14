<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# The FEMC report (Plan 10b)

`research-archive-in-a-box/femc-findings-report` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → ✓ Build → ✓ Sign off

Signed off 2026-11-14 10:04.

PLAN1 built

## Wrap-up

### The FEMC report is written and ready for Court to send.

#### How it works now

The report sits on Court's machine in `practice-data/report/`: `femc-report.pdf` to attach to an email, `femc-report.md` to edit, `notes.md` with the source and command behind every claim, and `ozone-after/`, the Ozone package filled only from FEMC's own pages. It covers the handoff's eight sections, from what FEMC does well through the findings in ten datasets to the bulk-export request in section 8. Nothing from it is committed to the public repo. To change it, edit the Markdown and re-render with pandoc and Chrome as the sign-off card describes.

#### Results

- The report, its evidence notes and the Ozone before-and-after, uncommitted in practice-data/report/: PLAN1
- The approved spec and plan: PLAN1, schuettc/research-in-a-box#36

#### Different from the plan

The claim review ran on Claude Opus rather than the other model family, because Codex had reached its usage limit; it found one overstated claim and several broader sentences, all fixed. Plan 6's search numbers aren't quoted, since its record of the searches isn't on main yet. Filling Ozone from FEMC's own sources moved its score only from 76 to 77, and the report makes that its section 4 point.

## Pick up next

- **PARK1 Fill the contact's name:** Replace [CONTACT NAME] in practice-data/report/femc-report.md and re-render the PDF before sending.
- **PARK2 Wire EML and DataCite into publish:** archive_contract.exports has EML and DataCite writers with no caller; publish (Plan 7) could write them beside each version so the report's section 5 row becomes true. Belongs to Plan 7's owner.
- **PARK3 Quote Plan 6's search test:** Once Plan 6's record of its 22 searches is on main, the Camels Hump finding can cite it.
- **PARK4 Audit the whole archive:** If FEMC agrees to a bulk export, run the same audit over every record and send them the results.
- **PARK5 Commit the report after FEMC sees it:** Once FEMC has read it and agrees, a version of the report could be committed.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 5, the FEMC migration and its audit numbers.)
> 
> Brief: Plan 10b in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the FEMC report (Plan 10b). Sections 1, 2 and 7 can be drafted from what we already know. Plan what each section needs, which findings we can already support with a specific record, and which need the audit tool first.

## Decisions

- **DCSN1 Where the draft lives.** Where should the report's drafts and the finished report live, given the repo is public? The user chose A: On your machine, beside the data.
- **DCSN2 The before-and-after dataset.** For section 4, how should we show a dataset 'after', when the local tool can't clean data yet and we may not invent what only FEMC knows? The user chose A: After = filled only from FEMC's own public sources.
- **AGNT1 Addressed to the contact.** Written to your FEMC contact by name, in a form they can forward to archive staff and partners unchanged. The user kept it.
- **AGNT2 Markdown source, PDF to send.** A Markdown source that renders to a plain PDF, which you attach to an email. The user kept it.
- **AGNT3 People on the project, said precisely.** 'None of the ten dataset records names a creator; people are recorded on the parent project, under FEMC's own role tags, so EML readers don't see them as the dataset's authors.'. The user kept it.
- **AGNT4 Recheck borrowed numbers.** Quote them only after rereading Plan 6's own record of the 22 searches, cited by file. The user kept it.
- **AGNT5 Cite records by their page.** Each finding links the dataset's FEMC page (from SOURCES.md), with the field named and the EML record's page id in brackets where a field-level check needs it. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The report, section by section](spec.md#the-report-section-by-section): rests on AGNT3, AGNT4, AGNT5
- [The Ozone before-and-after](spec.md#the-ozone-before-and-after): rests on DCSN2, DCSN1
- [Where it lives and how it reaches FEMC](spec.md#where-it-lives-and-how-it-reaches-femc): rests on DCSN1, AGNT1, AGNT2, AGNT4, AGNT5
- [Left out](spec.md#left-out): rests on DCSN1, AGNT2
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, AGNT4, AGNT5

## Plans

- [PLAN1](plans/1-write-the-femc-report.md) Write the FEMC report: built
  - TASK1 Task 1: The evidence notes: done. practice-data/report/notes.md: six findings and six strengths traced; audit re-run (exit 0) matches Plan 5 on all ten rows and rule totals; Plan 6's search record not on main, so not quoted; aerial survey count taken from the converter (29), not the handoff (14)
  - TASK2 Task 2: The Ozone after-package: done. practice-data/report/ozone-after/: creators filled from FEMC's citation and project record (2 changes.jsonl lines); diagnose exit 0 with no structure findings; audit errors 3 → 2, score 76 → 77; the remaining gaps (methods, coverage, 14 units, 7 descriptions, species code list) listed in notes.md
  - TASK3 Task 3: The report: done. practice-data/report/femc-report.md: eight sections (grep exit 0, 8), about 2,400 words; claims checked against notes.md and main (Plan 7 ingest and pages, Plan 6 usage form and download counts); three unsupported phrases cut on my own pass; git status shows nothing from practice-data
  - TASK4 Task 4: Review and the PDF: done. Review by claude-bridge/claude-opus-5-5 (Codex at its usage limit): 9 of 10 claims held, 1 overstated (EML/DataCite export at publish); that row, the Camels Hump search claim, the units count (3 are ID columns), the structure-check and config sentences, the cost line and 8 tone points fixed; notes.md corrected (researchProject in 3 records). pandoc exit 0, Chrome print exit 0: femc-report.pdf, 7 pages, checked by eye; git status clean

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
