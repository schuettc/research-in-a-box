---
diazo: research-archive-in-a-box/ingest-review-and-access-workflows
file: PLAN1
status: done
approved: 2026-11-13T22:39:54-06:00
hash: 2626c3cfe8272b185c0458198dc7fcaeae7203725d69690b289204768fb645eb
rests_on: [AGNT1, AGNT10, AGNT11, AGNT12, AGNT13, AGNT14, AGNT15, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, AGNT8, AGNT9, DCSN1, DCSN2, DCSN3]
record: README.md
---

# PLAN1: Submit, review and publish

## Spec

`spec.md` in this folder, approved. This plan builds all of it: the review policy, the submissions API, the durable ingest (scan, checks, hold, review with reminders and the stale mark, the request-changes loop), publish, the curators' topic, the infrastructure, and the run on a test stage.

## The change

- The contract gains `ReviewPolicy` and its matcher.
- archive-backend gains a dependency on cruise and three modules: `submissions` (records, events and the API), `ingest` (the durable function) and `pages` (the dataset page).
- The infra package gains an `Ingest` construct and three small edits to Plan 4's code: the staging lifecycle rule, the site function, and the archive-config parameter.
- A test-only Cognito app client on non-prod stages lets one scripted run (`just ingest-e2e <stage>`) drive the four paths and the policy cases on a deployed stage.

Every task leaves `just check` green.

The durable SDK pinned in archive-backend is `aws-durable-execution-sdk-python==3.0.2`. It provides:

- `context.wait_for_callback(submitter, name=..., config=WaitForCallbackConfig(timeout=Duration...))`, which raises `CallbackTimeoutError` (in `aws_durable_execution_sdk_python.exceptions`) on timeout.
- `context.wait_for_condition` and `context.step`.

The Lambda API offers `SendDurableExecutionCallbackSuccess(CallbackId, Result)`, and `Invoke` takes `DurableExecutionName`. The reindex (`archive_backend/reindex.py`, `infra/src/reindex.ts`) is the working pattern for the handler, the steps, the `live` alias and the IAM, and its tests show how to drive a handler with a fake `DurableContext`.

## Left out

Everything in the spec's Left out section: by-request access, takedown and access changes, DOIs, previews, extension checks, in-place edits, contributor email, multipart uploads, creating projects and withdrawing a submission. The call to Plan 6's catalog-file writer is added when that writer exists in archive-backend. If it exists when Task 5 runs, Task 5 calls it.

## Where

