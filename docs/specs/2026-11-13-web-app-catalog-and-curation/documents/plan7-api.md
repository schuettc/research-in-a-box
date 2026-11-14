# Plan 7 API for the Plan 8 contributor, curator and admin screens

Read at origin/main 4bbba59 from the ux-review worktree.

## 1. Routes

The router is `submissions.py:593-627`, and the CDK routes are `infra/src/ingest.ts:165-180`. Every route sits behind the Cognito authorizer. The group check uses the `cognito:groups` claim (`submissions.py:596`, `whoami.py:7-13`).

The script sends the raw ID token in `Authorization`, with no `Bearer` prefix (`ingest_e2e.py:262-263`). The API is served at `https://<SiteDomain>/api/...`.

Errors come back as `{"error": "<text>"}` with status 400, 403, 404 or 409 (`:201-212`, `:623-627`). A POST or PUT body must be a JSON object (`:602`).

| Method and path | Group | Request | Response |
|---|---|---|---|
| `POST /api/submissions` | contributor (`:367`) | `{files:[{path,size,sha256}], datasetId?}` | 201 `{submissionId, round:1, uploads:[{path,url,headers:{x-amz-checksum-sha256}}]}` (`:366-398`) |
| `GET /api/submissions` | contributor or curator (`:493`) | query `status=<Status>` (curator; default `in-review`), `mine` (any value: own list) | 200 `{submissions:[<Submission item>]}` (`:491-508`) |
| `GET /api/submissions/{id}` | its submitter, or any curator (`:512-515`) | none | 200 `{submission, events:[...], reportUrl?}` (`:511-529`) |
| `POST /api/submissions/{id}/uploads` | contributor and its submitter (`:403-405`) | `{files:[...]}` | 200 `{submissionId, round, uploads}` (`:401-422`) |
| `POST /api/submissions/{id}/submit` | contributor and its submitter (`:427-429`) | none | 202 `{submissionId, round, status:"checking"}` (`:425-458`) |
| `POST /api/submissions/{id}/decision` | curator (`:462`) | `{decision:"approve"\|"reject"\|"request-changes", note?:string}` | 202 `{submissionId, decision}` (`:461-488`) |
| `GET /api/submissions/{id}/files` | curator (`:534`) | none | 200 `{round, files:[{path,size,sha256,url}]}`; links last 300 s (`:532-560`) |
| `GET /api/submissions/policy` | admin (`:572`) | none | 200 `ReviewPolicy.dump()` (`:571-573`) |
| `PUT /api/submissions/policy` | admin (`:577`) | a ReviewPolicy object | 200 the stored policy; 400 `invalid policy: ...` (`:576-590`) |

Rules for the file list (`validate_files`, `:230-250`):

