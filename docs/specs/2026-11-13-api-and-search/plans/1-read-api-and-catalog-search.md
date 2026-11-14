---
diazo: research-archive-in-a-box/api-and-search
file: PLAN1
status: done
approved: 2026-11-13T22:39:28-06:00
hash: 0ac73b3fa188e4510489aa87a4f43891ef7ad267b3ea1ec41cda244d554aafa6
rests_on: [AGNT1, AGNT10, AGNT2, AGNT3, AGNT6, AGNT7, AGNT8, AGNT9, DCSN1, DCSN2, DCSN3, DCSN4]
record: README.md
---

# PLAN1: The read API, server search and downloads

## Spec

`docs/specs/2026-11-13-api-and-search/spec.md`, every section. Plans 1, 2 and 4 are built and merged: build on `archive_contract`, `archive-backend` (`reindex.py` with `catalog_items` and `dataset_item`), and the `ResearchArchive` construct with its `api`, `authorizer`, `catalogTables`, `activeCatalogParameter`, `archiveBucket`, `derivedBucket`, `downloadCounts`, `settings`, `distribution` and `pythonFunction`. The handoff's Decision log (rows dated 2026-11-13 for Plans 4, 6 and 7) holds the catalog item shapes and the archive layout. The implementer reads the spec beside this plan.

## The change

One API Lambda on Powertools answers search, dataset, version and project reads, restricted download links and the usage form. One function writes `catalog.json`, and the reindex calls it. A daily function rolls CloudFront's logs into DownloadCounts. One internal construct wires it all into `ResearchArchive`. Then one test deploy, a stage named `test` in your AWS account, walks the spec's "How we'll know it works" and is destroyed.

**Risk:**

- Tasks 1 to 4 are local code and CI; a mistake is undone by reverting the PR.
- The one way to do harm is a download route that signs a key it shouldn't. Task 2's tests cover a signed-out call, a path outside the version, a by-request dataset and an open one; links last five minutes; CloudFront is denied `restricted/*`.
- Task 5 creates real resources under a non-prod stage, all deleted with the stack; a few dollars at most, undone by `cdk destroy`. Nothing touches a prod stage.

**Cost:**

- One walkthrough step for you (STEP1): name the profile and alert address, Go for the deploy, sign in twice in the browser and paste back the URL, Go for the teardown.
- New dependency: `aws-lambda-powertools` in `archive-backend` (pure Python).
- No new programs on your machine.

## Left out

