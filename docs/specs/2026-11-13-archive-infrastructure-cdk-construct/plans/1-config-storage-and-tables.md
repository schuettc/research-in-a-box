---
diazo: research-archive-in-a-box/archive-infrastructure-cdk-construct
file: PLAN1
status: done
approved: 2026-11-13T15:39:26-06:00
hash: e3ea944d0007b976571def108ed82035055a9449669c44ee48a1a49cc4d3f2ff
rests_on: [AGNT1, AGNT10, AGNT12, AGNT4, AGNT5, AGNT7, AGNT9, DCSN1, DCSN2, DCSN4]
record: README.md
---

# PLAN1: Config, storage and tables

## Spec

`docs/specs/2026-11-13-archive-infrastructure-cdk-construct/spec.md`, sections "The parts", "Storage", "Tables", "Config and the construct's interface" and "Operations and stages" (the stages half). The implementer reads the spec beside this plan.

## The change

The archive config gains an `infrastructure` section in the Python contract. Its JSON Schema generates the construct's TypeScript props type, under the existing drift check. The default app reads the committed `archive.yaml`, validates it, and makes one stack per stage. Each stack holds a `ResearchArchive` with its storage (staging, archive and derived buckets, optional write-once locking) and its tables (catalog A and B, the active-catalog parameter, five operational tables). It is proven by Python tests and vitest synth tests, with no deploy.

**Risk:** local code and CI only; nothing reaches AWS in this plan. A mistake is undone by reverting the PR. The stage rules (prod retains its data) are pinned by tests now so the first deploy in PLAN3 inherits them.

**Cost:** no steps for you. New npm dependencies in `packages/infra`: `yaml` and `ajv` (runtime of the default app) and `json-schema-to-typescript` (dev). No new programs.

## Left out