- 1 to 1,000 files.
- Each path is relative and safe: no leading `/`, no `\`, no `.`, `..` or empty segments, at most 900 characters, no control characters, and no path listed twice.
- `size` is an integer from 0 to 5 GiB (`MAX_PUT`, `:71`).
- `sha256` is 64 hex digits, stored lower-case.

`datasetId` must match `[A-Za-z0-9_-]{1,200}` (`:373`). If it names a published dataset, only a curator or that dataset's earlier submitter may create the version, otherwise the call returns 403. A new version gets `newVersion: true` (`:370-380`, `:343-363`).

The Submission item is a TypedDict (`:86-102`) with these fields: `submissionId`, `submitter` (the Cognito sub), `submitterIsCurator`, `status`, `createdAt`, `round`, `files` (each round number as a string, mapped to its FileEntry list), `datasetId?`, `newVersion`, `rule` (int or null), `approvals` (list of subs), `stale`, `callbackId` (exposed; PARK13), `reportKey`.

The list call queries the `byStatus` or `bySubmitter` index once and doesn't follow `LastEvaluatedKey`, so there is no paging (`:502-508`). A contributor's `status` query parameter is ignored. The read route presigns `reportUrl` for 3,600 s (`:522-528`).

**OpenAPI coverage.** `packages/web/src/schema/openapi.json` lists only `/api/admin/usage` (:680), `/api/datasets/{id}` and its usage, versions and download routes (:719-887), `/api/projects/{id}` (:944) and `/api/search` (:983). It is generated from `archive_backend.api` (`justfile:219-231`). It has no submissions routes and no whoami. The contract JSON Schema `packages/web/src/schema/archive-contract.schema.json` does include `ReviewPolicy` (:1555), `Rule` (:1632), `Finding` (:669), `Target` (:1864), `Evidence` (:438), `QualityVerdict` (:1208) and `ValidationVerdict` (:1946), because `archive_contract/schema.py:26` adds `Finding` and `ReviewPolicy`. Types for submissions, events and responses would have to be written by hand, or the spec extended.

**CORS gap.** The staging bucket (`infra/src/storage.ts:32-36`) has no `cors` rule, and nothing in infra/src mentions CORS. Browser PUTs to the presigned URLs, and `fetch(reportUrl)`, will fail preflight. Plain link navigation to the held-file URLs works.

## 2. Lifecycle

`Status` (`submissions.py:32-43`; spec.md:43) has these values:

- `draft`
- `checking`
- `needs-changes`
- `in-review`
- `publishing`
- `published`
- `rejected`
- `abandoned`
- `expired`
- `failed`

`stale` is a flag on an `in-review` submission, not a status.

Transitions:

- Create sets `draft` (`:386`). Submit moves `draft` to `checking` with a conditional update (`:440`).
- In the check step, an error finding sets `needs-changes` and clears `callbackId` (`ingest.py:366-370`).
- In the policy step, a `skip` outcome records only `rule`. Otherwise it sets `in-review`, `stale=false`, `approvals=[]` (`ingest.py:419-445`).
- In the version step, publish sets `publishing` (`ingest.py:601`), then the finish step sets `published` (`:761`).
- A reject sets `rejected` (`:498`). Request-changes sets `needs-changes` (`:505`).
- With no resubmit within 30 days the status becomes `abandoned` (`:511`). At 360 days it becomes `expired` (`:519`). A failed step or a bad callback sets `failed` (`:797`, `:1002-1011`).
- Uploads in `needs-changes` move the submission to round+1 and back to `draft` (`submissions.py:410-419`).
- `held/<id>/` exists only while the status is `in-review` or `publishing` (`HELD`, `:75`).

`EventType` (`:46-62`): each event is a Reviews item `{submissionId, eventKey:"<ISO>#<uuid>", type, actor (sub or "pipeline"), round, at, ...details}` (`put_event`, `:183-198`). Details by type:

- `created` and `submitted`, or `resubmitted` on round 2 and later: no details (`:395`, `:457`).
- `scanned` `{files, threats:{path:status}}` (`ingest.py:294`).
- `checked` `{errors, warnings, notes, reportKey, blocked}` (`:371-382`).
- `held` `{files}` (`:397`).
- `entered-review` `{rule, outcome:"one"|"two", audience: sub|"all"}` (`:428-437`).
- `reminded` `{day, audience}` (`:465`).
- `stale` `{days, audience}` (`:480`); it also sends an admin alert.
- `decided` `{decision, note?, selfReview?}`, written by the API before it completes the callback (`submissions.py:475-480`).
- `rejected` `{note}`, actor is the curator (`ingest.py:499`).
- `published` `{rule, datasetId, version}` (`:762-771`).
- `abandoned` `{days:30}`, `expired` `{days:360}`, `failed` `{error}` (`:512`, `:520`, `:798`).

The `needs-changes` from a request for changes writes no event of its own; the screen reads it from `decided` (`:503-505`).

Event order isn't guaranteed within one moment (`ingest_e2e.py:134-150`). Sort by `eventKey`; the read returns events in sort-key order.

## 3. Contributor upload and the request-changes loop

The call order is in `ingest_e2e.py:317-331`:

1. `POST /api/submissions {files}` returns presigned PUTs.
2. PUT each file with the returned headers (`:292-303`).
3. `POST /{id}/submit`.

There is no separate manifest upload. `datapackage.json` and `checksums.sha256` are ordinary files in the list. `checksums.sha256` is required, because the fill step reads it (`ingest.py:632-634`).

Each URL is a presigned `put_object` under `incoming/<sid>/<round>/<path>`. It signs `ChecksumSHA256` as base64 of the hex digest, so the client must send the header `x-amz-checksum-sha256` with that value. URLs last 3,600 s and use SigV4 virtual-host addressing (`submissions.py:253-273`, `:73`, `:77`).

Submit HEADs every declared file and returns 409 `not uploaded yet: a, b` if any is missing (`:276-287`, `:437-439`). A submit with no stored callback in round 2 or later returns 409 `the pipeline is not waiting for a resubmit` (`:434-436`).

**Rounds.** Round 1 is set at create. `/uploads` is allowed only in `needs-changes` (it moves to round+1) or in `draft` with round above 1 (same round, new links). In any other status it returns 409 `no uploads while <status>` (`:401-422`). So an expired round-1 link can't be renewed.

Wait until `callbackId` is set before resubmitting; the e2e script polls for this (`ingest_e2e.py:340-358`). With no resubmit within 30 days the submission is `abandoned` (`ingest.py:950-963`).

**Report** at `reports/<sid>/<round>.json` (`ingest.py:339-365`):

```json
{"round": 2,
 "validation": {"valid": true, "contractVersion": "...", "checkedAt": "..."},
 "quality": {"errors": 0, "warnings": 1, "notes": 2, "auditedAt": "...", "score": 87,
             "find": {"passed": 3, "applicable": 4}, "understand": {}, "trust": {}},
 "findings": [Finding, ...]}