Branch `plan7/build-plan1` from `origin/main`, in the worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan7/build-plan1`. One pull request per task, or one for the plan, against `main`, with auto-merge on once checks pass. The deployed run in Task 7 uses a non-prod stage named `ingest-test` through `ARCHIVE_CONFIG`, so `archive.yaml` is not edited. Plan 6 deploys and destroys its own `test` stage, so the two never collide. Accounts are invitation-only, so the run never relies on self-service sign-up.

### Task 1: The review policy model and matcher

**Does:** Adds `ReviewPolicy` to `archive_contract` (new module `review.py`, exported from the package) as the spec's review-policy section gives it. The fields are `required`, `rules`, `reviewers`, `reminders` and `staleDays`, with their defaults. A `Rule` has optional matchers (`submitters`: user ids or the literal `curators`; `kind`: `new-dataset` or `new-version`; `access`: a list of access levels; `themes`: a list) and an `outcome` of `skip`, `one` or `two`. Adds `match(policy, facts) -> (outcome, rule_index | None)`, where the first match wins and the default follows `required`, and `reminder_schedule(policy)`, which returns the reminder days before `staleDays`, sorted, each a positive whole number. Adds the model to the generated JSON Schema, and adds `Manifest.published: datetime | None` (alias `archive:published`), the publish time that only publish writes.
**Files:** `packages/contract/src/archive_contract/review.py`, `packages/contract/src/archive_contract/__init__.py`, `packages/contract/src/archive_contract/schema.py` if models are listed there, `packages/contract/tests/test_review.py`, the regenerated schema file (`just schema`).
**Checks:** `just check`
**Serves:** DCSN1 (rests on calls AGNT12, AGNT13)

Rebase onto `origin/main` first. If Plan 6 has already added `Manifest.published`, use it as it is and don't add it again.

Tests cover:

- each matcher alone and combined
- the first match winning over a later one
- the default with `required` true and with it false
- the empty policy's defaults
- reminders on or after `staleDays` being refused
- the JSON Schema containing `ReviewPolicy`

### Task 2: Groundwork in Plan 4's code

**Does:** Groundwork in Plan 4's code, listed below.
**Files:** `packages/backend/pyproject.toml`, `uv.lock`, `packages/infra/src/storage.ts`, `packages/infra/src/web.ts`, `packages/infra/src/research-archive.ts` (exposes `archiveConfigParameter`), the tests in `packages/infra/test/` for storage, web and the app, and a new `packages/infra/test/assets.test.ts`.
**Checks:** `just check`
**Serves:** none (rests on calls AGNT3, AGNT9, AGNT14)

- Adds `cruise` to archive-backend's dependencies through a workspace source.
- Changes the staging bucket's lifecycle rule to expire only `incoming/` after 30 days.
- Changes the site function so `/datasets/<id>` and `/datasets/<id>/` go to `/datasets/<id>/index.html`, and every other extensionless path still goes to `/index.html`.
- Makes the construct write the config as JSON to the standard SSM parameter `/research-archive/<stage>/archive-config`. Synth throws when the JSON is over 4096 bytes.
- Adds a packaging test that fails when the unzipped `assets/python` folder reaches 250 MB.

The site function has a unit test that runs the inline JS over `/`, `/about`, `/datasets/abc`, `/datasets/abc/` and `/app.js`. The lifecycle test asserts the `incoming/` prefix filter. The asset test runs after `just lambda-assets`, which `check-ts` already depends on. Measure the asset size with cruise and DuckDB in it and put the number in the task result.

### Task 3: Submission records, events and the API

**Does:** Adds `archive_backend.submissions`, listed below.
**Files:** `packages/backend/src/archive_backend/submissions.py`, `packages/backend/tests/test_submissions.py`.
**Checks:** `just check`
**Serves:** DCSN1 (rests on calls AGNT1, AGNT2, AGNT6, AGNT7, AGNT12)

Adds `archive_backend.submissions`:

- The Submission record (the spec's fields) and its status values.
- `put_event(table, submission_id, type, actor, round, **details)`, which writes `eventKey = <ISO time>#<uuid>`.
- One API handler for every route in the spec's endpoint table, with the role checked from the token's `cognito:groups` claim.

Create validates the file list (relative safe paths, sizes, SHA-256 in hex), resolves `newVersion` and the owner check against the active catalog's dataset item when the manifest id is given in the request, and returns presigned PUTs with `ChecksumSHA256` required. Submit on round 1 invokes the ingest alias with `InvocationType=Event` and `DurableExecutionName=<submissionId>`. On a later round it completes the stored `callbackId` with `{"kind": "resubmit", "round": n}`. Decision checks the caller is a curator, refuses a second approval from the same curator, writes the `decided` event (with `selfReview` when the curator is the submitter), then completes the callback with `{"kind": "decision", "decision": ..., "by": ..., "note": ...}`. Policy `GET` returns the stored policy or the defaults, and `PUT` validates it with `ReviewPolicy` and stores it as the Settings item `review-policy`.

Tests use stubbed clients, as the reindex tests do. They cover:

- role refusals for each route
- the owner check for a new version
- a bad path refused
- the presigned URL carrying the checksum
- submit invoking with the execution name
- resubmit and decision completing the stored callback
- a second approval from the same curator refused
- the policy round trip and an invalid policy refused