- Python Lambda packaging and `pythonFunction`, the health route, auth, the API, CloudFront, operations and the integrity check (PLAN2).
- The reindex function and its just recipes, and the test deploy (PLAN3).
- API throttling settings in the config: PLAN2 uses fixed defaults unless a real need appears.
- Teardown of a non-prod stage with write-once locking on (locked objects can't be auto-deleted): follow-up if an adopter turns locking on in dev.

## Where

- Worktree: `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan4/config-storage-and-tables`, branch `plan4/config-storage-and-tables`, from `origin/main`. Confirm with `git -C <wt> branch --show-current` before editing.
- Python: `packages/contract/src/archive_contract/config.py`, `packages/contract/tests/test_config.py`.
- Config: `archive.yaml` at the repo root (new), the one file a fork edits.
- TypeScript: `packages/infra/bin/app.ts`, `packages/infra/src/` (`research-archive.ts`, `storage.ts`, `tables.ts`, `config.ts`, `generated/archive-config.ts`), `packages/infra/scripts/generate-config-type.ts`, `packages/infra/test/`.
- `justfile` (`schema`, `check-schema`), `packages/web/src/schema/archive-contract.schema.json` (regenerated).
- Global constraints: Python >=3.12, ruff, mypy strict; TypeScript strict per `tsconfig.base.json`, ESM; `just check` is the gate and must exit 0; nothing published; every stack keeps the `Repo` tag `schuettc/research-in-a-box`.

### Task 1: The infrastructure section of the archive config

**Does:** Adds the `infrastructure` section to `ArchiveConfig`, commits the root `archive.yaml`, and regenerates the JSON Schema.
**Files:** `packages/contract/src/archive_contract/config.py`, `packages/contract/tests/test_config.py`, `archive.yaml`, `packages/web/src/schema/archive-contract.schema.json`
**Checks:** `uv run pytest packages/contract/tests/test_config.py` exits 0; `just check-python check-schema` exits 0.
**Serves:** DCSN2, DCSN4 (rests on calls AGNT1, AGNT9)

Models in `config.py`, each refusing unknown keys (`model_config = ConfigDict(extra="forbid")` on top of `ArchiveModel`), so a typo in this section fails validation:

- `Stage`: `name: str` matching `^[a-z][a-z0-9-]{0,19}$`; `account: str | None` matching `^[0-9]{12}$`; `region: str | None`.
- `ObjectLock`: `retention_days: PositiveInt`, alias `retentionDays`.
- `Modules`: `waf: bool = False`; `object_lock: ObjectLock | None = None`, alias `objectLock`.
- `Infrastructure`: `stages: list[Stage]`, default `[Stage(name="prod")]`, at least one, names unique; `alert_email: str`, alias `alertEmail`, required; `monthly_budget_usd: PositiveInt = 50`, alias `monthlyBudgetUsd`; `modules: Modules = Modules()`.
- `ArchiveConfig.infrastructure: Infrastructure | None = None`. It stays optional so `cruise` keeps working with catalog-only configs; the default app requires it (Task 2).

Tests, added to `test_config.py`:

- `test_infrastructure_reads_from_yaml`: a YAML with `alertEmail`, `monthlyBudgetUsd: 80`, two stages (one with `account: "123456789012"`, `region: us-east-2`) and `modules: {waf: true, objectLock: {retentionDays: 3650}}` loads through `load_config` with those values.
- `test_infrastructure_defaults_to_prod_only`: `Infrastructure(alertEmail="a@b.c")` has one stage named `prod`, budget 50, WAF off, no object lock.
- `test_infrastructure_refuses_unknown_keys`: `modules: {wafs: true}` raises `ValidationError`.
- `test_infrastructure_refuses_duplicate_stage_names` and `test_stage_refuses_bad_names_and_accounts` (`Prod`, `123`).
- `test_root_archive_yaml_is_valid`: `load_config(<repo root>/archive.yaml)` succeeds and has an infrastructure section.

`archive.yaml` at the root: `publisher: Invented Research Cooperative`, `profiles: [core, ecology]`, and an `infrastructure` section with `alertEmail: archive-admin@example.org`, `monthlyBudgetUsd: 50`, `stages: [{name: prod}]` and no modules. A comment line at the top says this is the one file a fork edits. Regenerate the schema with `just schema`.

Commit: `Add the infrastructure section to the archive config`

### Task 2: Generated config type and the default app

**Does:** Generates the TypeScript `ArchiveConfig` type from the committed schema under the drift check. Makes the default app read and validate `archive.yaml` and build one stack per stage, with `ResearchArchive` taking typed props.
**Files:** `packages/infra/scripts/generate-config-type.ts`, `packages/infra/src/generated/archive-config.ts`, `packages/infra/src/config.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/bin/app.ts`, `packages/infra/test/app.test.ts`, `packages/infra/package.json`, `justfile`
**Checks:** `npm test -w packages/infra` exits 0; `npm run typecheck -w packages/infra` exits 0; `just check-schema` exits 0, and exits non-zero after a field is added to `Infrastructure` in Python without regenerating (try it, then revert).
**Serves:** DCSN2, DCSN4 (rests on call AGNT9)

- `scripts/generate-config-type.ts <schema> <out>`: reads `packages/web/src/schema/archive-contract.schema.json`, compiles `{ ...$defs.ArchiveConfig, $defs }` with json-schema-to-typescript (banner says generated, do not edit), and writes `src/generated/archive-config.ts`, then formats it with prettier. The exported names include `ArchiveConfig`, `Infrastructure`, `Stage`, `Modules`.
- `justfile`: `schema` also runs the generator (`npx tsx packages/infra/scripts/generate-config-type.ts ...`). `check-schema` also regenerates the TypeScript to a temp file and diffs it against `src/generated/archive-config.ts`. CI's python job already runs `check-schema`, so add `actions/setup-node` with `npm ci` to that job.
- `src/config.ts`: `loadArchiveConfig(path: string): ArchiveConfig` parses YAML with `yaml` and validates with ajv against the committed schema's `ArchiveConfig` definition. On failure it throws an error listing ajv's messages. It throws `archive.yaml needs an infrastructure section` when that section is missing.
- `src/research-archive.ts`: `export interface ResearchArchiveProps { readonly config: ArchiveConfig; readonly stage: string }`. The constructor throws `stage "<name>" is not in infrastructure.stages` for an unknown stage, and keeps `readonly isProd = stage === "prod"` for the parts.
- `bin/app.ts`: `createApp(configPath = <repo root>/archive.yaml): App` makes, for each stage, `new Stack(app, \`ResearchArchive-${name}\`, { env })`, with `env` set only when the stage names an account or region, and one `ResearchArchive` in it. It keeps the `Repo` tag. `STACK_NAME` is replaced by `stackName(stage: string): string`.

Tests in `test/app.test.ts`, writing temp YAML files for the variants:

- `the default app makes ResearchArchive-prod from the committed archive.yaml, with the Repo tag`.
- `a second stage makes a second stack` (stages `prod` and `dev`).
- `a stage with an account and region sets the stack's environment`.
- `a config with no infrastructure section is refused with a clear message`.
- `a typo in modules is refused` (`wafs: true`).
- `ResearchArchive refuses a stage not in the config`.

Commit: `Generate the construct's config type and build one stack per stage`

### Task 3: Storage

**Does:** Adds the staging, archive and derived buckets, with optional write-once locking and the prod/non-prod removal rules.
**Files:** `packages/infra/src/storage.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/storage.test.ts`
**Checks:** `npm test -w packages/infra` exits 0.
**Serves:** DCSN4 (rests on calls AGNT1, AGNT7, AGNT9)

`class Storage extends Construct` with `readonly stagingBucket`, `archiveBucket` and `derivedBucket` (`s3.Bucket`). Props: `{ isProd: boolean; objectLock?: { retentionDays: number } }`.

- Every bucket: `blockPublicAccess: BLOCK_ALL`, `enforceSSL: true`, `encryption: S3_MANAGED`. Prod: `removalPolicy: RETAIN`. Non-prod: `removalPolicy: DESTROY` with `autoDeleteObjects: true`.
- Staging: a lifecycle rule expiring objects after 30 days.
- Archive: `versioned: true`. When `objectLock` is set, `objectLockEnabled: true` with `objectLockDefaultRetention: ObjectLockRetention.governance(Duration.days(retentionDays))`. The `open/` and `restricted/` prefixes are conventions used by PLAN2 and Plans 6 and 7; no resources.
- Derived: not versioned.
- `ResearchArchive` creates `Storage` and exposes `stagingBucket`, `archiveBucket`, `derivedBucket`.

Tests (`Template.fromStack`):

- `the archive bucket is versioned, blocks public access and enforces TLS`.
- `staging objects expire after 30 days`.
- `prod buckets are retained and a dev stage's are deleted with their objects`.
- `write-once locking appears only when objectLock is set, in governance mode with its retention days`.

Commit: `Add the archive's buckets`

### Task 4: Tables and the active-catalog parameter

**Does:** Adds catalog tables A and B, the `/research-archive/<stage>/catalog-active` parameter and the five operational tables, all exposed on the construct.
**Files:** `packages/infra/src/tables.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/tables.test.ts`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0.
**Serves:** DCSN1, DCSN4 (rests on calls AGNT4, AGNT5, AGNT10, AGNT12)

Use `dynamodb.Table`, not `TableV2`. `TableV2` synthesises `AWS::DynamoDB::GlobalTable`, and bulk put items does not support global tables, which PLAN3's reindex needs. Every table uses `billingMode: PAY_PER_REQUEST`, string keys and generated names, so stages never collide. Prod: `removalPolicy: RETAIN` and `deletionProtection: true`. Non-prod: `DESTROY` and no deletion protection.

`class Tables extends Construct`, props `{ stage: string; isProd: boolean }`:

- `readonly catalogTables: { a: Table; b: Table }`: each with partition `PK`, sort `SK`, and GSI `GSI1` (partition `GSI1PK`, sort `GSI1SK`, projection ALL). No point-in-time recovery.
- `readonly activeCatalogParameter: ssm.StringParameter`: name `/research-archive/<stage>/catalog-active`, initial value `A`.
- Operational tables, each with `pointInTimeRecoverySpecification: { pointInTimeRecoveryEnabled: true }`:
  - `submissions`: partition `submissionId`; GSI `byStatus` (`status`, `createdAt`); GSI `bySubmitter` (`submitter`, `createdAt`).
  - `reviews`: partition `submissionId`, sort `eventKey` (written as `<at>#<eventId>`).
  - `settings`: partition `name`.
  - `userProfiles`: partition `userId`.
  - `downloadCounts`: partition `datasetId`, sort `month`.
- `ResearchArchive` creates `Tables` and exposes `catalogTables`, `activeCatalogParameter`, `submissions`, `reviews`, `settings`, `userProfiles`, `downloadCounts` as readonly properties.

Tests:

- `there are two catalog tables with PK, SK and GSI1, on demand, without point-in-time recovery`.
- `no table is a global table` (no `AWS::DynamoDB::GlobalTable` in the template).
- `the active-catalog parameter is named for the stage and starts at A`.
- `each operational table has its key and point-in-time recovery` (one assertion per table, keys as above, including both Submissions indexes).
- `prod tables have deletion protection and are retained; a dev stage's are not`.

Add one line to the Decision log at the end of `docs/planning-handoff.md`: `| <date> | 4, 6 | The catalog and operational tables are plain dynamodb.Table (AWS::DynamoDB::Table), not TableV2, because TableV2 synthesises a GlobalTable and bulk put items does not support global tables. Plan 6 adds the vector index through the catalog tables' CfnTable (vectorIndexes). |`

Commit: `Add the catalog and operational tables`

After Task 4, push the branch, open a PR against `main` with `gh api`, and enable auto-merge after CI passes on the PR (main has no branch protection, so `--auto` merges at once: wait for the PR's CI run to pass, then merge).
