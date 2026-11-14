---
diazo: research-archive-in-a-box/deployment-skill-and-ci
file: spec
status: approved
approved: 2026-11-14T00:54:34-06:00
hash: eede9d6dc0b351091caac0edefa85aaca55b147ea42ed7576aa8b8e6865a8f89
rests_on: [AGNT4, AGNT6, AGNT7, AGNT1, AGNT2, AGNT3, DCSN1, DCSN3, DCSN2, AGNT5]
record: README.md
---

# Deployment skill and CI

## Goal

Someone who forks the repo opens it in Claude Code and the deployment skill takes them from a clone to a working archive in their own AWS account: it checks what they need, writes `archive.yaml` with them, connects GitHub Actions to AWS, has CI deploy it, invites the first admin, publishes the sample package through the archive's own submit and publish path, and runs a smoke test. Update and teardown are part of the same skill. CI tests Python, the CDK and the web app, runs security checks, and is the one thing that deploys an archive stack. It builds on what Plans 1 to 9 built or are building (the justfile recipes, `ArchiveConfig`, the default CDK app, Plan 7's submissions API, Plan 8's reindex that rewrites pages) and rebuilds none of them.

## The deployment skill

The skill is `.claude/skills/deploy-archive/SKILL.md` in the repo, for the person running an archive. A fork opened in Claude Code has it with no plugin install. Plan 9's plugin is for researchers and curators and doesn't carry it.

Its steps, in order. ✋ marks a step where it stops, says what will happen and what it costs or changes, and waits for a yes:

1. **Prerequisites.** uv, Node 24, just, the AWS CLI signed in (it shows `aws sts get-caller-identity` and asks whether that is the account), gh signed in, the clone's `origin` is the adopter's GitHub fork with Actions on. It says what is missing and how to install it, and goes no further until it is there.
2. **The config.** It asks about the archive (publisher, the alert email, the monthly budget, profiles, licenses, access levels), then walks through every other setting with its default. It reads the settings, their defaults and their descriptions from `ArchiveConfig`'s JSON Schema, so a setting a later plan adds reaches the skill with no edit. It writes `archive.yaml` and validates it with the contract's `load_config` before going on. A fork keeps the default `prod` stage unless the adopter asks for another, such as `dev`.
3. ✋ **Connect GitHub to AWS** (see Connecting GitHub to AWS). It creates IAM in their account.
4. ✋ **Deploy.** It says what bills while the archive sits idle and what bills per use, and points to the budget alarm the config sets. It gives no dollar figure, since none has been measured. On a yes it commits `archive.yaml`, pushes to `main`, and follows the CI run with `gh run watch` on that run's id until it ends.
5. ✋ **First admin.** It confirms the email address, then runs `just invite-user <stage> <email> admin,curator,contributor`. Cognito emails a temporary password.
6. ✋ **Seed.** It says the sample package becomes public data on their archive, then runs `just seed <stage>` (see Seeding).
7. **Smoke test.** `just smoke <stage>` (see The smoke test). It reports each check.

The skill never runs `cdk deploy` itself. A stage in another account (an entry in `infrastructure.stages` with its own `account`) gets step 3 run once against that account.

Rests on: AGNT4, AGNT6, AGNT7

## Connecting GitHub to AWS

A small separate CDK stack, `ResearchArchiveDeploy`, lives in `packages/infra`. It holds GitHub's OIDC provider and one role whose trust allows only `repo:<owner>/<name>:environment:<stage>` for this fork's stages, and which may only assume the CDK bootstrap roles in its account (`cdk-*-deploy-role-*`, `cdk-*-file-publishing-role-*`, `cdk-*-image-publishing-role-*`, `cdk-*-lookup-role-*`). That is how CDK itself scopes a deploy, so the role holds no broad permissions.

The skill runs `cdk bootstrap` when the account and region have no `CDKToolkit` stack, deploys `ResearchArchiveDeploy` from the laptop, then creates one GitHub environment per stage and sets the role's ARN as the environment variable `AWS_DEPLOY_ROLE_ARN`, and the stage's region as `AWS_REGION`, with `gh api`. A synth test pins the trust to the repo and its environments and the role's permissions to the bootstrap roles.

Rests on: AGNT1

## CI

`ci.yml` keeps its two check jobs and gains:

- **security**: `pip-audit` on the exported uv lock, `npm audit --audit-level=high`, and `zizmor` on `.github/workflows/`. It runs on every push and pull request beside the checks.
- **deploy**: on a push to `main`, after the check and security jobs pass. It reads the stage list from `archive.yaml` through the contract and deploys one stage at a time in the order the file lists them, each waiting for the one before and stopping at the first failure. Each stage's job runs in the GitHub environment named for it, takes its credentials from `AWS_DEPLOY_ROLE_ARN` with `id-token: write`, runs `just lambda-assets` and `npx cdk deploy ResearchArchive-<stage> --require-approval never`, then `just smoke <stage>`.

A prod-only fork deploys `prod` on every push to `main`. A fork that lists `dev` before `prod` gets `dev` first. A stage whose environment has no `AWS_DEPLOY_ROLE_ARN` is skipped with a notice and doesn't fail the run, so this upstream repo and a fork not yet connected stay green. An adopter who wants an approval before prod adds a required reviewer to the `prod` environment in GitHub's settings, with no code change.

Rests on: AGNT2, AGNT3

## Seeding and the sign-in

The seed goes through the archive's own submit and publish path, the way any dataset arrives, never a copy into the bucket. The seed is the committed sample package (`examples/sample-package`, invented data under CC-BY-4.0, access `open`).

