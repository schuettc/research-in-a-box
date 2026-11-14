<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Ingest, review and access workflows (Plan 7)

`research-archive-in-a-box/ingest-review-and-access-workflows` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans · 1 to write** → Build → Sign off

PLAN1 can be written now

## Pick up next

- **PARK1 By-request access:** A small durable function that emails the data owner and waits on their callback, then issues a short-lived link. A later plan in this folder.
- **PARK2 Takedown and access changes:** What takedown means when the bucket keeps every object version, and moving a dataset between open/ and restricted/ (its /data URL changes). A later plan in this folder.
- **PARK3 DOIs through DataCite:** The optional DOI module: the config setting, the credentials parameter, minting one DOI per version through DataCite's REST API, tested against DataCite's test environment. A later plan in this folder.
- **PARK4 Previews and spatial extent:** Derive data previews and the spatial extent at publish.
- **PARK5 Extension checks from config:** Extra check functions listed in the archive config, run in the check step.
- **PARK6 In-place metadata edits:** A metadata-only change applied to the current version, appended to archive:metadataHistory, rewriting datapackage.json, README.md and checksums.sha256.
- **PARK8 Contributor email:** Email contributors on each decision through SES, once the archive's SES is out of the sandbox.
- **PARK9 Multipart uploads:** Multipart presigned uploads for files over 5 GB.
- **PARK10 Creating projects:** Create and edit project records at projects/&lt;id>/project.json.
- **PARK11 Withdrawing a submission:** Let a contributor withdraw a submission before it is decided.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 2, folder 8da653f233f9, Plan 3, the quality rules and local tool, and Plan 4, the archive infrastructure.)
> 
> Brief: Plan 7 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the ingest pipeline and the review and access workflows (Plan 7). It is one Lambda durable function in Python with a callback wait for curator review. That is decided. Plan the steps, the review policy an admin controls, and the request-changes loop. Take the open questions with me one at a time.

## Decisions