```

`validation` and `quality` are null when the scan blocked the round. `quality` is null when the manifest can't be read (`cruise/diagnose.py:61-98`).

`Finding` (`archive_contract/findings.py:32-40`) is `{ruleId, severity:"error"|"warning"|"note", message, target?:{resource?,field?,path?}, evidence?:{rows?,values?,count?}, suggestedFix?}`. Null standard fields are dropped (`_base.py:29-48`). Scan findings use `ruleId` `scan.<status>` with a target path (`ingest.py:297-307`). Any error blocks the round; warnings and notes go to review.

## 4. Curator decision, two curators and named reviewers

`POST /{id}/decision {decision, note?}`:

- The status must be `in-review` with a `callbackId`, else 409 `not in review (...)`.
- A curator who already approved gets 409 `a second approval must come from a different curator`.
- If the submitter decides their own submission, the event records `selfReview: true`.
- If the callback can't be completed, the call returns 409 `the review wait has already closed`, after the `decided` event was written (`submissions.py:461-488`).

Two curators: the `entered-review` event carries `outcome:"two"`. The submission's `approvals` grows as each approval lands (`ingest.py:486-492`). After the first approval the pipeline opens a new callback, so the screen should wait for `callbackId` to change before accepting a second decision (`ingest_e2e.py:464-484`). Approval completes when the number of distinct approvers reaches the number needed (`ingest.py:899`, `:934-937`). The needed count isn't on the Submission item.

Named reviewers: `audience` is the first curator listed for the manifest's first theme in the policy, otherwise `all` (`ingest.py:416-417`). It appears in the `entered-review`, `reminded` and `stale` events. Any curator may decide.

Held files come from `GET /{id}/files`: 300 s links to the current round's listed files only, and 409 unless the status is `in-review` or `publishing`.

## 5. ReviewPolicy (`archive_contract/review.py`)

- `required: bool = true`
- `rules: list[Rule] = []`. Each Rule (`:33-56`) is `{submitters?: [sub | "curators"], kind?: "new-dataset"|"new-version", access?: ["open"|"restricted"|"by-request"|"description-only"], themes?: [str], outcome: "skip"|"one"|"two"}`. The first match wins. With no match the outcome is `one` if `required` is true, otherwise `skip` (`:82-88`).
- `reviewers: {theme: [sub]} = {}`
- `reminders: [positive int] = []`, each below `staleDays`, enforced by a validator (`:74-79`).
- `staleDays: positive int = 14`
- Extra keys are allowed (`extra="allow"`).

The policy is stored as the Settings item `review-policy` with `updatedBy` and `updatedAt`, but the GET returns only the policy (`submissions.py:563-590`). With no item set, GET returns the defaults. The policy is read once when a round enters review (`ingest.py:400-453`), so editing it never changes a submission already waiting. An example policy is at `ingest_e2e.py:116-131`.

## 6. How `ingest_e2e.py` drives the API

Setup (`:533-596`):

- Creates a contributor, a curator who is also an admin, and a second curator.
- Saves the current policy with GET, PUTs the test policy, and restores the saved one at the end.

Runs:

- Approve (`:399-406`): created → submitted → scanned → checked → held → entered-review → decided → published. Then checks `/data/<id>/1/datapackage.json` and `/datasets/<id>`.
- Reject (`:409`).
- Request changes, then resubmit and approve as round 2, version 1 (`:418-433`).
- Blocked: `checked.blocked` with errors of at least 1, then `needs-changes`, then resubmit (`:436-451`).
- Skip: no `entered-review`; `published.rule == 0` (`:454`).
- Two curators: the second approval by the same curator returns 409 (`:464-484`).
- Reminder (`:487-512`).

Every run polls `GET /{id}` every 10 seconds.

## 7. What Plan 7's decisions and spec say for the screens

- The submit screens, the curator screens and the admin's policy screen belong to Plans 8 and 9 (spec.md:172). The admin edits the policy through the endpoint until Plan 8's screen exists, and the web app gets the model from the JSON Schema (AGNT12, README:79; spec.md:71).
- Contributors read their status from `GET /{id}`; there is no contributor email (DCSN2, spec.md:97). Curators get email through SNS, filtered per sub and `all`.
- The curator sees whether a submission is a new version of an existing dataset (AGNT6, README:73). Self-review is allowed and logged. With two curators, the approvals come from two different people (AGNT7).
- The web app taking over the dataset page is Plan 8's job (AGNT9).

Open follow-ups that affect screens (README:32-50):

- PARK8: contributor email.
- PARK9: multipart uploads; files over 5 GB are refused.
- PARK11: withdrawing a submission; there is no endpoint.
- PARK13: `callbackId` is exposed in responses.
- PARK12: an event can be recorded twice when a step retries. Show events deduplicated or tolerate repeats.
- PARK14: a failed publish leaves a partial META item in the catalog.
- PARK1 and PARK2: by-request access and takedown don't exist yet.
- PARK10: there is no way to create projects.

Gaps found here:

- The staging bucket has no CORS rule.
- No endpoint turns a sub into a name or email, or lists curators. Only `/api/whoami` exists, and it returns your own sub, email and groups.
- An expired round-1 upload link can't be renewed.
- The list call has no paging.