- Semantic search, the vector index and the embedding model (PLAN3).
- Submission, review and review-policy endpoints (Plan 7).
- Theme and species in the catalog (Plan 2's PARK5 and PARK6).
- The CLI and MCP sign-in client (Plan 9); Task 5 walks the flow by hand once.
- An admin reindex route (Plan 4's PARK1).
- Loading project records into the catalog table: projects are read from the archive bucket where they live.

## Where

- Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan6/read-api-and-catalog-search`, branch `plan6/read-api-and-catalog-search` from `origin/main`. Confirm with `git -C <wt> branch --show-current` before editing.
- Python: `packages/backend/pyproject.toml`, `uv.lock`, `packages/backend/src/archive_backend/{catalog_file,search,api,downloads,reindex}.py`, their tests under `packages/backend/tests/`, `packages/contract/src/archive_contract/usage.py` with its test.
- TypeScript: `packages/infra/src/read-api.ts` (new), `packages/infra/src/research-archive.ts`, `packages/infra/src/reindex.ts`, `packages/infra/test/read-api.test.ts` (new), `packages/infra/test/reindex.test.ts`.
- `justfile`, `packages/web/src/schema/openapi.json` (new, generated), `docs/planning-handoff.md` (Decision log: `publishedAt`).
- Global constraints:
  - Lambdas are Python 3.13 on arm64 through `archive.pythonFunction`; `just check` must exit 0.
  - Nothing reaches AWS in Tasks 1 to 4.
  - Task 5 runs only with your Go on STEP1, under the profile you name, never against a stage named `prod`.
  - On any AWS auth error, stop and report; never copy or export credentials.

### Task 1: The catalog file and its writer

**Does:** Adds `archive_backend.catalog_file.write_catalog_file(table_name, derived_bucket)`, which builds `catalog.json` from a catalog table and writes it to `site/catalog.json`; carries the manifest's publish time onto version items; the reindex calls the writer after it flips.
**Files:** `packages/contract/src/archive_contract/manifest.py`, `packages/contract/tests/test_manifest.py`, `packages/web/src/schema/archive-contract.schema.json`, `packages/infra/src/generated/archive-config.ts` (if regenerated), `packages/backend/src/archive_backend/catalog_file.py`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_catalog_file.py`, `packages/backend/tests/test_reindex.py`, `docs/planning-handoff.md`
**Checks:** `uv run pytest packages/backend packages/contract` exits 0; `just check-python` exits 0; `just check-schema` exits 0.
**Serves:** DCSN1 (rests on calls AGNT2, AGNT3)

- The publish time lives in the manifest as `archive:published`, an ISO 8601 UTC datetime the archive sets at publish and nobody else writes (agreed with Plan 7 and the coordinating session, muster thread 945). If `origin/main` doesn't have it yet, add `Manifest.published: datetime | None` with alias `archive:published` to `archive_contract`, run `just schema`, and add one Decision log row; if Plan 7 landed it first, use theirs.
- `catalog_items` reads `archive:published` from the manifest it already parses and writes it as `publishedAt` on the version item. No new argument and no fallback: a manifest without it gets no `publishedAt`.
- `catalog_rows(items) -> list[dict]`: pure, from the dataset `META` items and their current version items. Row fields, each left out when the manifest lacks it: `id`, `version`, `title`, `description`, `keywords`, `access`, `licenses` (each license's `name`, else `path`), `rightsStatus`, `project`, `creators` (contributors with the `creator` role: `title`, else `givenName familyName`, else `organization`), `formats` (distinct resource formats, sorted), `start`, `end` (date, or `"unknown"`), `ongoing`, `bbox` (`[west, south, east, north]`), `bytes` (sum of the version's file items' `bytes`) and `published` (the version item's `publishedAt`). Rows sorted by `id`.
- `write_catalog_file` scans the table (paginated), builds the rows and puts `site/catalog.json` with `ContentType: application/json` and `CacheControl: max-age=60`. It returns the row count.
- In the reindex, a new checkpointed step after `flip` calls it on the table it flipped to. A failure there alerts like the other steps and does not undo the flip.
- Tests: rows from the sample package's manifest (`examples/sample-package/datapackage.json`) and from a bare manifest with only a title; a two-dataset fake table writes one object with both rows; the reindex calls the writer only when it flipped.

### Task 2: The API Lambda

**Does:** Adds `archive_backend.search` (pure filtering over catalog rows) and `archive_backend.api` (one Powertools `APIGatewayRestResolver` with validation on), the usage answers model in the contract, and a committed OpenAPI spec with a drift check.
**Files:** `packages/backend/pyproject.toml`, `uv.lock`, `packages/backend/src/archive_backend/search.py`, `packages/backend/src/archive_backend/api.py`, `packages/contract/src/archive_contract/usage.py`, `packages/backend/tests/test_search.py`, `packages/backend/tests/test_api.py`, `packages/contract/tests/test_usage.py`, `justfile`, `packages/web/src/schema/openapi.json`
**Checks:** `uv run pytest packages/backend packages/contract` exits 0; `just check-python` exits 0; `just check-schema` exits 0.
**Serves:** DCSN1, DCSN2, DCSN3, DCSN4 (rests on calls AGNT1, AGNT6, AGNT8, AGNT9, AGNT10)

Search (`search.py`, no AWS):

- `search(rows, query) -> SearchResult`, where the query holds `q`, `access`, `license`, `format`, `project` (lists), `from_`, `to` (dates), `bbox` and `page`, `size` (default 20, 1 to 100).
- Each whitespace-separated word of `q` must appear, ignoring case, in `title`, `description`, `keywords` or `creators`. A list filter keeps a row that has any of the values. Dates keep a row whose coverage overlaps the range: `end: "unknown"` or `ongoing` counts as open-ended, a row without `start` drops out when a date filter is set. The box keeps a row whose box intersects it, splitting either box at the antimeridian when west is greater than east; a row without a box drops out when a box is set.
- Order: rows with a word of `q` in the title first, then by `published` newest first with rows lacking it last, then `id`.
- The answer is `rows` (that page), `total`, and `facets`: for each of `access`, `license`, `format` and `project`, every value's count among the rows matching all the other filters (so a facet doesn't hide its own alternatives).

Routes (`api.py`), paths as API Gateway passes them:

- `GET /api/search`: query parameters as above (`from` and `to` in the URL); reads the catalog through a module-level cache that `head_object`s `site/catalog.json` at most every 60 seconds and re-reads on a new ETag.
- `GET /api/datasets/<id>`, `/api/datasets/<id>/versions`, `/api/datasets/<id>/versions/<version>`: query the active catalog table (the `/research-archive/<stage>/catalog-active` parameter, cached 60 seconds, naming `CATALOG_TABLE_A` or `CATALOG_TABLE_B`). The dataset answer is the dataset item's fields, the current version's manifest parsed as JSON, and its files; 404 when absent.
- `GET /api/projects/<id>`: `projects/<id>/project.json` from the archive bucket, and the datasets from GSI1 (`GSI1PK=PROJECT#<id>`); 404 when the file is absent.
- `GET /api/datasets/<id>/versions/<version>/download?path=`: signed in (claims present). `open` answers `{"url": "https://<SITE_DOMAIN>/data/<id>/<version>/<path>"}`; `restricted` answers a presigned `get_object` URL on `restricted/<id>/<version>/<path>` with `ExpiresIn=300` and adds 1 to `restricted` on DownloadCounts (`datasetId`, `month` as `YYYY-MM`); `by-request` answers 403; `description-only` and a path that is not one of the version's file items answer 404.
- `POST /api/datasets/<id>/usage`: body is `archive_contract.usage.UsageAnswers` (`organisation` and `purpose` each one of the spec's six values or absent, `note` up to 500 characters); 404 for an unknown dataset; stores `datasetId`, `entry` = `<YYYY-MM>#<uuid4>`, the answers and `at`; answers 204.
- `GET /api/admin/usage?dataset=`: 403 unless the claims' `cognito:groups` holds `admin` (parse as `whoami.py` does); answers that dataset's entries, newest first.
- Environment: `ARCHIVE_BUCKET`, `DERIVED_BUCKET`, `CATALOG_TABLE_A`, `CATALOG_TABLE_B`, `ACTIVE_CATALOG_PARAMETER`, `DOWNLOAD_COUNTS_TABLE`, `USAGE_TABLE`, `SITE_DOMAIN`. Handler `archive_backend.api.handler`.

OpenAPI: `python -m archive_backend.api <path>` writes `app.get_openapi_json_schema()` with sorted keys. Add `openapi_file := "packages/web/src/schema/openapi.json"`, a `just openapi` recipe that writes it, and a diff of it in `check-schema` beside the contract schema's.

Tests drive the resolver with API Gateway REST events and fakes for S3, DynamoDB and SSM: each search filter, facet counts, paging bounds, the antimeridian box, every download case above (including no claims: API Gateway refuses it, but the handler also answers 401), the usage 204 and 404, admin 403 and 200, and a 404 for each missing read.

### Task 3: The download rollup

**Does:** Adds `archive_backend.downloads.handler`, run daily, which adds CloudFront's open downloads to DownloadCounts and never counts a day twice.
**Files:** `packages/backend/src/archive_backend/downloads.py`, `packages/backend/tests/test_downloads.py`
**Checks:** `uv run pytest packages/backend` exits 0; `just check-python` exits 0.
**Serves:** none (rests on call AGNT7)

- Days to count: from the day after the Settings item `downloads-rolled-up-through` (`name`, `value` = `YYYY-MM-DD`), or from two days ago when there is none, through two days ago (UTC), since CloudFront may deliver a day's logs hours late.
- For each day, list `logs/` keys whose name holds `.<YYYY-MM-DD>-`, read each gzip file (tab-separated, `#` lines are headers), and count lines with `cs-method` `GET`, `sc-status` `200` and `cs-uri-stem` starting `/data/`; the dataset id is the next path segment.
- Add each dataset's count to `open` for that day's month with one `UpdateItem ... ADD`, then write the day to the Settings item before moving to the next day, so a crash mid-run recounts at most nothing already marked.
- An event `{"through": "YYYY-MM-DD"}` replaces two days ago as the last day, so the test deploy can count today by hand; the schedule sends none.
- Environment: `DERIVED_BUCKET`, `DOWNLOAD_COUNTS_TABLE`, `SETTINGS_TABLE`.
- Tests: a fake log with a 200 GET, a 206, a HEAD, a 404 and a non-`/data` path counts one; a second run the same day counts nothing; two missed days are both counted once.

### Task 4: The infrastructure

**Does:** Adds the internal `ReadApi` construct, created by `ResearchArchive` after the distribution: the API Lambda and its routes, the UsageResponses table, the daily rollup schedule, and the reindex's grant to write the catalog file.
**Files:** `packages/infra/src/read-api.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/src/reindex.ts`, `packages/infra/test/read-api.test.ts`, `packages/infra/test/reindex.test.ts`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0.
**Serves:** DCSN2, DCSN3, DCSN4 (rests on calls AGNT7, AGNT10)

- One Lambda from `archive.pythonFunction("ApiFunction", { handler: "archive_backend.api.handler" })` with the Task 2 environment (`SITE_DOMAIN` is the distribution's domain name).
- Routes under Plan 4's existing `/api` resource, each a `LambdaIntegration` to that one function. `download` and `admin/usage` use `AuthorizationType.COGNITO` with `archive.authorizer`; the rest `NONE`.
- UsageResponses: plain `dynamodb.Table`, partition `datasetId`, sort `entry`, on-demand, point-in-time recovery, the same removal policy as Plan 4's operational tables for prod and non-prod. Add it to the operations dashboard as Plan 4 does with its tables.
- Grants: read on both catalog tables and the active-catalog parameter; read `site/catalog.json` and the archive bucket's `restricted/*` and `projects/*`; `ADD` on DownloadCounts; read and write UsageResponses.
- The rollup: `archive.pythonFunction("DownloadRollupFunction", ...)`, timeout 15 minutes, read `logs/*`, write DownloadCounts and Settings, on an EventBridge Scheduler rate of one day with no retries, as `integrity.ts` schedules its check.
- Reindex: add `derivedBucket.grantPut(fn, "site/catalog.json")`.
- Synth tests: each route's method and authorization type, the table's keys and recovery, the schedule, and the reindex's new grant.

### Task 5: The test deploy

**Does:** Merges Tasks 1 to 4 and Task 6, deploys `ResearchArchive-test`, walks every check in the spec's "How we'll know it works" with you, measures search round trips, and destroys the stack.
**Files:** none (results go in the task's result line and the build thread)
**Checks:** every action in STEP1 is done; `aws cloudformation describe-stacks --stack-name ResearchArchive-test` fails with "does not exist" at the end.
**Serves:** DCSN1, DCSN2, DCSN3

STEP1's actions, in order:

1. You: name the AWS profile and the alert email address.
2. Agent: open the PR for Tasks 1 to 4, merge it once CI's `python` and `typescript` checks pass, and check the profile's identity.
3. You: Go for the deploy.
4. Agent: `just lambda-assets`, deploy `ResearchArchive-test` with a test `ARCHIVE_CONFIG`, upload the sample package twice with `archive:published` set (once `open`, once with `archive:access` set to `restricted`, under `restricted/`), run `just reindex test` and wait for `COMPLETED`.
5. Agent: check `/catalog.json` has both rows; `GET /api/search?q=` with a word from the description finds both, filters by `access=restricted` to one, facet counts add up; `GET /api/datasets/<id>` returns the manifest and files; the download route signed out answers 401.
6. Agent invites you with `just invite-user test <your email>`. You: open the sign-in link the agent gives (Plan 4's `cli` client with PKCE), sign in with the temporary password from the invitation email, set your own, and paste back the `localhost:8765` URL you land on, even though the page doesn't load.
7. Agent: exchange the code; the restricted download link fetches the file; DownloadCounts shows one restricted; a usage answer posts; `GET /api/admin/usage` answers 403; add your user to `admin`.
8. You: sign in again with the new link and paste back the URL.
9. Agent: `GET /api/admin/usage` answers the posted answer; download an open file through `/data`, invoke the rollup with `{"through": "<today>"}` once the log file has arrived, and check DownloadCounts shows it; time ten searches warm and one after fifteen idle minutes through CloudFront.
10. You: Go for the teardown.
11. Agent: `cdk destroy ResearchArchive-test` and confirm the stack, buckets and tables are gone.

### Task 6: Invitation-only accounts

**Does:** Turns off self-service sign-up and adds a recipe for an admin to invite a person by email, optionally into a group, so restricted data reaches only people the archive invited. Added at your word through the coordinating session; Task 5 deploys it.
**Files:** `packages/infra/src/auth.ts`, `packages/infra/test/auth.test.ts`, `justfile`, `docs/planning-handoff.md`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0.
**Serves:** DCSN2

- `selfSignUpEnabled: false` on the user pool; the synth test asserts `AdminCreateUserConfig.AllowAdminCreateUserOnly` is true.
- `just invite-user <stage> <email> [group]`: reads the user pool id from the stack's resources, runs `aws cognito-idp admin-create-user` with the email as username, `email_verified=true` and Cognito's invitation email, then `admin-add-user-to-group` when a group is given. Uses the caller's `AWS_PROFILE` and region, like `just reindex`.
- One Decision log row: accounts are invitation-only; restricted means invited.
