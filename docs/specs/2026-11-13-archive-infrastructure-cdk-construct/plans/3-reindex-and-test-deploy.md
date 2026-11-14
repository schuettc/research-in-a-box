---
diazo: research-archive-in-a-box/archive-infrastructure-cdk-construct
file: PLAN3
status: done
approved: 2026-11-13T16:31:09-06:00
hash: 73556a3c44e81618d678d419dcbf3cf97cdc4a37bf200165dbf8c8dfd97666a2
rests_on: [AGNT10, AGNT8, DCSN1, DCSN2, DCSN3, DCSN4]
record: README.md
---

# PLAN3: Reindex and the test deploy

## Spec

`docs/specs/2026-11-13-archive-infrastructure-cdk-construct/spec.md`, sections "Reindex", "Risk and cost" and "How we'll know it works". PLAN1 (research-in-a-box#10) and PLAN2 (research-in-a-box#12) are built and merged. Build on their code: `ResearchArchive`, `pythonFunction`, `catalogTables` with `activeCatalogParameter`, `derivedBucket`, `archiveBucket` and `alertTopic`. The implementer reads the spec beside this plan.

## The change

The reindex is a Python durable function in the construct. It:

1. Empties the inactive catalog table.
2. Turns every published manifest in the archive bucket into line-delimited DynamoDB JSON under the derived bucket's `reindex/<run>/`.
3. Bulk-loads that into the inactive table and waits for the load to end.
4. Flips the active-catalog parameter only when the load ends `COMPLETED`.

An admin starts it with `just reindex <stage>` and follows it with `just reindex-status <stage>`. Then one test deploy, a stage named `test` in your AWS account, walks every check in the spec's "How we'll know it works" and is destroyed.

**Risk:**

- Tasks 1 and 2 are local code and CI; a mistake is undone by reverting the PR.
- Task 3 creates real resources in one AWS account you choose, under a non-prod stage, so every bucket, table and user pool deletes with the stack. A mistake there costs a few dollars at most, and `cdk destroy` undoes it.
- Nothing touches a prod stage; none exists.

**Cost:**

- One walkthrough step for you (STEP1). You name the AWS profile and alert address, approve the deploy, confirm the alert email subscription, sign up once in the browser and paste back one URL, then approve the teardown.
- New dependency: `aws-durable-execution-sdk-python==3.0.2` in `archive-backend`.
- No new programs on your machine; the AWS CLI is already installed.

## Left out

- Projects in the catalog. Where a project record lives in the archive bucket is Plan 7's to decide, so reindex loads datasets, versions and files only (follow-up PARK6).
- Catching up packages published during a reindex (follow-up PARK5).
- Reindex from `cruise` (follow-up PARK1).
- A prod deploy, a CI deploy and the deployment skill (Plan 10a).
- Testing write-once locking and WAF on the test deploy. Both stay synth-tested; locked objects can't be removed by a clean teardown, and WAF needs no outside credentials to synth.

## Where

- Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan4/reindex-and-test-deploy`, branch `plan4/reindex-and-test-deploy` from `origin/main`. Confirm with `git -C <wt> branch --show-current` before editing.
- Python: `packages/backend/pyproject.toml`, `uv.lock`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_reindex.py`.
- TypeScript: `packages/infra/src/python-function.ts`, `packages/infra/src/reindex.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/bin/app.ts`, `packages/infra/vitest.config.ts`, `packages/infra/test/reindex.test.ts`, `packages/infra/test/app.test.ts`.
- `justfile`, `docs/planning-handoff.md` (decision log).
- Global constraints:
  - Lambdas are Python 3.13 on arm64; `just check` must exit 0.
  - Nothing reaches AWS in Tasks 1 and 2.
  - Task 3 runs only with your Go on STEP1, under the profile you name, never against a stage named `prod`.
  - On any AWS auth error, stop and report; never copy or export credentials.

### Task 1: The reindex function

**Does:** Adds `archive_backend.reindex`. Plain functions turn manifests into DynamoDB JSON lines; a durable handler runs the empty, write, load, wait and flip as checkpointed steps and alerts on a bad outcome. All of it is unit-tested with fakes.
**Files:** `packages/backend/pyproject.toml`, `uv.lock`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_reindex.py`
**Checks:** `uv run pytest packages/backend` exits 0; `just check-python` exits 0.
**Serves:** DCSN1, DCSN3 (rests on calls AGNT8, AGNT10)

Add `aws-durable-execution-sdk-python==3.0.2` to `archive-backend` and run `uv lock`. The package needs `boto3>=1.43.114`; the lock has 1.44.3.

Archive layout, from the decision log: a published version sits at `<open|restricted>/<datasetId>/<version>/` with `datapackage.json` at its root.

Catalog items (catalog keys from the spec; attributes beyond the keys are Plan 4's first cut, which Plan 6 may extend). Every value is a DynamoDB JSON string unless noted.

- **Dataset:** `PK=DATASET#<id>`, `SK=META`, `id`, `title`, `access` (from `archive:access`, default `open`), `currentVersion` (number, the highest version found), `prefix` (`open` or `restricted`, of the current version). When `archive:project` is set: `project`, `GSI1PK=PROJECT#<project>` and `GSI1SK=DATASET#<id>`.
- **Version:** `PK=DATASET#<id>`, `SK=V#<version zero-padded to 6>`, `version` (number), `prefix`, `manifest` (the `datapackage.json` text as one string).
- **File:** `PK=DATASET#<id>`, `SK=V#<version padded>#FILE#<path>`, `path`, `name` (resource name), and `format`, `bytes` (number) and `hash` when the resource has them. One item per resource `path`, plus one per member of `archive:files` when a resource lists them.

Functions:

- `catalog_items(prefix: str, dataset_id: str, version: int, manifest_text: str) -> list[dict[str, Any]]`: the version item and its file items, as DynamoDB JSON maps (`{"S": ...}`, `{"N": ...}`).
- `dataset_item(versions: list[tuple[str, int, dict[str, Any]]]) -> dict[str, Any]`: given `(prefix, version, manifest)` for every version of one dataset, the dataset item for the highest version.
- `to_lines(items: list[dict[str, Any]]) -> str`: one `{"Item": {...}}` per line, newline-terminated, the bulk put items input format.
- `manifest_keys(s3, bucket: str) -> list[str]`: every key ending `/datapackage.json` exactly three segments under `open/` or `restricted/`, sorted.

`@durable_execution def handler(event: dict[str, Any], context: DurableContext) -> dict[str, Any]` reads `ARCHIVE_BUCKET`, `DERIVED_BUCKET`, `CATALOG_TABLE_A`, `CATALOG_TABLE_B`, `ACTIVE_CATALOG_PARAMETER` and `ALERT_TOPIC_ARN`. It does only these, each as a named `context.step`:

1. `start`: return `{"run": <UTC timestamp YYYYMMDDTHHMMSSZ>, "active": <parameter value>}`. The target is the other table (`A` loads `B`, and back).
2. `empty`, repeated: each step scans one page of the target table (projection `PK, SK`), deletes it with `batch_write_item` in groups of 25, retrying unprocessed items, and returns the `LastEvaluatedKey` (or `None` when done).
3. `list`: return `manifest_keys`.
4. `write-<n>`: for each batch of 200 keys, read the manifests, write `reindex/<run>/data/part-<n:05d>.json` with `to_lines`, and return the item count. Group keys by dataset id first, so a dataset's item is written in the batch holding its versions; a batch boundary never splits a dataset.
5. `load`: `start_bulk_put_items` into the target table with input `{S3Bucket: DERIVED_BUCKET, S3KeyPrefix: "reindex/<run>/data/", InputFormat: "DYNAMODB_JSON"}`, output `{S3Bucket: DERIVED_BUCKET, S3KeyPrefix: "reindex/<run>/report/", OutputType: ["ERROR"]}`, `PerformanceTier: "STANDARD"` and `ClientToken` = the run. Return the operation ARN. With no manifests, skip the load and treat it as `COMPLETED`.
6. `wait_for_condition` named `wait-load`: the check describes the operation and returns `{"status", "processed", "failed"}`. The strategy stops once the status is not `IN_PROGRESS` or `CANCELLING`, else waits `min(30 * attempt, 300)` seconds.
7. On `COMPLETED`, a step `flip` writes the target letter to the parameter (overwrite). On anything else, a step `alert` publishes `Reindex <run> on <target> ended <status>` with the report prefix to the alert topic, and the parameter is left alone.
8. Return `{"run", "target", "status", "items", "flipped": bool}`.

Tests use fake S3, DynamoDB, SSM and SNS clients and a `FakeContext` whose `step(func, name)` calls `func(None)` and whose `wait_for_condition` loops the check until the strategy stops, recording each step name. The handler takes its clients from a module function `clients()` that the tests monkeypatch.

- `test_catalog_items_for_the_sample_package`: `examples/sample-package/datapackage.json` as version 1 under `open` yields one version item with the manifest text, and one file item per resource path and per `archive:files` member, each with its `format`, `bytes` and `hash` where present.
- `test_dataset_item_takes_the_highest_version_and_its_prefix`: versions 1 (`open`) and 2 (`restricted`) give `currentVersion` 2 and `prefix` `restricted`.
- `test_dataset_item_has_gsi1_only_with_a_project`.
- `test_to_lines_is_one_item_per_line`: each line parses as `{"Item": {...}}`.
- `test_manifest_keys_skips_nested_and_other_prefixes`: `open/a/1/datapackage.json` is kept; `open/a/1/docs/datapackage.json` and `staging/a/1/datapackage.json` are not.
- `test_reindex_loads_the_inactive_table_and_flips_on_completed`: active `A`, the load targets table B, and the parameter ends `B`.
- `test_reindex_empties_the_target_before_loading`: target items present before the run are deleted, and `empty` runs before `load`.
- `test_reindex_does_not_flip_and_alerts_on_completed_with_errors`: also for `FAILED`.
- `test_reindex_with_no_packages_flips_to_an_empty_table`.

Commit: `Add the reindex durable function`

### Task 2: The reindex in the construct, the just recipes and a test-stage config

**Does:** Adds the reindex as a durable function with a `live` alias, its permissions and a stack output. Adds `just reindex` and `just reindex-status`. Lets the default app read another config file through `ARCHIVE_CONFIG`, raises the infra test timeout, and records the reindex facts in the decision log.
**Files:** `packages/infra/src/python-function.ts`, `packages/infra/src/reindex.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/bin/app.ts`, `packages/infra/vitest.config.ts`, `packages/infra/test/reindex.test.ts`, `packages/infra/test/app.test.ts`, `justfile`, `docs/planning-handoff.md`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0; `npx cdk synth -q` in `packages/infra` exits 0.
**Serves:** DCSN3 (rests on calls AGNT8, AGNT10)

- `PythonFunctionProps` gains `readonly durableConfig?: lambda.DurableConfig`, passed through. Plan 7's durable functions use the same helper.
- `reindex.ts`: `class Reindex extends Construct`, props `{ archive: ResearchArchive }`:
  - The function comes from `archive.pythonFunction("ReindexFunction", { handler: "archive_backend.reindex.handler", timeout: Duration.minutes(15), memorySize: 1024, durableConfig: { executionTimeout: Duration.hours(12), retentionPeriod: Duration.days(30) }, environment: {...} })`. The environment holds the six names Task 1 reads.
  - `readonly alias = new lambda.Alias(this, "Live", { aliasName: "live", version: fn.currentVersion })`. Durable functions are invoked only through a version or alias.
  - Grants:
    - read on the archive bucket;
    - read and write on the derived bucket's `reindex/*`;
    - read and write data on both catalog tables;
    - read and write on the active-catalog parameter;
    - publish on the alert topic;
    - `dynamodb:StartBulkOperation` on `*` (account-scoped, per AWS);
    - `dynamodb:BulkPutItems` and `dynamodb:DescribeBulkOperation` on both catalog table ARNs and `<table ARN>/bulk-operation/*`.

    Task 3's deploy proves these grants against the real service; if an action name differs, Task 3 fixes it with the error text as its evidence.
  - `new CfnOutput(Stack.of(this), "ReindexFunction", { key: "ReindexFunction", value: alias.functionArn })`.
- `ResearchArchive` creates `Reindex` last and exposes `reindexFunction` (the alias).
- `bin/app.ts`: the config path is `process.env.ARCHIVE_CONFIG ?? <repo root>/archive.yaml`, so a test stage needs no edit to `archive.yaml`.
- `vitest.config.ts` in `packages/infra`: `testTimeout: 30_000`. On research-in-a-box#12's CI run, the infra test files took 3.7 to 7.0 seconds each against a 5-second per-test default.
- `justfile`:
  - `reindex stage`: reads the `ReindexFunction` output of `ResearchArchive-<stage>` with `aws cloudformation describe-stacks`, then `aws lambda invoke --invocation-type Event --function-name <alias ARN> --payload '{}' --cli-binary-format raw-in-base64-out /dev/null`. It prints `reindex started on <stage>; follow it with just reindex-status <stage>`.
  - `reindex-status stage`: `aws lambda list-durable-executions-by-function --function-name <alias ARN> --max-items 1`, then `aws lambda get-durable-execution` on its ARN, printing the status and the result.
  - Both use the caller's `AWS_PROFILE` and region as set in their shell.
- Decision log (today's date), added to `docs/planning-handoff.md`:
  - Plans 4, 6 and 7: catalog items as listed in Task 1.
  - Plans 4 and 7: reindex loads datasets, versions and files from manifests only; projects join once Plan 7 decides where project records live in the archive bucket.
  - Plans 4, 7 and 10a: `pythonFunction` takes `durableConfig`; durable functions are invoked through a `live` alias, never unqualified. `ARCHIVE_CONFIG` points the default app at another config file.

Tests in `test/reindex.test.ts` (with `testApp()`):

- `the reindex function is durable with a 12-hour execution timeout`.
- `it is invoked through a live alias, which the ReindexFunction output names`.
- `it may start bulk operations and bulk-load both catalog tables`.
- `its environment names both catalog tables, the active-catalog parameter, both buckets and the alert topic`.

In `test/app.test.ts`: `ARCHIVE_CONFIG points the default app at another config file` (a temp file with stage `test` gives stack `ResearchArchive-test`).

Commit: `Add the reindex to the construct with its just recipes`

After Task 2's commit, the implementer stops. The Plan 4 planning session runs the final review, pushes, opens the PR and merges it once CI passes, before Task 3.

### Task 3: The test deploy

**Does:** Deploys a `test` stage from main to your AWS account and walks every check in the spec's "How we'll know it works" against it. Fixes what the live run shows, then destroys the stack. This is one walkthrough step for you, STEP1, with the agent's actions between yours.
**Files:** a test config at `~/.local/state/plans/plan4-3-reindex-and-test-deploy/test.yaml`, outside the repo. Repo files change only if a check fails, through a fix PR.
**Checks:** each walkthrough action records its result. `cdk destroy` exits 0, and `aws cloudformation describe-stacks --stack-name ResearchArchive-test` then reports that the stack does not exist.
**Serves:** DCSN1, DCSN2, DCSN3, DCSN4 (rests on calls AGNT8, AGNT10)

The test config is `archive.yaml`'s catalog settings, with `infrastructure.alertEmail` set to the address you give, `stages: [{name: test, account: <your account id>, region: <region>}]`, and no modules.

STEP1's actions, in order:

1. You: name the AWS profile and the alert address (Ready).
2. Agent: `aws sts get-caller-identity` under that profile, then `cdk bootstrap` if the account and region have no `CDKToolkit` stack. STEP1's how says that a bootstrap leaves the `CDKToolkit` stack and its bucket in the account after the teardown, which is normal and shared by any CDK app there.
3. You: Go for the deploy.
4. Agent: `just lambda-assets`, then `ARCHIVE_CONFIG=<test.yaml> npx cdk deploy ResearchArchive-test --require-approval never`.
5. You: confirm the SNS subscription email (Done).
6. Agent:
   - `curl` of `https://<distribution>/api/health` returns 200 with `{"status": "ok"}`.
   - A burst of 400 concurrent requests shows at least one 429.
   - An object put with `aws s3 cp --checksum-algorithm SHA256` under `open/sample/1/` downloads from `/data/sample/1/...` with the same bytes.
   - A put under `restricted/` returns 403 from `/data/...`.
7. You: open the authorize URL the agent gives, for the `cli` client with a PKCE challenge. Sign up with email, then paste back the `http://localhost:8765/callback?code=...` URL from the address bar. The page there won't load; that's expected.
8. Agent: exchanges the code at `/oauth2/token`, and `curl` of `/api/whoami` with the ID token returns your email and `groups: []`.
9. Agent:
   - Uploads the sample package as `open/stream-temperature-sample/1/`, and a copy with a second id as `open/second-sample/1/`, every object with `--checksum-algorithm SHA256`.
   - Runs `just reindex test`, then `just reindex-status test` until it ends.
   - Expects `COMPLETED`, the active-catalog parameter flipped to `B`, and two dataset items in catalog table B.
10. Agent:
    - Invokes the integrity function by hand: `problems: 0`.
    - Overwrites one archived file with different bytes and invokes it again: one `mismatch`, and the alert email arrives.
11. You: Go for the teardown.
12. Agent: `ARCHIVE_CONFIG=<test.yaml> npx cdk destroy ResearchArchive-test --force`, then confirms the stack, its buckets and its tables are gone.

A failing check stops the walk. The fix is a new commit on a branch, with a test that reproduces it where one can, merged by PR. Then the agent redeploys and repeats that action.
