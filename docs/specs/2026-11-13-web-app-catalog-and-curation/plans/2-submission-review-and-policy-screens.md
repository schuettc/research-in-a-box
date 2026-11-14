---
diazo: research-archive-in-a-box/web-app-catalog-and-curation
file: PLAN2
status: approved
approved: 2026-11-14T15:29:41-06:00
hash: f72d3ea874decafcc316b4300b3cc27222e87e7e506c1776d3ce3c0af29841f3
rests_on: [AGNT13, DCSN5]
record: README.md
---

# PLAN2: The contributor, curator and admin screens

## Spec

`spec.md` in this folder ("The plans": PLAN2 is the submission, review and policy screens, written once Plan 7's `/api/submissions` is built), with DCSN5 (C: contributors upload a package made with cruise; building one in the browser is PARK19), call AGNT13 (the screens and the API gaps), PRIN1 (one frame on every view) and the Reading room look PLAN3 built. The research behind it is `documents/plan7-api.md`: every route, its group, request and response, the lifecycle, the findings report and the review policy, read at main.

## The change

**Backend gaps in Plan 7's API**, built here because the coordinating session didn't object (muster thread 1008): a CORS rule on the staging bucket for the site's origin, so a browser can PUT the presigned uploads and read the findings report and held files; the submissions routes in the committed OpenAPI spec, from Pydantic models the handler validates with, so the screens use generated types; two lookups that turn Cognito ids into email addresses (`GET /api/people`) and list the curators (`GET /api/curators`); and new upload links for a round-1 draft whose links expired.

**Signed-in areas.** The masthead gains the areas a reader's groups allow (Submit for contributors, Review for curators, Settings for admins), in the same place on every view. Each area asks a reader who isn't signed in to sign in, and says plainly when their account can't use it.

**Contributor.** Submit: choose or drop the package folder, the app checks it holds `datapackage.json` and `checksums.sha256` and that each file matches its checksum, takes the dataset id from the manifest, creates the submission, uploads every file with progress, and submits. My submissions lists them with their status. A submission's page shows where it stands, the checks' findings grouped by severity (the same Finding model cruise prints), and its history; on needs-changes the contributor chooses the corrected folder and resubmits as the next round.

**Curator.** The review queue (in review by default, other statuses a filter away), each row saying new dataset or new version, stale, one or two curators needed, and who it's assigned to. A submission's review page: the findings, the held files with download links and a preview of a table's first rows, the history with people as emails, and Approve, Reject or Request changes with a note, confirmed in a modal; with two curators, the page waits for the pipeline before taking the second approval.

**Admin.** Settings: the review policy as a form (required, the ordered rules, named reviewers by theme picked from the curators, reminders and the stale mark), saved with the API's own validation messages.

**Risk.** Moderate. The screens only call Plan 7's API, which already checks every caller's group; the new routes are read-only and limited to curators and admins; CORS is limited to the site's own origin. What a mistake could do: show one person's email to someone who shouldn't see it (the lookups check the group, pinned by tests), or let a contributor renew links on someone else's submission (the existing ownership check, pinned by a test). Gates are backend tests for each new route and change, synth tests for CORS and grants, web tests with the API mocked, `just check`, and one walk on a test stage with your look.

**Cost.** No new AWS service. Two read-only Cognito calls per lookup. For you: two Go presses (deploy, teardown) and one look.

## Left out

- Building the package in the browser (PARK19).
- Withdrawing a submission, contributor email and multipart uploads over 5 GB (Plan 7's PARK11, PARK8, PARK9).
- Paging the queue and My submissions: the list call returns everything today; paging waits for a real archive with more than a screenful.
- Hashing very large files without holding each in memory: files are hashed one at a time with the browser's SHA-256 (fine for the 155 MB the corpus has); a streaming hasher waits for a larger file.
- Editing the archive config from the browser; only the review policy is a run-time setting.

## Where

| Path | What changes |
| --- | --- |
| `packages/infra/src/storage.ts`, `ingest.ts`, their tests | CORS on the staging bucket; the lookup routes and their Cognito grants |
| `packages/backend/src/archive_backend/submissions.py`, a new `submissions_api.py` (the models), `people.py`, `api.py` (the OpenAPI writer), their tests | Models, validation, renewing links, the lookups, the spec |
| `packages/web/src/schema/openapi.json`, `src/generated/` | Regenerated |
| `packages/web/src/` (`App.tsx`, `auth.ts`, `api.ts`, `routes/Submit*.tsx`, `routes/Review*.tsx`, `routes/Settings.tsx`, `Findings.tsx`, `People.tsx`, `styles.css`) and tests | The screens |
| `docs/planning-handoff.md` | Decision log rows for the new routes and the CORS rule |

### Task 16: Close Plan 7's API gaps

**Does:** Adds a CORS rule to the staging bucket allowing the site's origin (the distribution's domain; plus `http://localhost:5199` on non-prod stages for local work) to `PUT` and `GET`, with the `x-amz-checksum-sha256`, `content-type` and `range` headers, exposing `ETag`. Lets `/api/submissions/{id}/uploads` give a round-1 draft new links for its own files (today it refuses `draft` in round 1), still only for the submitter. Adds `GET /api/people?sub=<id>&sub=<id>` (curator or admin; at most 50 ids; answers `{people:{<sub>:{email}}}`, unknown ids left out) and `GET /api/curators` (admin; answers `[{sub,email}]` for the `curator` group), backed by Cognito `ListUsers` with a `sub` filter and `ListUsersInGroup`, with the Lambda granted exactly those two actions on the pool. Records the routes and the CORS rule in the handoff's Decision log.
**Files:** `packages/infra/src/storage.ts`, `packages/infra/src/ingest.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/storage.test.ts`, `packages/infra/test/ingest.test.ts`, `packages/backend/src/archive_backend/submissions.py`, `packages/backend/src/archive_backend/people.py`, `packages/backend/tests/test_submissions.py`, `packages/backend/tests/test_people.py`, `docs/planning-handoff.md`
**Checks:** `uv run pytest packages/backend`, `uv run mypy packages`, `npm test -w packages/infra`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests: the synth shows the CORS rule with the site's origin and those methods and headers; a round-1 draft gets new links for its submitter and 403 for anyone else; `/people` answers emails to a curator and an admin, 403 to a contributor, and leaves out an unknown id; `/curators` answers only to an admin; more than 50 ids is a 400.

### Task 17: The submissions API in the OpenAPI spec

**Does:** Moves every request and response shape of `/api/submissions`, `/api/people` and `/api/curators` into Pydantic models (`submissions_api.py`): the file list, create, uploads, submit, decision, the Submission item (without `callbackId`, which only the pipeline needs), an event with its typed details, the read answer with `reportUrl`, the held files, the findings report (reusing the contract's `Finding` and verdicts), and the policy (the contract's `ReviewPolicy`). The handler validates bodies and builds answers through them, with the same 400 and 409 messages as now. The OpenAPI writer adds these paths beside the read API's, so `just openapi` and the drift check cover them, and `just web-types` regenerates the app's types.
**Files:** `packages/backend/src/archive_backend/submissions_api.py`, `packages/backend/src/archive_backend/submissions.py`, `packages/backend/src/archive_backend/api.py`, `packages/backend/tests/test_submissions.py`, `packages/web/src/schema/openapi.json`, `packages/web/src/generated/api.ts`
**Checks:** `uv run pytest packages/backend`, `uv run mypy packages`, `just check-schema`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests: every existing submissions test still passes unchanged in what it asserts; the read answer no longer carries `callbackId`; `just check-schema` fails when a model changes and the spec doesn't.
- `scripts/ingest_e2e.py` reads `callbackId` to know when to resubmit: it keeps working by reading the stored item through the test's own DynamoDB access, or the read answer gains a boolean `waiting` (the pipeline holds an open callback) that the script and the screens both use. Pick the second and record a Ruling.

### Task 18: Signed-in areas in the frame

**Does:** The app reads the reader's groups from the ID token's `cognito:groups`. The masthead's nav shows Submit (contributors), Review (curators) and Settings (admins) beside Browse and About, in the same place on every view and for every group (an area a reader lacks simply isn't listed; the nav's left edge and the Account button never move). Each area is a route that, signed out, shows its heading with Sign in; signed in without the group, says which role it needs and whom to ask. API helpers for every submissions route from the generated types, a people hook that looks up and caches emails (showing "you" for the reader), and plain labels for every status and event. Every new view keeps PRIN1's frame: its h1 where every h1 sits, no layout shift between loading, loaded and error.
**Files:** `packages/web/src/App.tsx`, `packages/web/src/auth.ts`, `packages/web/src/api.ts`, `packages/web/src/People.tsx`, `packages/web/src/labels.ts`, their tests, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests: each group sees exactly its entries; the nav and Account button keep their position whatever the groups; a signed-out area offers Sign in back to itself; a signed-in reader without the group is told which role; the people hook batches ids and shows "you".

### Task 19: The contributor's screens

**Does:** `/submit`: a drop area and Choose folder (a directory input), listing what was found; it refuses a folder without `datapackage.json` or `checksums.sha256`, hashes each file with the browser's SHA-256 and compares it with `checksums.sha256` (a mismatch names the file and stops), reads the dataset id and title from the manifest and says whether it is a new dataset or a new version, then creates the submission, uploads each file to its presigned link with the checksum header and a progress bar per file and overall, and submits. `/submissions`: My submissions with title, round, status and last change. `/submissions/<id>`: the status as one line ("Waiting for a curator", "Changes requested"), the checks' summary and findings grouped error, warning, note with each finding's target and suggested fix, a curator's note when changes were requested, and the history; on needs-changes, Resubmit opens the same folder flow for the next round and waits until the pipeline is ready for it; an expired round-1 upload gets new links. It reloads the submission every 10 s while something is in progress and stops when nothing can change.
**Files:** `packages/web/src/routes/Submit.tsx`, `packages/web/src/routes/MySubmissions.tsx`, `packages/web/src/routes/Submission.tsx`, `packages/web/src/Findings.tsx`, `packages/web/src/package.ts` (folder reading and hashing), their tests, `packages/web/src/App.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests with the API mocked and files from the sample package: a folder without `checksums.sha256` is refused; a changed file is named as not matching; the upload sends each file's checksum header; progress reaches 100 %; findings group by severity; needs-changes offers Resubmit and the second round's files go to the new links; polling stops on a final status; axe on each screen.

### Task 20: The curator's screens

**Does:** `/review`: the queue for a status (in review by default; a filter for the others), each row with the title (from the held manifest), submitter's email, round, new dataset or new version, how many curators it needs and how many have approved, stale, and who it's assigned to. `/review/<id>`: the summary, the findings (the shared component), the held files with download links and, for a CSV, a preview of its first rows fetched by range through the file's link, the history with emails, and Approve, Reject and Request changes; each opens a modal with an optional note (required for Request changes and Reject) and a confirm. After a first approval of a two-curator review, the page says it waits for a second curator and disables Approve for the curator who approved. A decision answered 409 is shown in the API's words with Reload.
**Files:** `packages/web/src/routes/ReviewQueue.tsx`, `packages/web/src/routes/Review.tsx`, `packages/web/src/Preview.tsx`, their tests, `packages/web/src/App.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests: the queue marks stale and new version and reads the needed count from the `entered-review` event; a decision posts its note; Request changes without a note can't be confirmed; the second approval is disabled for the first approver; a 409 shows its message; the preview shows the first rows of a CSV; axe on each screen.

### Task 21: The admin's review policy

**Does:** `/settings`: the review policy as a form. Review required (a switch); the rules as an ordered list, each with its conditions (submitters as curators or people picked from a list, new dataset or new version, access levels, themes) and its outcome (skip, one curator, two curators), with move up, move down, add and remove; named reviewers per theme, picked from `/api/curators`; reminders as a list of days and the stale mark in days. The field names, allowed values and defaults come from the `ReviewPolicy` JSON Schema. Save sends it whole; the API's validation message shows beside the form; a saved policy says it applies to submissions entering review from now on.
**Files:** `packages/web/src/routes/Settings.tsx`, `packages/web/src/routes/Settings.test.tsx`, `packages/web/src/App.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN5 (rests on call AGNT13)

- Tests: the form loads the stored policy and saves it unchanged; reordering rules changes the saved order; a reminder past the stale mark shows the API's message; the reviewer picker lists curators by email; axe.

### Task 22: The walk on web-test

**Does:** Opens the PR with Tasks 16 to 21 and enables auto-merge. After it merges and you Go, deploys `ResearchArchive-web-test`, creates throwaway users (a contributor, a curator who is also an admin, a second curator) and walks headless at 1280 and 390: the contributor submits the sample package folder and sees the findings; the curator requests changes with a note; the contributor resubmits round 2; the curator approves and it publishes; a second submission is rejected; the admin sets a two-curator rule, and a third submission needs both curators, the second approval from the other one; the frame doesn't move between any of these views; axe on every screen. Then invites you as contributor, curator and admin for your look (submit the sample package yourself and review it). On your second Go, destroys the stage and confirms nothing is left.
**Files:** none changed; the walk's notes and screenshots go in the task's result and the folder
**Checks:** `just check` on main; `cdk deploy` and `just destroy web-test` exit 0
**Serves:** DCSN5

- The walk is a step on this folder's page, with a Go before the deploy and a Go before the teardown. Throwaway users are deleted at the end.
- On any AWS auth error, stop and report; never copy or export credentials.
