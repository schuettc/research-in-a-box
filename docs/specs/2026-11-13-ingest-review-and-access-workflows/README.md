<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Ingest, review and access workflows (Plan 7)

`research-archive-in-a-box/ingest-review-and-access-workflows` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 7 of 9** → Sign off

PLAN1 built · PLAN2 building · 0 of 2 done

## Wrap-up

### A contributor can now submit a package, a curator can review it, and an approved package is published and findable.

#### How it works now

A contributor creates a submission, uploads the package with links that S3 checks against each file's checksum, and submits it. GuardDuty scans every file, cruise runs the structure and quality checks, and a package with a blocking error goes straight back to the contributor with its findings. Under the review policy an admin sets at run time (review on or off, skip rules, two-curator cases, named reviewers per theme, reminders and a stale mark), a curator approves, rejects or requests changes, and a request for changes loops back through the checks when the contributor resubmits. An approved package gets its version, a checksummed copy under the archive's open or restricted prefix, its catalog entries and its own dataset page at `/datasets/<id>`. Curators get an email when a submission waits for them, and every step is an event in the audit log.

#### Results

- The review policy model and the `archive:published` field in the contract: PLAN1, research-in-a-box#21
- The archive-config parameter and the shared config reader, split out early for Plan 6: PLAN1, research-in-a-box#28
- The submissions API, the durable ingest, publish, dataset pages, the Ingest construct and `just ingest-e2e`: PLAN1, research-in-a-box#29

#### Different from the plan

You chose not to wait a day for the reminder email (DCSN4), so the reminder never fired on AWS; it is covered by unit tests only (PARK17). The final review ran on Claude Opus, not OpenAI, because OpenAI's usage limit was reached. The test stage was deployed and run a second time after Plan 6's first plan landed underneath, and its first teardown got stuck on a waiting submission (PARK19).

## Pick up next

- **PARK1 By-request access:** A small durable function that emails the data owner and waits on their callback, then issues a short-lived link. A later plan in this folder.
- **PARK2 Takedown and access changes:** What takedown means when the bucket keeps every object version, and moving a dataset between open/ and restricted/ (its /data URL changes). A later plan in this folder.
- **PARK3 DOIs through DataCite:** The optional DOI module: the config setting, the credentials parameter, minting one DOI per version through DataCite's REST API (from the contract's DataCite export, which publish doesn't call yet), tested against DataCite's test environment. A later plan in this folder.
- **PARK4 Previews and spatial extent:** Derive data previews and the spatial extent at publish.
- **PARK5 Extension checks from config:** Extra check functions listed in the archive config, run in the check step.
- **PARK6 In-place metadata edits:** A metadata-only change applied to the current version, appended to archive:metadataHistory, rewriting datapackage.json, README.md and checksums.sha256.
- **PARK8 Contributor email:** Email contributors on each decision through SES, once the archive's SES is out of the sandbox.
- **PARK9 Multipart uploads:** Multipart presigned uploads for files over 5 GB.
- **PARK10 Creating projects:** Create and edit project records at projects/&lt;id>/project.json.
- **PARK11 Withdrawing a submission:** Let a contributor withdraw a submission before it is decided.
- **PARK12 Duplicate events on step retry:** Write each step's audit event after its SNS call, so a retried step doesn't record the same event twice (final review M1).
- **PARK13 Hide callbackId in responses:** Leave callbackId out of GET /api/submissions responses (final review M3).
- **PARK14 Partial META after failed publish:** A publish that fails after claiming its version leaves a partial dataset item (no title) in the catalog until a reindex. Clean the claim up in the failure path.
- **PARK15 Curator file links route:** GET /api/submissions/{id}/files, for the curator group: five-minute presigned GETs for the current round's listed files under held/&lt;id>/, answered only while in-review or publishing (409 otherwise). Needed by Plan 9's review skill and Plan 8's curator screen. A small task after PR #29 merges, with a Decision log row. The same task moves the page write into pages.write_page (PARK16). From the coordinating session, thread 964.
- **PARK16 Shared page writer for reindex:** Move the dataset page's S3 write out of ingest's durable _page step into pages.write_page(s3, bucket, html, dataset_id), which the _page step then calls. Plan 8's reindex calls only that and never edits ingest. render_page's signature stays stable. Built in the same task as PARK15, at the coordinating session's request.
- **PARK17 Reminder unproven on AWS:** The day-1 reminder (a callback wait that times out, sends the reminder and waits again) has been tested only through a fake durable context. Its first real use on AWS is unproven: watch the first archive's first reminder, or leave a 1-day reminder waiting on the next test stage. Recorded at DCSN4 B.
- **PARK18 Publish writes eml.xml:** Publish writes eml.xml, from the contract's EML export, into the version's prefix beside datapackage.json, and lists it in checksums.sha256 so the weekly integrity check holds. The brief asked for it; nobody needs it until a harvester does. Found by Plan 10b, via the coordinating session (thread 984).
- **PARK19 Teardown stops running executions:** cdk destroy of a stage with a durable execution still running (a submission waiting for review) gets stuck deleting the ingest function's version, then fails DELETE_FAILED after about 10 minutes (Lambda::Version NotStabilized). Seen on ingest-test 2026-11-14 with one waiting submission; stopping it with StopDurableExecution let the retry go through. The teardown path (Plan 10a's deployment skill, and the ingest-e2e script's cleanup) should stop or wait out running executions first.

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
- **DCSN4 Wait for the reminder.** Should the deployed run wait until Sunday to see the real reminder, or finish now? The user chose B: Finish now, trusting the timer's unit tests.
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
- **AGNT15 Test-only sign-in client.** A third Cognito app client, `e2e`, with ADMIN_USER_PASSWORD_AUTH, created only on non-prod stages. The script creates throwaway users with admin APIs, signs them in, and deletes them at the end. The user kept it.

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