### Task 4: The durable ingest function

**Does:** Adds `archive_backend.ingest` with `handler = durable_execution(run)`, following the spec's path as listed below.
**Files:** `packages/backend/src/archive_backend/ingest.py`, `packages/backend/tests/test_ingest.py`.
**Checks:** `just check`
**Serves:** DCSN1, DCSN2, DCSN3 (rests on calls AGNT3, AGNT4, AGNT5, AGNT7, AGNT13)

Adds `archive_backend.ingest` with `handler = durable_execution(run)`, following the spec's path:

- **Scan.** `wait_for_condition` on every round file's `GuardDutyMalwareScanStatus` tag, with backoff capped at one hour.
- **Check.** `cruise.diagnose` on the round, downloaded to `/tmp`, with the profiles and required fields from the config parameter. The report goes to `reports/<id>/<round>.json`. An error finding, or a scan status other than `NO_THREATS_FOUND`, sends the round to needs-changes.
- **Hold.** Copy the round to `held/<id>/`.
- **Policy.** Read the policy once and record the matched rule.
- **Review.** Repeated `wait_for_callback`. The timeout runs to the next reminder or the stale mark. On `CallbackTimeoutError` the function sends a reminder or sets `stale` and alerts, then waits again. On a decision it publishes, counts a first approval in a two-curator case, rejects, or requests changes.
- **Request changes.** A resubmit `wait_for_callback` with a 30-day timeout, which ends as `abandoned` and deletes `held/`.
- **Failure.** A failing step ends as `failed` with an admin alert.

Every status change writes its event in the same step. The publish call is a stub here, and Task 5 fills it in.

Curator messages go to the curators' topic with the message attribute `audience` set to a named reviewer's user id or `all`. The function looks up the reviewer for the package's first theme (`archive:themes`) in `policy.reviewers`.

Tests drive `run` with a fake `DurableContext`. The fake replays `step`, raises `CallbackTimeoutError` on a scripted timeout, and returns scripted callback payloads. The tests cover:

- approve
- reject
- request changes then approve
- a blocking error
- a threat tag
- a skip rule
- a two-curator case that waits after the first approval and publishes after the second
- a reminder then the stale mark
- abandoned

Each test asserts the final status and the ordered event types. Check the field name for themes against `archive_contract.manifest` before writing the lookup.

### Task 5: Publish and the dataset page

**Does:** Fills in publish as the spec's seven steps, each a named step that is safe to repeat, as listed below.
**Files:** `packages/backend/src/archive_backend/ingest.py`, `packages/backend/src/archive_backend/pages.py`, `packages/backend/tests/test_publish.py`, `packages/backend/tests/test_pages.py`.
**Checks:** `just check`
**Serves:** none (rests on calls AGNT6, AGNT8, AGNT9, AGNT10, AGNT11)

Fills in publish as the spec's seven steps, each a named step that is safe to repeat:

