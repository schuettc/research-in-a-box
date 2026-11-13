---
diazo: research-archive-in-a-box/archive-infrastructure-cdk-construct
file: PLAN2
status: approved
approved: 2026-11-13T16:00:56-06:00
hash: 6097d0b91ec4afe9fe5d39b475dd919f03b7164632dc00934426a2385f052621
rests_on: [AGNT11, AGNT2, AGNT5, AGNT6, AGNT7, AGNT9]
record: README.md
---

# PLAN2: Auth, API, web and operations

## Spec

`docs/specs/2026-11-13-archive-infrastructure-cdk-construct/spec.md`, sections "Python Lambdas", "Auth", "API shell and web", "Operations and stages" (the operations half) and "Storage" (the integrity check). PLAN1 is built and merged (research-in-a-box#10). Build on what it made: `ResearchArchive` in `packages/infra/src/research-archive.ts` with `Storage` and `Tables`, the generated `ArchiveConfig` type, and `archive.yaml`. The implementer reads the spec beside this plan.

## The change

The construct gets everything else the spec's parts list except the reindex:

- **Packaging:** a just recipe packages Python Lambdas without Docker, and `pythonFunction` builds functions from them.
- **Operations:** an alert topic, a budget, failure alarms and a dashboard.
- **Auth:** a Cognito user pool with managed login and two app clients.
- **API:** a REST API with a public health route and one signed-in route, fixed throttling, and optional regional WAF.
- **Web:** one CloudFront distribution over the site, open data and the API, with standard logs.
- **Integrity check:** a weekly job. Its Python code lives in `archive-backend` with unit tests.

Everything is proven by synth and unit tests; nothing deploys.

**Risk:** local code and CI only; nothing reaches AWS in this plan, and a mistake is undone by reverting the PR. Two rules are pinned by tests so PLAN3's deploy inherits them: the prod user pool is retained with deletion protection, and the integrity check never retries on its own.

**Cost:** no steps for you. New dependencies:

- `boto3` (runtime) in `archive-backend`.
- `boto3-stubs[s3,sns]` in the root dev group, for mypy strict.
- CI's typescript job installs uv to build the Lambda assets.

No new programs on your machine.

## Left out

- The reindex function, `just reindex` and `just reindex-status`, and the test deploy (PLAN3).
- API endpoints beyond `/api/health` and `/api/whoami` (Plan 6).
- The dataset-page rewrite. The site function sends every extensionless path to the app's `index.html`; Plan 7 changes it when it writes per-dataset pages.
- Deploying the web bundle to `site/` (Plans 8 and 10a).
- An alarm on API throttling. A REST API has no separate throttle metric, so 4xx (which includes 429) is shown on the dashboard, and only 5xx alarms.
- Integrity checking at large scale. The check lists and heads every archived object weekly, which suits a small archive; S3 Inventory with checksums is a follow-up for when an archive outgrows a 15-minute run.

## Where

- Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan4/auth-api-web-and-operations`, branch `plan4/auth-api-web-and-operations` from `origin/main`. Confirm with `git -C <wt> branch --show-current` before editing.
- Python: `packages/backend/pyproject.toml`, `packages/backend/src/archive_backend/` (`health.py`, `whoami.py`, `integrity.py`), `packages/backend/tests/`, root `pyproject.toml` (dev group).
- TypeScript: `packages/infra/src/` (`python-function.ts`, `operations.ts`, `auth.ts`, `api.ts`, `web.ts`, `integrity.ts`, `research-archive.ts`), `packages/infra/test/`.
- `justfile`, `.gitignore`, `.github/workflows/ci.yml`, `docs/planning-handoff.md` (decision log).
- Global constraints: Python >=3.12 for the workspace, Lambdas on Python 3.13 arm64; ruff, mypy strict; TypeScript strict, ESM; `just check` must exit 0; nothing published; every stack keeps the `Repo` tag; prod retains data and other stages tear down cleanly (PLAN1's `isProd`).

### Task 1: Lambda packaging, pythonFunction and operations

**Does:** Adds `just lambda-assets` and `pythonFunction`, which builds an arm64 Python 3.13 Lambda from the packaged `archive-backend` with an error alarm. Adds the operations part: alert topic, monthly budget and dashboard.
**Files:** `justfile`, `.gitignore`, `.github/workflows/ci.yml`, `packages/backend/pyproject.toml`, `pyproject.toml`, `uv.lock`, `packages/infra/src/python-function.ts`, `packages/infra/src/operations.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/operations.test.ts`
**Checks:** `just lambda-assets` exits 0 and `packages/infra/assets/python/pydantic_core/` holds a `*aarch64-linux-gnu.so`; `npm test -w packages/infra` exits 0.
**Serves:** none (rests on calls AGNT2, AGNT9)

- `justfile` `lambda-assets`:
  1. Remove `packages/infra/assets/python`.
  2. `uv export --package archive-backend --no-dev --no-hashes --frozen --no-emit-workspace -o <tmp>/requirements.txt`.
  3. `uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary :all: --target packages/infra/assets/python -r <tmp>/requirements.txt`. This exact command was run against the current lock and produced `_pydantic_core.cpython-313-aarch64-linux-gnu.so`.
  4. `uv pip install --no-deps --python-version 3.13 --target packages/infra/assets/python packages/contract packages/backend`.

  `check-ts` depends on `lambda-assets`. Add `packages/infra/assets/` to `.gitignore`. CI's typescript job adds `astral-sh/setup-uv` (same pin as the python job) before `just check-ts`.
- `archive-backend` gains the dependency `boto3`, and the root dev group gains `boto3-stubs[s3,sns]`. Run `uv lock`.
- `operations.ts`: `class Operations extends Construct`, props `{ alertEmail: string; monthlyBudgetUsd: number }`:
  - `readonly alertTopic: sns.Topic`, with an email subscription to `alertEmail`.
  - A `budgets.CfnBudget`: monthly, `COST`, limit `monthlyBudgetUsd` USD. Notifications on `ACTUAL` at 80 and 100 percent (`GREATER_THAN`, `PERCENTAGE`), each emailing `alertEmail`.
  - `readonly dashboard: cloudwatch.Dashboard`, named `ResearchArchive-<stage>`.
  - `addFunction(fn: lambda.Function): void`: adds an alarm on `fn.metricErrors()` (sum ≥ 1 over 5 minutes, one period, missing data not breaching) with an SNS action on the alert topic, and adds an errors-and-duration graph for the function to the dashboard.
- `python-function.ts`: `export interface PythonFunctionProps { readonly handler: string; readonly environment?: Record<string, string>; readonly timeout?: Duration; readonly memorySize?: number }`. `handler` is a dotted path in `archive_backend`, such as `archive_backend.health.handler`.
- `ResearchArchive`:
  - Creates `Operations` from `config.infrastructure` (which the default app always supplies; throw `ResearchArchive needs config.infrastructure` if it is missing) and exposes `alertTopic`.
  - `pythonFunction(id: string, props: PythonFunctionProps): lambda.Function` makes a function in the archive's scope: `Runtime.PYTHON_3_13`, `Architecture.ARM_64`, `Code.fromAsset(<packages/infra/assets/python>)`, timeout default 30 seconds, memory default 512, and a log group with one-month retention, removed with the stack unless prod. It calls `operations.addFunction`.
  - Synth throws `run just lambda-assets first` when the asset folder is missing.

Tests in `operations.test.ts`:

- `the alert topic emails the configured address`.
- `the budget is monthly, at the configured limit, and alerts at 80 and 100 percent`.
- `pythonFunction makes an arm64 Python 3.13 function with an errors alarm on the alert topic`.
- `there is one dashboard per stage`.

Commit: `Package Python Lambdas and add operations defaults`

### Task 2: The health and whoami handlers, and the integrity check code

**Does:** Adds the Python handlers for `/api/health` and `/api/whoami` and the integrity check's logic, each with unit tests and no AWS.
**Files:** `packages/backend/src/archive_backend/health.py`, `whoami.py`, `integrity.py`, `packages/backend/tests/test_health.py`, `test_whoami.py`, `test_integrity.py`
**Checks:** `uv run pytest packages/backend` exits 0; `just check-python` exits 0.
**Serves:** none (rests on calls AGNT5, AGNT7)

- `health.handler(event: dict[str, Any], context: object) -> dict[str, Any]`: returns `{"statusCode": 200, "headers": {"content-type": "application/json"}, "body": "{\"status\": \"ok\"}"}`.
- `whoami.handler(event, context)`: reads `event["requestContext"]["authorizer"]["claims"]` and returns 200 with a JSON body `{"sub": ..., "email": ..., "groups": [...]}`. `groups` comes from `cognito:groups` (absent means `[]`).
- `integrity.py`. Archived package layout (recorded in the decision log in Task 4): each published version sits at `<open|restricted>/<datasetId>/<version>/`, with `checksums.sha256` at its root in `sha256sum` format (`<hex>  <relative path>`, as `examples/sample-package/checksums.sha256` shows). Each object is written in one PUT with a full-object SHA-256 checksum.
  - `@dataclass(frozen=True) class Problem: key: str; kind: Literal["mismatch", "missing", "no-checksum"]`.
  - `check_archive(s3: S3Client, bucket: str) -> list[Problem]`:
    1. Find every `checksums.sha256` under `open/` and `restricted/` with the `list_objects_v2` paginator.
    2. For each line, `head_object(..., ChecksumMode="ENABLED")` on the version folder plus the relative path.
    3. A 404 is `missing`. An absent `ChecksumSHA256`, or a composite one (it contains `-`), is `no-checksum`. A base64-decoded value that differs from the line's hex is `mismatch`.
  - `handler(event, context)`: runs `check_archive` on `ARCHIVE_BUCKET`. When there are problems, it publishes one message to `ALERT_TOPIC_ARN`: subject `Archive integrity check: <n> problems`, body the first 50 as `<kind> <key>` lines. It returns `{"checked": <objects>, "problems": <n>}` and never raises for problems found. A raise would make Lambda's async invoke retry the whole scan.
  - Type the client as `mypy_boto3_s3.S3Client` and create it in the handler.
- Tests use a small in-memory fake implementing `get_paginator("list_objects_v2")`, `get_object` and `head_object`, not moto:
  - `test_matching_objects_have_no_problems`.
  - `test_changed_object_is_a_mismatch`.
  - `test_listed_file_that_is_gone_is_missing`.
  - `test_object_without_a_full_sha256_is_no_checksum` (absent, and composite `abc-2`).
  - `test_handler_alerts_only_when_there_are_problems` (fake SNS records publishes).
  - `test_health_answers_ok`.
  - `test_whoami_returns_sub_email_and_groups`.

Commit: `Add the health, whoami and integrity check handlers`

### Task 3: Auth, the API shell and the integrity schedule

**Does:** Adds the Cognito user pool with groups and managed login, and the REST API (`/api/health` public, `/api/whoami` behind the Cognito authorizer, fixed throttling, optional regional WAF). Schedules the integrity check weekly.
**Files:** `packages/infra/src/auth.ts`, `packages/infra/src/api.ts`, `packages/infra/src/integrity.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/auth.test.ts`, `packages/infra/test/api.test.ts`
**Checks:** `npm test -w packages/infra` exits 0.
**Serves:** none (rests on calls AGNT5, AGNT7, AGNT11)

- `auth.ts`: `class Auth extends Construct`, props `{ stage: string; isProd: boolean }`:
  - `readonly userPool`: self sign-up, sign-in with email, email auto-verified, account recovery by email. Prod: `RETAIN` and `deletionProtection: true`; other stages: `DESTROY`.
  - Groups `contributor`, `curator`, `admin` (`CfnUserPoolGroup`).
  - A Cognito domain with prefix `archive-<stage>-<account>` and `managedLoginVersion: NEWER_MANAGED_LOGIN`.
  - `addAppClients(siteDomain: string): { web: UserPoolClient; cli: UserPoolClient }`: both use authorization code with PKCE, no client secret, and scopes `openid email profile`.
    - `web`: callback `https://<siteDomain>/auth/callback`, logout `https://<siteDomain>/`.
    - `cli`: callback `http://localhost:8765/callback`.
    - Each gets a `CfnManagedLoginBranding` with `useCognitoProvidedValues: true`, since managed login shows no page for a client without one.
- `api.ts`: `class Api extends Construct`, props `{ userPool; waf: boolean; health: lambda.Function; whoami: lambda.Function }`:
  - `readonly restApi: apigateway.RestApi`, with a regional endpoint and deploy options `throttlingRateLimit: 50`, `throttlingBurstLimit: 100`, metrics on.
  - `readonly authorizer: apigateway.CognitoUserPoolsAuthorizer`.
  - Resources `api/health` (`GET`, no auth) and `api/whoami` (`GET`, Cognito authorizer). The whoami route exists because CDK refuses an authorizer attached to no method, and it lets PLAN3 prove a signed-in call end to end.
  - When `waf`: a `CfnWebACL` (scope `REGIONAL`, default allow) with `AWSManagedRulesCommonRuleSet`, `AWSManagedRulesKnownBadInputsRuleSet` and `AWSManagedRulesAmazonIpReputationList`, associated with the API's deployment stage.
- `integrity.ts`: `class IntegrityCheck extends Construct`:
  - Makes the function with `pythonFunction` (`archive_backend.integrity.handler`, timeout 15 minutes, environment `ARCHIVE_BUCKET` and `ALERT_TOPIC_ARN`) and grants it read on the archive bucket and publish on the topic.
  - Schedules it with `scheduler.Schedule`, `ScheduleExpression.rate(Duration.days(7))`, target `LambdaInvoke` with `retryAttempts: 0`.
  - Sets the function's async invoke config to `retryAttempts: 0`.
- `ResearchArchive` exposes `userPool`, `userPoolClients`, `api` (the `RestApi`) and `authorizer`. It wires the WAF switch from `config.infrastructure.modules.waf`.

Tests:

- `the user pool signs in with email and has contributor, curator and admin groups`.
- `managed login is the newer version, and each client has branding`.
- `both app clients use code with PKCE and no secret, with the site and localhost callbacks`.
- `the prod user pool is retained with deletion protection; a dev stage's is not`.
- `health is public and whoami uses the Cognito authorizer`.
- `the stage throttles at 50 per second with a burst of 100`.
- `WAF appears only when modules.waf is true, associated with the API stage`.
- `the integrity check runs weekly with no retries`.

Commit: `Add Cognito, the API shell and the weekly integrity check`

### Task 4: CloudFront

**Does:** Adds one distribution: the default behaviour is the derived bucket's `site/` with an index fallback; `/data/*` is the archive bucket's `open/` at stable URLs; `/api/*` is the REST API, uncached. It writes standard logs to the derived bucket's `logs/`, wires the web app client's callbacks to its domain and records the cross-plan facts.
**Files:** `packages/infra/src/web.ts`, `packages/infra/src/storage.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/web.test.ts`, `docs/planning-handoff.md`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0; `npx cdk synth -q` in `packages/infra` exits 0.
**Serves:** none (rests on calls AGNT6, AGNT11)

- `storage.ts`: the derived bucket gets `objectOwnership: BUCKET_OWNER_PREFERRED`. CloudFront's standard logs are delivered with an ACL, which a bucket that enforces the owner refuses. Public access stays fully blocked.
- `web.ts`: `class Web extends Construct`, props `{ derivedBucket; archiveBucket; restApi }`, with `readonly distribution: cloudfront.Distribution`:
  - Default behaviour: `S3BucketOrigin.withOriginAccessControl(derivedBucket, { originPath: "/site" })`, redirect to HTTPS, cache optimized. A viewer-request CloudFront Function rewrites a URI whose last segment has no `.` to `/index.html`, and one ending in `/` to `<uri>index.html`. `defaultRootObject: "index.html"`.
  - `/data/*`: `S3BucketOrigin.withOriginAccessControl(archiveBucket, { originPath: "/open" })`, with a viewer-request function stripping the leading `/data`. A request for `/data/<datasetId>/<version>/<path>` reads `open/<datasetId>/<version>/<path>`. Cache optimized, GET and HEAD only.
  - `/api/*`: `RestApiOrigin(restApi)`, all methods, `CACHING_DISABLED`, `ALL_VIEWER_EXCEPT_HOST_HEADER` origin request policy.
  - No distribution-wide error responses, so a missing data file or an API 404 stays a 404.
  - Logging on, to `derivedBucket` with prefix `logs/`.
- `ResearchArchive` exposes `distribution` and calls `auth.addAppClients(distribution.distributionDomainName)` after creating it.
- Decision log lines (today's date), added to `docs/planning-handoff.md`:
  - Plans 4 and 7: an archived version lives at `<open|restricted>/<datasetId>/<version>/` with `checksums.sha256` at its root. Every object is written in one PUT with a full-object SHA-256 checksum, which the weekly integrity check compares. Open files are served at `/data/<datasetId>/<version>/<path>` on the CloudFront domain. A metadata edit that rewrites `datapackage.json` or `README.md` in place must rewrite `checksums.sha256` too, or the weekly check alerts. Changing a dataset's access level moves it between `open/` and `restricted/`, so its `/data` URL changes; Plan 7 owns both.
  - Plans 4, 6 and 9: the API lives under `/api/*` on the CloudFront domain. Two Cognito app clients use code with PKCE and no secret: `web` (callback `/auth/callback`) and `cli` (callback `http://localhost:8765/callback`, which Plan 6 may change when it designs the CLI and MCP sign-in). Roles are the Cognito groups `contributor`, `curator` and `admin`.
  - Plans 4 and 7: the site's CloudFront Function sends extensionless paths to `/index.html`; Plan 7 changes it when it writes per-dataset pages.

Tests:

- `the default behaviour serves site/ from the derived bucket through origin access control`.
- `/data/* serves open/ from the archive bucket and strips /data`.
- `/api/* goes to the REST API uncached with all methods`.
- `the distribution has no error responses`.
- `standard logs go to the derived bucket under logs/, and the derived bucket accepts the log ACL`.
- `the web client's callback is on the distribution's domain`.

Commit: `Add CloudFront for the site, open data and the API`

The implementer stops after Task 4's commit. The Plan 4 planning session (which dispatched the implementer) pushes the branch, opens the PR and merges it once CI passes on it.