- [PLAN1](plans/1-submit-review-publish.md) Submit, review and publish: built
  - TASK1 Task 1: The review policy model and matcher: done. 9db583a + 287415b (decision log row), rebased on Plan 6's #20; just check exit 0; PR #21 CI re-running after rebase
  - TASK2 Task 2: Groundwork in Plan 4's code: done. df8febe..18db588 (lifecycle incoming/, /datasets/&lt;id> rewrite, archive-config SSM param, cruise in backend, asset-size test); just check exit 0; asset 92.8 MiB of 250
  - TASK3 Task 3: Submission records, events and the API: done. 33531a3: archive_backend.submissions, 8 routes, 23 tests; just check exit 0 (390 py). Owner check moves to the caller's published submissions (fixed at the start of TASK4)
  - TASK4 Task 4: The durable ingest function: done. 6f23230 (owner check via the caller's published submissions), 93faf4c (durable ingest, 11 fake-context tests); just check exit 0 (404 py)
  - TASK5 Task 5: Publish and the dataset page: done. ac6caae (submitterIsCurator), b02633b (expired at 360 days), 0133a6e (dataset page), 0e5a215 (publish: version, fill, checksummed copy, catalog items via reindex builders, page, finish); just check exit 0. Catalog-file call is a marked spot until Plan 6's writer lands
  - TASK6 Task 6: The Ingest construct: done. 81e777e (page Cache-Control, datasetId pattern), 3f2dd01 (Ingest construct: durable fn + live alias, 10 GiB /tmp, submissions fn + routes, curators' topic, GuardDuty plan on incoming/, least-privilege grants, just add-curator); just check exit 0 (423 py, 55 ts)
  - TASK7 Task 7: The run on a test stage: done. 5b2374a, 541652f (e2e client, script, ingest-test config) plus review fixes; deployed run on ingest-test passed twice (875cb69, then rebased afd047f on Plan 6): all six paths; reminder decided early under DCSN4 B (PARK17). PR #29 merged as a22c85a
- [PLAN2](plans/2-curator-files-and-page-writer.md) The curator files route and the shared page writer: building · 0 of 2 done
  - TASK8 Task 8: The curator files route: not started
  - TASK9 Task 9: The shared page writer: not started

## Steps

- STEP1 Walk the deployed run on the ingest-test stage: done
  1. agent · Final review of the code, and fixes · done. Review (Opus fallback; OpenAI at its usage limit): 0 critical, 4 important + 1 minor fixed with tests (e8e2db0..4adf4dc); just check exit 0, 442 py + 61 ts; pushed 875cb69
  2. The user · Go for the deploy, and confirm the profile and email · done: Go (2026-11-13 23:58, on the page)
  3. agent · Deploy ResearchArchive-ingest-test and subscribe your curator email · done. cdk deploy exit 0 in 284 s (126 resources); GuardDuty plan on the staging bucket ACTIVE, no status reasons; court@subaud.io subscribed with audience filter court/all
  4. The user · Confirm the curator subscription email · done: Confirmed (2026-11-14 00:17, on the page)
  5. agent · Run just ingest-e2e ingest-test: the four paths, the skip rule, the two-curator case, and leave one submission waiting for its reminder · done. exit 0: approve, reject, request changes then approve, blocking error, skip rule and two curators all pass; reminder submission 7672e8e9 left waiting for court, due after 2026-11-15 07:17 UTC; 3 test users deleted
  6. The user · Check the reminder email arrived · done: Reminder arrived (2026-11-14 00:34, on the page)
  7. agent · Check the Reviews table for the reminded event · done. answered at 00:34 CST Nov 14, a day before the reminder is due; Reviews for 7672e8e9 ends at entered-review 06:17:54 UTC, no reminded event, so the email seen was the Review: one from entering review
  8. The user · On Sunday after 1:17 am Central: check for the Reminder email · done: Reminder arrived (2026-11-14 00:35, on the page)
  9. agent · Check the Reviews table again · done. answered at 00:36 CST Nov 14, still before the reminder is due; Reviews still ends at entered-review; the choice to wait or finish now is on DCSN4
  10. agent · Under DCSN4 B, decide the waiting submission now instead of waiting for its reminder · done. approved 7672e8e9 as a temporary curator (deleted after): 202, then published stream-temperature-at-three-invented-sites-elyfee; events created, submitted, scanned, checked, held, entered-review, decided, published; state file removed; reminder on AWS stays unproven (PARK17)
  11. agent · Redeploy ingest-test from PR #29's rebased head (Plan 6 PLAN1 now underneath) and run just ingest-e2e once more · done. afd047f deployed in 161 s; e2e exit 0: all six runs pass again on Plans 6 + 7 together; one new submission c2b151b6 left waiting (teardown removes it); CI green, PR #29 merged as a22c85a
  12. The user · Go or No go on tearing the stage down · done: Go: tear it down (2026-11-14 10:04, on the page)
  13. agent · Tear down the stage and confirm it is gone · done. first destroy stuck on the ingest function's version while c2b151b6 still ran, DELETE_FAILED (PARK19); stopped that execution, second destroy exit 0; stack gone, 0 ingest-test tables, 0 buckets, its GuardDuty plan gone (the two left protect search-test and web-test); state file removed; Plan 10a told

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