- **DCSN1 Review policy at first.** What should the review policy an admin controls hold in the first plan? The user chose C: The full policy from the handoff.
- **DCSN2 Telling people.** How do curators learn that a submission is waiting for them (including reminders and their named-reviewer assignments), and contributors learn that it was decided? The user chose B: A curators' topic, targeted per reviewer; contributors check status.
- **DCSN3 Malware scanning.** Should the first plan scan uploads for malware before they can be published? The user chose B: GuardDuty Malware Protection on the staging bucket.
- **AGNT1 Plan 7 owns submission endpoints.** Plan 7 builds everything under /api/submissions: create a submission and get upload links, submit, the queue, one submission's status and events, the curator's decision and the review-policy setting. Plan 6 keeps every read of the catalog. Publish calls Plan 6's catalog-file writer. If that writer isn't built yet, publish writes the catalog items now and the call is added when the writer lands. That is build order, not a second path. The user kept it.
- **AGNT2 Presigned PUT per file.** Create-submission returns one presigned PUT URL per file under staging/incoming/&lt;submissionId>/&lt;round>/. A single PUT holds up to 5 GB. Multipart upload is a follow-up for when a real file goes over that. The user kept it.
- **AGNT3 Held packages outlive staging expiry.** The staging lifecycle rule applies only to incoming/. Once the checks pass, a step copies the round into staging/held/&lt;submissionId>/, which never expires. Publish and reject delete it. Plan 7 changes Plan 4's lifecycle rule in storage.ts and keeps its synth test true. The user kept it.
- **AGNT4 Stale means alert and keep waiting.** The submission is marked stale and the alert goes out (by DCSN2). The function then waits again with the same timeout, so the submission stays in the queue until someone decides it. The user kept it.
- **AGNT5 Resubmit wait ends as abandoned.** 30 days. After that the submission ends as abandoned, its files are deleted, and the event is recorded. The user kept it.
- **AGNT6 New version by manifest id.** If the manifest's id matches a published dataset, the submission is that dataset's next version, and only the dataset's original submitter or a curator may submit it. The curator sees that it is a new version of an existing dataset. With no id, the archive gives it one at publish, made from the title plus a short random suffix. The user kept it.
- **AGNT7 Self-review allowed, logged.** Yes, and the audit log records it. Where the policy asks for two curators, the two approvals must come from two different curators, and the submitter can be at most one of them. The user kept it.
- **AGNT8 Project records location.** projects/&lt;projectId>/project.json. The first plan doesn't create projects: a package's archive:project is kept in the manifest and the catalog item as it is. Creating and editing projects is a follow-up. This location goes in the decision log, for Plan 4's PARK6 and Plan 6's project reads. The user kept it.
- **AGNT9 Static dataset page.** site/datasets/&lt;id>/index.html, served at /datasets/&lt;id>. It holds the title, description, citation, version and file links, with the schema.org JSON-LD in the head, and reads on its own. The CloudFront site function sends /datasets/&lt;id> to that file. How the web app takes over from the page is Plan 8's to add, by rebuilding the page from its template. The user kept it.
- **AGNT10 Publish writes the active catalog.** The active one, named by the SSM parameter. Reindex catch-up for packages published during a run stays Plan 4's PARK5, and a reindex stays something an admin runs while publishing is quiet. The user kept it.
- **AGNT11 Identifier is the stable URL.** https://&lt;domain>/datasets/&lt;id>/v&lt;version>, plus the publisher from the config and the publication year. DOIs are a later plan. The user kept it.
- **AGNT12 Policy is a contract model.** A ReviewPolicy Pydantic model in archive_contract, so the web app gets it through the generated JSON Schema. It is stored as the Settings item `review-policy`, read once per submission when it enters review, and edited with GET and PUT /api/submissions/policy by the admin group. Until Plan 8's admin screen exists, the admin edits it through that endpoint. With no item set, the default is review required, any curator, a 14-day stale mark and no reminders. The user kept it.
- **AGNT13 Rules match fixed facts.** An ordered list of rules, where the first match wins. Each rule matches on a fixed set of facts about the submission: submitter (user ids or the curator group), new dataset or new version, access level, and theme. The outcome is skip review, one curator, or two curators. Named reviewers are a theme-to-curators map: with one, that curator is asked first, and any curator may still decide. Reminders are a list of days before the stale mark. A submission records the rule that matched. The user kept it.
- **AGNT14 Config reaches Lambdas via SSM.** At synth, the CDK app writes the validated config as JSON to a standard SSM parameter, /research-archive/&lt;stage>/archive-config. Synth fails if the JSON is over 4 KB, the standard tier's limit. The check step reads the parameter once per round, inside a step. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The path](spec.md#the-path): rests on DCSN1, AGNT4, AGNT5
- [Submissions and upload](spec.md#submissions-and-upload): rests on AGNT1, AGNT2, AGNT3, AGNT6
- [Scanning and checks](spec.md#scanning-and-checks): rests on DCSN3, AGNT14
- [The review policy](spec.md#the-review-policy): rests on DCSN1, AGNT7, AGNT12, AGNT13
- [Review and the request-changes loop](spec.md#review-and-the-request-changes-loop): rests on DCSN1, AGNT4, AGNT5, AGNT7
- [Notifications](spec.md#notifications): rests on DCSN2
- [Publish](spec.md#publish): rests on AGNT1, AGNT6, AGNT8, AGNT9, AGNT10, AGNT11
- [The audit log](spec.md#the-audit-log): rests on AGNT7, AGNT13
- [The API and the infrastructure](spec.md#the-api-and-the-infrastructure): rests on AGNT1, AGNT3, AGNT9, AGNT12, AGNT14, DCSN2, DCSN3
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN3, AGNT3
- [Left out](spec.md#left-out): rests on AGNT1, AGNT8, DCSN2
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, DCSN3, AGNT13

## Plans

- PLAN1 Submit review publish: can be written now

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
