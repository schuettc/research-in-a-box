---
diazo: research-archive-in-a-box/deployment-skill-and-ci
file: PLAN1
status: building
approved: 2026-11-14T00:57:03-06:00
hash: ea1a697cda6c8d8790846950b54470a23e9e22a530cb0b445feada2c1aef313d
rests_on: [AGNT1, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, DCSN1, DCSN2, DCSN3]
record: README.md
---

# PLAN1: The deployment skill and CI

## Spec

`docs/specs/2026-11-13-deployment-skill-and-ci/spec.md`, every section. Plans 1 to 6 are built and merged. Plan 7's submissions API and publish, Plan 8's `/auth-config.json` and Plan 9's `archive_client.signin` are being built in their own folders: this plan builds on them and rebuilds none of them. Where a task needs one that hasn't merged yet, that task waits on its pull request.

## The change

- A `ResearchArchiveDeploy` stack in `packages/infra`, in its own small CDK app, holding GitHub's OIDC provider and one deploy role.
- CI gains a security job and a deploy job that deploys each stage in `archive.yaml` order and runs the smoke test after it.
- `scripts/smoke.py` behind `just smoke <stage>`, `scripts/seed.py` behind `just seed <stage>`, and a `just destroy <stage>` recipe. `just invite-user` takes a comma-separated group list.
- The skill, `.claude/skills/deploy-archive/SKILL.md`, with its setup, update and teardown steps.
- One live run on a throwaway copy of the repo in an AWS account Court chooses.

**Risk.** The deploy role's trust is the piece that could do harm: a trust that is too loose lets another repo deploy into the account. Task 1's synth test pins it to the repo and its environments, and the role may only assume the CDK bootstrap roles. Task 6 creates real resources under a non-prod stage, all deleted by `just destroy`; a few dollars at most. Nothing touches a `prod` stage or this upstream repo's AWS access, since the upstream repo has no deploy role and its deploy job skips.