The sign-in is the shared module the Decision log fixes, `archive_client.signin` in `packages/client` (`archive-client`), which Plan 9's build is writing now on its own branch: `AuthConfig.from_archive(site_url)` reads the archive's `/auth-config.json` (written by Plan 8 at deploy), and `sign_in(config) -> Tokens` signs in through the existing `cli` app client with PKCE in the browser and a one-shot listener on `localhost:8765`, keeping the one-hour tokens in memory and never the refresh token. This plan builds none of it: `just seed` imports it, and this plan's build of the seed waits on Plan 9's pull request merging.

`just seed <stage>` runs a small script that takes the site's domain from the stage's stack, gets the `AuthConfig` with `AuthConfig.from_archive`, signs in as the admin (the first sign-in sets their own password in the browser), and then:

1. creates a submission for the sample package's files with `POST /api/submissions`, uploads each to its presigned URL, and submits it;
2. follows `GET /api/submissions/{id}` until the submission leaves `checking`;
3. approves it with `POST /api/submissions/{id}/decision` when it is `in-review` (a review policy that skips review publishes it with no decision);
4. waits for `published`, then prints the dataset's URL.

A submission that ends anywhere else (`needs-changes`, `rejected`, `failed`) stops the script with the status and its findings or events.

Rests on: DCSN1, AGNT7

## The smoke test

`just smoke <stage>` takes the site's domain from the stage's stack and checks, with no sign-in:

- the site's `/` answers 200 with HTML;
- `/api/health` answers `{"status": "ok"}`;
- `/api/search?q=stream` lists `stream-temperature-sample`;
- `/datasets/stream-temperature-sample` serves its page;
- one open file of it downloads from `/data/stream-temperature-sample/<version>/...` and its SHA-256 matches the manifest's hash.

Until the seed exists, the three dataset checks are skipped and say so, and the rest must pass. It exits non-zero on any failed check. CI runs it after every deploy, and the skill runs it after seeding. The submit path is proven once, by the seed, so CI holds no credentials for the archive.

Rests on: DCSN3

## Update

The skill's update steps:

1. Add the upstream remote (`schuettc/research-in-a-box`) if it is missing, and fetch it.
2. Show what changed upstream since the fork's last merge (the commit list, and any change to `ArchiveConfig`'s settings).
3. Merge upstream's `main` into the fork's `main`. A conflict in `archive.yaml` keeps the fork's values. A conflict anywhere else is shown to the adopter, who decides.
4. Walk through any new setting the merge brought, as step 2 of the setup does.
5. Run `just check`. On a failure it stops and pushes nothing.
6. ✋ Push, and follow the CI run that deploys it.

Rests on: DCSN2

## Teardown

`just destroy <stage>` runs from the laptop, never in CI. The skill makes the adopter type the stage name, and says plainly that `prod` keeps its buckets and tables (they then hold the data and still bill for storage) while other stages delete everything. It runs `npx cdk destroy ResearchArchive-<stage> --force`, deletes the log group CDK's S3 auto-delete helper leaves behind (`/aws/lambda/ResearchArchive-<stage>-CustomS3AutoDeleteObjects*`, Plan 4's PARK12), and confirms the stack no longer exists. Removing `ResearchArchiveDeploy` and the GitHub environments is offered last, as its own ✋ step, only when no stage is left in that account.

Rests on: AGNT5

## Risk and cost

**Risk.** The deploy role is the riskiest piece: a trust that is too loose would let another repo deploy into the adopter's account. Its trust is pinned to the fork and its environments by a synth test, and it can only assume CDK's bootstrap roles. A bad commit on `main` deploys to `prod`, but only after the checks pass, `prod` retains its buckets and tables, and a revert deploys the fix the same way. A mistaken teardown is guarded by running only from the laptop with the stage name typed, and `prod` keeps its data even then. The seed publishes public data, so it asks first; until Plan 7's takedown exists, undoing it is by hand (delete the version's objects and catalog items, then reindex).

**Cost.** New programs: `pip-audit` and `zizmor`, both run with `uvx`, nothing installed. AWS: the OIDC provider and role cost nothing. The user's steps: one walkthrough on a throwaway fork in an AWS account they choose, using a non-prod stage, where they answer the skill's stops, sign in once in the browser and approve the teardown.

Rests on: AGNT1, AGNT5

## Left out

- Running the reindex after a deploy so a template change reaches every page: waits on Plan 8's reindex that rewrites pages (PARK1).
- CodeQL and cdk-nag (PARK2).
- A one-click template, a custom domain, ORCID and university sign-in: Plan 4's follow-ups.
- Signed-in smoke checks and a submit round trip on every deploy: they need credentials in CI or test data on `prod`.
- A weekly upstream-sync workflow and GitHub's Sync fork button.
- `archive_client` itself: Plan 9 builds it, and this plan only imports it.

Rests on: DCSN2, DCSN3, AGNT3

## How we'll know it works

- `just check` and the new security job pass on this repo, and the deploy job skips with a notice because no environment has a deploy role.
- A synth test shows `ResearchArchiveDeploy`'s role trusts only the fork's environments and may only assume the CDK bootstrap roles.
- The seed script has unit tests for its submit, follow, approve and stop paths, with the API faked.
- On a throwaway fork in a real AWS account, with a non-prod stage, the skill runs end to end: it stops at each ✋ step, CI deploys the stage, the first admin is invited, `just seed` publishes the sample package after the admin signs in, and `just smoke` passes every check. `just destroy` then leaves no stack, bucket, table or helper log group for that stage.

Rests on: DCSN1, DCSN3, AGNT1, AGNT2, AGNT5
