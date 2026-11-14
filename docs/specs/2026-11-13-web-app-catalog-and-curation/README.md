<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Web app (Plan 8)

`research-archive-in-a-box/web-app-catalog-and-curation` · repo `research-archive-in-a-box`

**Planned** since 2026-11-13: waits for the user's Start planning.

**Start** → Understanding → Decisions → Spec → Plans → Build → Sign off

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 6, the API and search, and Plan 7, the ingest pipeline, for the submission screens.)
> 
> Brief: Plan 8 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the web app (Plan 8): a static React with Vite app on S3 and CloudFront, backed by the API. Start with the reader's flow from search to dataset page to download, since findability is the main problem we set out to fix. The generated `README.md` in `practice-data/packages/ozone-bioindicators/` shows what a dataset page has to present.

## Decisions

None yet.

## Spec

Not printed yet.

## Plans

None yet.

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
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