**Cost.** New programs: `pip-audit` and `zizmor`, run with `uvx`. Court's steps: Task 6's walkthrough (choose the account, create the throwaway repo, answer the skill's stops, sign in once in the browser, approve the teardown).

## Left out

Everything in the spec's Left out section: the reindex after a deploy (PARK1), CodeQL and cdk-nag (PARK2), signed-in smoke checks, a sync workflow, and `archive_client` itself, which Plan 9 builds.

## Where

Branch `plan10a/build-plan1` from `origin/main`, in the worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan10a/build-plan1`. One pull request per task against `main`, merged once its checks pass. `scripts/` is new: add it to pytest's `testpaths`, to the `mypy` paths in `just check-python`, and to ruff's first-party list.

### Task 1: The deploy role stack

**Does:** Adds `ResearchArchiveDeploy`: GitHub's OIDC provider and one role that GitHub Actions assumes to deploy.
**Files:** `packages/infra/src/deploy-access.ts`, `packages/infra/bin/deploy-access.ts`, `packages/infra/test/deploy-access.test.ts`
**Checks:** `just check`
**Serves:** none (rests on call AGNT1)

- `bin/deploy-access.ts` is its own CDK app, run with `npx cdk --app "npx tsx bin/deploy-access.ts"`, so the default app and CI's deploy never touch it. It takes the repo from the context value `githubRepo` (`owner/name`) and the stages from `archive.yaml` (or `ARCHIVE_CONFIG`), keeping those whose account is the one being deployed to or is unset. It fails synth with a clear message when `githubRepo` is missing.
- The OIDC provider is `token.actions.githubusercontent.com` with audience `sts.amazonaws.com`.
- The role's trust allows `sts:AssumeRoleWithWebIdentity` only when `aud` is `sts.amazonaws.com` and `sub` is exactly one of `repo:<owner>/<name>:environment:<stage>` for those stages (`StringEquals`, never a wildcard). Its only permission is `sts:AssumeRole` on `arn:aws:iam::<account>:role/cdk-*-{deploy,file-publishing,image-publishing,lookup}-role-<account>-*`.
- The stack outputs the role's ARN as `DeployRoleArn` and carries the `Repo` tag.
- The synth test asserts the trust's exact `sub` list for a two-stage config, that no statement grants anything but `sts:AssumeRole` on those role patterns, and that synth fails without `githubRepo`.

### Task 2: CI's security and deploy jobs

**Does:** Adds the security job and the deploy job to `ci.yml`, and a recipe that lists the stages.
**Files:** `.github/workflows/ci.yml`, `justfile`
**Checks:** `just check`; `uvx zizmor .github/workflows/`; on this repo's pull request, the security job passes and, after merge, the deploy job on `main` reports every stage skipped
**Serves:** none (rests on calls AGNT2, AGNT3)

- `just stages` prints the stage names of `archive.yaml` (or `ARCHIVE_CONFIG`) as a JSON list, in file order, read through the contract's `load_config`.
- **security**: on every push and pull request, `uv export --frozen --no-hashes` piped to `uvx pip-audit -r`, `npm audit --audit-level=high`, and `uvx zizmor .github/workflows/`. Actions stay pinned by SHA as in the existing jobs.
- **stages**: on a push to `main`, after `python`, `typescript` and `security` pass, runs `just stages` and outputs the list.
- **deploy**: a matrix over that list with `max-parallel: 1` and `fail-fast: true`, so stages go one at a time in order. Each job has `environment: ${{ matrix.stage }}`, `permissions: id-token: write, contents: read`, and its first step exits the job successfully with a `::notice::` when `vars.AWS_DEPLOY_ROLE_ARN` is empty. Otherwise it configures credentials with `aws-actions/configure-aws-credentials` (pinned) from `vars.AWS_DEPLOY_ROLE_ARN` and `vars.AWS_REGION`, runs `just lambda-assets`, `npx cdk deploy ResearchArchive-${{ matrix.stage }} --require-approval never` from `packages/infra`, then `just smoke ${{ matrix.stage }}`.
- `zizmor` findings are fixed, not suppressed, unless one is a false positive, which gets a one-line comment saying why.

### Task 3: just smoke, just destroy and invite-user's groups

**Does:** The smoke test, the teardown recipe, and a comma-separated group list for `just invite-user`.
**Files:** `scripts/smoke.py`, `scripts/tests/test_smoke.py`, `justfile`, `pyproject.toml`
**Checks:** `just check`
**Serves:** DCSN3 (rests on calls AGNT5, AGNT7)

- `scripts/smoke.py <domain> [--dataset stream-temperature-sample]`, standard library only (`urllib`, `hashlib`, `json`). It runs the spec's five checks in order and prints one line per check (`ok`, `failed: <why>` or `skipped: no seed yet`). When search doesn't list the dataset, the page and download checks are skipped and say so. It exits 1 on any failure.
- The download check reads the dataset's current version from `GET /api/datasets/<id>`, fetches `/data/<id>/<version>/datapackage.json`, picks the first resource whose `path` is a single file with a `hash`, downloads it, and compares SHA-256.
- `just smoke <stage>` takes the distribution's domain from the stack's outputs (adding a `SiteDomain` output in `research-archive.ts` with its synth assertion, if the stack has none) and runs the script.
- `just destroy <stage>` runs `npx cdk destroy ResearchArchive-<stage> --force`, deletes every log group whose name starts with `/aws/lambda/ResearchArchive-<stage>-CustomS3AutoDeleteObjects`, then checks that `aws cloudformation describe-stacks` reports the stack doesn't exist, and exits 1 if it still does. The typed confirmation is the skill's, not the recipe's.
- `just invite-user <stage> <email> [groups]` splits `groups` on commas and adds the user to each.
- Tests fake the HTTP answers: all pass, the no-seed skip, a wrong hash, a 500 from health.

### Task 4: just seed

**Does:** Submits the sample package through the archive's submissions API as the signed-in admin, approves it when it needs review, and waits for it to publish.
**Files:** `scripts/seed.py`, `scripts/tests/test_seed.py`, `justfile`, `pyproject.toml`
**Checks:** `just check`
**Serves:** DCSN1 (rests on call AGNT7)

Waits on Plan 9's pull request that adds `archive_client` (with `AuthConfig.from_archive`), on Plan 7's submissions API and publish being merged, and on Plan 8's `/auth-config.json`.

- `scripts/seed.py <domain> [--package examples/sample-package]`, standard library plus `archive_client`. It gets `AuthConfig.from_archive("https://<domain>")`, calls `sign_in`, then follows the spec's four steps against `/api/submissions`, uploading each file to its presigned URL with its SHA-256 checksum header as Plan 7 requires.
- It polls `GET /api/submissions/{id}` every 5 seconds, for at most 15 minutes, printing each new status once.
- On `in-review` it posts `approve` with the note `seed`. On `published` it prints `https://<domain>/datasets/<id>`. On `needs-changes`, `rejected`, `failed`, `expired` or the time running out, it prints the status with the latest findings or events and exits 1.
- `just seed <stage>` takes the domain from the stack's outputs, as `just smoke` does.
- Tests fake `sign_in` and the API: a skip-review publish, an approve-then-publish, a `needs-changes` stop, a timeout.

### Task 5: The deploy-archive skill

**Does:** Writes the skill a fork's owner runs in Claude Code to set up, update and tear down their archive.
**Files:** `.claude/skills/deploy-archive/SKILL.md`, `README.md`
**Checks:** `npx prettier --check .claude README.md`
**Serves:** DCSN2 (rests on calls AGNT1, AGNT4, AGNT5, AGNT6, AGNT7)

- The frontmatter's description says it is for the person running an archive, to set up, update or tear down a deployment of their fork.
- **Setup** follows the spec's seven steps, each ✋ step with what it does, what it costs or changes, and the words the skill waits for before going on. Step 2 tells the agent to read `packages/web/src/schema/archive-contract.schema.json` for `ArchiveConfig` and its definitions, and to validate with `uv run python -c` calling `archive_contract.config.load_config`. Step 3 runs `cdk bootstrap` when `aws cloudformation describe-stacks --stack-name CDKToolkit` fails, deploys `ResearchArchiveDeploy` with `-c githubRepo=<owner/name>`, then creates each stage's GitHub environment and sets `AWS_DEPLOY_ROLE_ARN` and `AWS_REGION` with `gh api`. Step 4 pushes, finds the new run's id with `gh run list --commit <sha>`, and watches that run.
- **Update** follows the spec's six steps.
- **Teardown** makes the adopter type the stage name, says what `prod` keeps, runs `just destroy <stage>`, and offers removing `ResearchArchiveDeploy` and the environments only when no stage is left in that account.
- It names the recipes it calls and never runs `cdk deploy` on an archive stack.
- `README.md` gains a short "Deploy your archive" section: fork, open in Claude Code, ask it to set up the archive.

### Task 6: The live run on a throwaway copy

**Does:** Runs the skill end to end on a throwaway copy of the repo in a real AWS account, then tears it down.
**Files:** none in the repo
**Checks:** each walkthrough action records its result; `just smoke deploy-test` exits 0; after `just destroy deploy-test`, `describe-stacks` reports no stack and no bucket, table or helper log group named for the stage remains
**Serves:** DCSN1, DCSN2, DCSN3 (rests on calls AGNT1, AGNT2, AGNT5)

A walkthrough step for Court, run once Tasks 1 to 5 are merged:

1. Court: choose the AWS profile and region, and Go on creating two private throwaway repos from `main`: `schuettc/research-in-a-box-deploy-test` (the fork) and `schuettc/research-in-a-box-upstream-test` (a stand-in for upstream, so the update test never touches the real repo).
2. Agent: create both with `gh repo create` and push `main` to each. In the fork's clone, `archive.yaml` lists one stage, `deploy-test`, and the `upstream` remote points at `research-in-a-box-upstream-test`.
3. Court: in a Claude Code session in that clone, ask it to set up the archive, and answer each ✋ stop.
4. Agent: confirm CI's run deployed `ResearchArchive-deploy-test` and its smoke step passed with the dataset checks skipped.
5. Court: sign in from the invite email when `just seed` opens the browser, setting the password.
6. Agent: confirm the seed published and `just smoke deploy-test` passes every check.
7. Agent: push a one-line change to `research-in-a-box-upstream-test`'s `main`, then run the skill's update in the fork's clone, confirming it merges, checks and deploys. Nothing is pushed to `schuettc/research-in-a-box`.
8. Court: Go on the teardown, including deleting both throwaway repos. The how says deleting a repo needs gh's `delete_repo` scope, with the command to add it (`gh auth refresh -h github.com -s delete_repo`) in its own block, for Court to run first.
9. Agent: `just destroy deploy-test`, remove `ResearchArchiveDeploy` and the environments, confirm nothing named for the stage remains, and delete both throwaway repos.