- Assign the version from the active catalog.
- Fill in `id`, `version`, `archive:published` (the publish time, made inside the step; the exports' publication year is its year), publisher and identifier.
- Regenerate `README.md` with the contract's readme export and rewrite `checksums.sha256`.
- Copy to `open|restricted/<id>/<version>/` with one PUT per file and `ChecksumSHA256`, putting the manifest last.
- Put the catalog items built by `reindex.catalog_items` and `reindex.dataset_item` into the active table.
- Write `site/datasets/<id>/index.html` from `archive_backend.pages`, an escaped HTML template with the title, description, citation, version, open file links and the schema.org JSON-LD from the contract's export.
- Call Plan 6's catalog-file writer if it exists.
- Delete `held/` and record `published`.

The dataset id, when none is given, is a slug of the title plus six random lower-case characters, made inside a step.

Tests publish the sample package against stubs. They cover:

- version 1, then version 2 for the same id
- the open and restricted prefixes
- every PUT carrying a checksum, with the manifest last
- the rewritten `checksums.sha256` validating with `archive_contract.validate`
- catalog items equal to what the reindex builds from the published manifest
- the page escaping a title containing `<script>` and holding JSON-LD that parses

### Task 6: The Ingest construct

**Does:** Adds `packages/infra/src/ingest.ts` and builds it in `ResearchArchive`, as listed below.
**Files:** `packages/infra/src/ingest.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/ingest.test.ts`, `justfile`.
**Checks:** `just check`
**Serves:** DCSN2, DCSN3 (rests on calls AGNT1, AGNT14)

Adds `packages/infra/src/ingest.ts` and builds it in `ResearchArchive`, through `archive.pythonFunction`:

- `IngestFunction`, with `durableConfig` set to an execution timeout of 365 days and retention of 30 days, a 15-minute timeout and 2048 MB, plus its `live` alias.
- `SubmissionsFunction`.
- The routes under `/api/submissions`, behind the authorizer.
- The curators' topic.
- `AWS::GuardDuty::MalwareProtectionPlan` on the staging bucket, with `ObjectPrefixes: ["incoming/"]`, tagging on, and its role as in the AWS documentation.
- Least-privilege grants: staging read and write, archive write, derived `site/*` write, active catalog read and write and both tables, Submissions, Reviews and Settings, the config parameter read, alert and curator topics publish, `lambda:InvokeFunction` on the alias, and `lambda:SendDurableExecutionCallbackSuccess` on the function.
- A stack output `IngestFunction`.

Adds `just add-curator <stage> <email> <userId>`, which subscribes the email to the curators' topic with the filter policy `{"audience": ["<userId>", "all"]}`.

Synth tests assert:

- the alias
- the durable config
- each route's method and authorizer
- the GuardDuty plan's bucket and prefix
- the topic
- the callback permission scoped to the ingest function

Check the GuardDuty plan's CloudFormation properties against the AWS documentation before writing them.

### Task 7: The run on a test stage

**Does:** A test-only Cognito app client and `just ingest-e2e <stage>`, which drives the runs listed below.
**Files:** `packages/infra/src/auth.ts`, `packages/infra/test/auth.test.ts`, `scripts/ingest_e2e.py`, `justfile`, a test config such as `examples/ingest-test-stage/archive.yaml`.
**Checks:** `just check`; `just ingest-e2e ingest-test` against the deployed stage
**Serves:** DCSN1, DCSN2, DCSN3 (rests on calls AGNT13, AGNT15)

Adds a test-only Cognito app client `e2e` with `ADMIN_USER_PASSWORD_AUTH`, created only on non-prod stages, and `scripts/ingest_e2e.py` behind `just ingest-e2e <stage>`. The script:

1. Creates three throwaway users (a contributor and two curators) with admin APIs.
2. Sets a policy.
3. Drives these runs against the deployed API:
   - approve, which is then fetched at `/data/<id>/1/datapackage.json` and `/datasets/<id>`
   - reject
   - request changes, then round 2 approved
   - a copy of the sample with a core field removed, which returns `needs-changes`
   - a skip rule that publishes without review
   - a two-curator case that waits after one approval and publishes after the second
   - a reminder set to the policy's smallest interval, checked as an event
4. Asserts the event types in Reviews for each run.
5. Deletes its users.

Deploying the stage and confirming the curator subscription are your steps. Seeing the reminder email arrive is part of your step. Tearing the test stage down after the run is a step with Go / No go, as Plan 4's was.

A synth test pins that a `prod` stage has no `e2e` client and no `ADMIN_USER_PASSWORD_AUTH` flow on any client.

The reminder interval is in days, so the run checks the reminder with a policy whose smallest reminder is 1 day, and leaves that run's submission waiting. The script records its id, and a re-run the next day asserts the `reminded` event and decides it. This waits a day because day is the policy's smallest unit. Making the unit smaller only for a test would be a second path.
