<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Quality rules and local tool (Plan 3)

`research-archive-in-a-box/quality-rules-and-local-tool` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 0 of 4** → Sign off

PLAN1 building · 0 of 4 done

## Pick up next

- **PARK1 Taxonomic coverage field:** The contract has no taxonomic coverage field, so Ozone's 'taxonomic coverage missing' finding can't be checked. Add the field (an edit to the contract) when a profile needs it.
- **PARK2 Grid ids with no grid:** Ozone's HEXAGONNUMBER looks like a location id with no grid described. Spotting that is a judgement call for the agent layer (Plan 9), not a deterministic rule.
- **PARK3 Tidy and package commands:** cruise tidy (proposals into changes.jsonl, originals untouched) and cruise package (build the folder, infer types where the source is silent, checksums, README). Plan it as this folder's next plan once diagnose and audit have been used on real data. Calls AGNT5 and AGNT6 are its starting point.
- **PARK4 Inventory and profile commands:** cruise inventory and cruise profile for a messy folder before it is a package, including how far inventory groups files without an agent (the handoff's open question; the aerial survey zip is the real case: shapefile sidecars plus CSV and XLSX copies under one base name). Plan after tidy and package.
- **PARK5 Species names against ITIS:** Species-name matching against ITIS, with a local snapshot so it works offline (DCSN3 option B), when a dataset with a species-name column arrives.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> Brief: Plan 3 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the quality rules engine and the local tool (Plan 3), generic first. Design the rules from what makes any dataset hard to use, then check them against the sample package from Plan 2 and the hand-made Ozone findings in `practice-data/packages/ozone-bioindicators/datapackage.json` under `archive:quality`. Then plan the commands. Take the open questions with me one at a time.

## Decisions

- **DCSN1 What blocks publishing.** Which findings stop a package from being published, and which only warn? The user chose A: Only required fields and structure block. answered in the terminal: “yes, let's do that”
- **DCSN2 Completeness score.** How is the completeness score calculated and shown? The user chose B: One unweighted percent, with its three parts.
- **DCSN3 Species names offline.** Do we build species-name matching against ITIS now, and if so how does it work offline? The user chose A: Not yet. answered in the terminal: “yes, let's do that”
- **AGNT1 Rules live in cruise.** A cruise.rules module that imports without the CLI, so the backend (Plan 7) and the MCP server (Plan 9) can depend on cruise as a library and run the same rules. The user kept it.
- **AGNT2 Dotted rule ids.** &lt;group>.&lt;what>: package.*, field.*, values.*, beside Plan 2's structure.*. The ecology profile's three placeholders turn out to be generic (any measurement needs a unit, any dated table can fall outside its coverage, any coordinates can be out of range), so they become core rules field.unit-missing, values.dates-outside-coverage and values.coordinates-out-of-range, and ecology.yaml's rules list is emptied. Profiles keep the rules mechanism for real domain rules later. The user kept it.
- **AGNT3 Evidence gets a count.** Both confirmed as drafted, with one addition to Evidence: count (how many rows show it), since a rule like values.placeholder must say '18,104 rows' without listing them. Distinct values, inferred types and years present fit in values. The user kept it.
- **AGNT4 A messy fixture.** A small invented messy fixture package beside the sample, with each value problem planted once and listed in its GAPS.md. The user kept it.
- **AGNT5 Types inferred at packaging.** cruise package and profile infer a type only where the source is silent and record field.type-inferred or field.type-narrower findings then (the second plan), rather than the audit re-guessing later. The user kept it.
- **AGNT6 Tidy proposals outside the package.** In _build/proposals.jsonl, as Change lines with no acceptedBy; accepting one moves it into changes.jsonl and applies it to the tidy table. _build/ is already outside package content. The user kept it.
- **AGNT7 Diagnose and audit first.** Only the rules, cruise diagnose and cruise audit. Tidy, package, inventory and profile are planned later in this folder, once diagnose has been used on real data (follow-ups PARK3 and PARK4). The user kept it.
- **AGNT8 Ozone checked on paper.** The rules are checked against Ozone's 36 hand-made findings on paper (the first take's table). A real diagnose run on Ozone waits on Plan 5 converting it into the contract format. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [What diagnose and audit do](spec.md#what-diagnose-and-audit-do): rests on AGNT7, DCSN1, DCSN2
- [The rules](spec.md#the-rules): rests on AGNT2, DCSN1, DCSN3
- [What blocks publishing](spec.md#what-blocks-publishing): rests on DCSN1
- [The completeness score](spec.md#the-completeness-score): rests on DCSN2
- [How the rules are built](spec.md#how-the-rules-are-built): rests on AGNT1, AGNT2
- [Changes to the contract](spec.md#changes-to-the-contract): rests on AGNT2, AGNT3, DCSN2
- [Test data](spec.md#test-data): rests on AGNT4, AGNT8
- [Left out](spec.md#left-out): rests on AGNT5, AGNT6, AGNT7, DCSN1, DCSN3
- [How we'll know it works](spec.md#how-well-know-it-works): rests on AGNT4, AGNT8

## Plans

- [PLAN1](plans/1-rules-diagnose-and-audit.md) The rules, cruise diagnose and cruise audit: building · 0 of 4 done
  - TASK1 Task 1: Contract edits: not started
  - TASK2 Task 2: Rules engine, package and column rules, cruise diagnose: not started
  - TASK3 Task 3: The messy test package and the value rules: not started
  - TASK4 Task 4: cruise audit: not started

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
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
