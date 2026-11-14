<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# The FEMC report (Plan 10b)

`research-archive-in-a-box/femc-findings-report` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 0 of 4** → Sign off

PLAN1 building · 0 of 4 done

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

- [PLAN1](plans/1-write-the-femc-report.md) Write the FEMC report: building · 0 of 4 done
  - TASK1 Task 1: The evidence notes: not started
  - TASK2 Task 2: The Ozone after-package: not started
  - TASK3 Task 3: The report: not started
  - TASK4 Task 4: Review and the PDF: not started

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
