---
name: deploy-archive
description: For the person running a research archive from a fork of research-in-a-box. Use to set up a deployment of the fork in their own AWS account (prerequisites, archive.yaml, connecting GitHub Actions to AWS, the first deploy, the first admin, the seed dataset and a smoke test), to update the fork from upstream and redeploy, or to tear a stage down.
---

# Deploy the archive

This skill sets up, updates and tears down a deployment of this fork. It is for the person who
runs the archive, not for researchers or curators.

Ground rules:

- **CI deploys archive stacks; you never do.** Never run `cdk deploy` on a `ResearchArchive-*`
  stack. You push to `main` and CI deploys each stage in `archive.yaml` order. The only stack you
  deploy from the laptop is `ResearchArchiveDeploy`, the GitHub-to-AWS connection.
- **✋ means stop.** At a ✋ step, say what will happen and what it costs or changes, then wait for
  the words the step names. Anything else is a no: answer questions, change nothing, and ask again.
- The recipes you call: `just stages`, `just invite-user`, `just seed`, `just smoke`,
  `just destroy`, `just check`. Run them from the repo's root.

Choose the part the person asked for: **Setup**, **Update** or **Teardown**.

## Setup

### 1. Prerequisites

Check each, say what is missing and how to install it, and go no further until all are there:

- `uv --version` ([install](https://docs.astral.sh/uv/getting-started/installation/)),
  `node --version` is 24 or later, `just --version` ([install](https://just.systems/)).
- The AWS CLI is signed in: run `aws sts get-caller-identity`, show the account and the ARN, and
  ask: "Is this the AWS account the archive should live in?" A no means they sign in to the right
  one (`aws sso login --profile <name>` and `export AWS_PROFILE=<name>`, or `aws configure`).
  Note the region: `aws configure get region`.
- gh is signed in: `gh auth status`.
- The clone's `origin` is their own fork on GitHub: `git remote get-url origin` must not be
  `schuettc/research-in-a-box`. Note `<owner>/<name>` from it.
- Actions is on for the fork: `gh api repos/<owner>/<name>/actions/permissions --jq .enabled` is
  `true`. If not, they turn it on under the fork's Settings → Actions.

Then run `uv sync --all-packages` and `npm ci`.

### 2. The config

Read the settings from the JSON Schema, never from memory, so a setting a later change adds
reaches you with no edit here: `packages/web/src/schema/archive-contract.schema.json`,
`$defs.ArchiveConfig` and the definitions it refers to (`Infrastructure`, `Stage`, `Modules`,
`ObjectLock`, `Vocabulary` and the rest). Each property's `description` and `default` are what you
tell the person.

1. Ask about the archive first: the publisher's name, the alert email (budget and failure alerts
   go there), the monthly budget in US dollars, the profiles, the licenses offered and the access
   levels offered.
2. Then walk through every other setting, one at a time, with its default, and keep the default
   unless they want something else. Optional modules (such as WAF and object lock) are off unless
   they switch them on; say what each adds.
3. Keep the one `prod` stage unless they ask for another, such as `dev` listed before `prod`. A
   stage in another AWS account gets its own `account` (and `region`).
4. Write `archive.yaml` and validate it before going on:

   ```
   uv run python -c "from pathlib import Path; from archive_contract.config import load_config; print(load_config(Path('archive.yaml')))"
   ```

   On an error, fix it with them and validate again. `just stages` then prints the stages.

### 3. ✋ Connect GitHub to AWS

**What it does.** Deploys the `ResearchArchiveDeploy` stack into their AWS account: GitHub's OIDC
provider and one IAM deploy role. The role trusts only this fork's GitHub environments named for the stages
(`repo:<owner>/<name>:environment:<stage>`) and may only assume CDK's bootstrap roles. It also
bootstraps CDK in the account and region if that hasn't been done (a `CDKToolkit` stack with an
S3 bucket), and creates one GitHub environment per stage holding the role's ARN and the region,
which only `main` may deploy from.

**What it costs.** The provider and role cost nothing. The CDK bootstrap bucket bills for the
little it stores.

**Wait for:** "connect it" (or a clear yes).

Then, for the account and region of the stages (run it once more against each other account a
stage names, signed in to that account):

1. If `aws cloudformation describe-stacks --stack-name CDKToolkit` fails, bootstrap:

   ```
   cd packages/infra && npx cdk bootstrap aws://<account>/<region>
   ```

2. Deploy the connection:

   ```
   cd packages/infra && npx cdk --app "npx tsx bin/deploy-access.ts" deploy -c githubRepo=<owner>/<name> --require-approval never
   ```

3. Read the role's ARN:

   ```
   aws cloudformation describe-stacks --stack-name ResearchArchiveDeploy --query "Stacks[0].Outputs[?OutputKey=='DeployRoleArn'].OutputValue" --output text
   ```

4. For each stage in that account, create its environment so that only `main` can deploy from
   it, then set its two variables (the stage's own `region`, or the profile's region when the
   stage names none). The branch rule matters: the role trusts any workflow run in the stage's
   environment, so without it a push to any branch whose workflow names `environment: prod`
   could assume the role and deploy.

   ```
   gh api -X PUT repos/<owner>/<name>/environments/<stage> --input - <<< '{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}'
   gh api -X POST repos/<owner>/<name>/environments/<stage>/deployment-branch-policies -f name=main -f type=branch
   gh api -X POST repos/<owner>/<name>/environments/<stage>/variables -f name=AWS_DEPLOY_ROLE_ARN -f value=<role-arn>
   gh api -X POST repos/<owner>/<name>/environments/<stage>/variables -f name=AWS_REGION -f value=<region>
   ```

   A branch policy that already exists answers with an error; that is fine. A variable that
   already exists is changed with
   `gh api -X PATCH repos/<owner>/<name>/environments/<stage>/variables/<NAME> -f name=<NAME> -f value=<value>`.

Tell them that to require an approval before `prod` deploys, they add a required reviewer to the
`prod` environment in the fork's Settings → Environments; no code changes.

### 4. ✋ Deploy

**What it does.** Commits `archive.yaml`, pushes to `main`, and CI deploys each stage in order
after the checks pass, then smoke-tests it.

**What it costs.** Say what bills while the archive sits idle: storage in S3 and DynamoDB, the
CloudWatch alarms and dashboard, retained logs, and the WAF web ACL if they switched WAF on. Say
what bills per use: Lambda, API Gateway, CloudFront, DynamoDB reads and writes, and Cognito past
its free tier. Give no dollar figure; none has been measured. Point to the budget alarm: AWS
Budgets emails the alert email when the month passes `monthlyBudgetUsd`.

**Wait for:** "deploy it" (or a clear yes).

Then:

1. `git add archive.yaml && git commit -m "Configure the archive" && git push origin main`
2. Find the run: `gh run list --commit $(git rev-parse HEAD) --workflow CI --json databaseId --jq '.[0].databaseId'`
   (wait a few seconds and ask again if it isn't listed yet).
3. `gh run watch <run-id> --exit-status` until it ends. On a failure, show
   `gh run view <run-id> --log-failed` and stop.

A stage's job that says it has no `AWS_DEPLOY_ROLE_ARN` was skipped: step 3 missed it.

### 5. ✋ First admin

**What it does.** Creates the first account on the stage, in the `admin`, `curator` and
`contributor` groups (creating a submission needs contributor; deciding one needs curator).
Cognito emails a temporary password to the address.

**What it costs.** Nothing.

Confirm the email address with them. **Wait for:** "invite <email>" (or a yes naming the address).

Then: `just invite-user <stage> <email> admin,curator,contributor`

### 6. ✋ Seed

**What it does.** Publishes the committed sample package (`examples/sample-package`, invented
stream temperature data under CC-BY-4.0, access `open`) through the archive's own submit and
publish path. It becomes **public data on their archive**. The admin signs in once in the
browser, setting their own password from the invite email.

**What it costs.** A few requests and a few kilobytes of storage. Until takedown exists, undoing
it is by hand.

**Wait for:** "seed it" (or a clear yes).

Then: `just seed <stage>`. It prints the dataset's URL when it is published, or the status and
its findings when it stops.

### 7. Smoke test

`just smoke <stage>`. Report each check's line: the site, health, search, the dataset page and a
download whose SHA-256 matches the manifest. Every check should say `ok` after the seed. Then give
them the site's URL:
`aws cloudformation describe-stacks --stack-name ResearchArchive-<stage> --query "Stacks[0].Outputs[?OutputKey=='SiteDomain'].OutputValue" --output text`.

## Update

1. Add upstream if it is missing, and fetch it:

   ```
   git remote get-url upstream || git remote add upstream https://github.com/schuettc/research-in-a-box.git
   git fetch upstream
   ```

2. Show what changed since the fork's last merge: `git log --oneline main..upstream/main`, and any
   change to the settings: `git diff main...upstream/main -- packages/web/src/schema/archive-contract.schema.json`.
3. Merge: `git merge upstream/main`. A conflict in `archive.yaml` keeps the fork's values. Show
   any other conflict to them; they decide how it resolves.
4. Walk through any setting the merge brought, as Setup's step 2 does, and validate
   `archive.yaml` again.
5. `just check`. On a failure, stop and push nothing.
6. ✋ **Push.** What it does: pushes the merge to `main`, and CI deploys every stage in order.
   **Wait for:** "push it" (or a clear yes). Then push and follow the run as Setup's step 4 does.

## Teardown

1. Ask which stage. **They type the stage name** exactly; anything else stops here.
2. Say plainly what happens: the stage's stack is deleted. A `prod` stage **keeps its buckets and
   tables**: they still hold the data and still bill for storage, and deleting them is by hand.
   Any other stage deletes everything, data included. Submissions still waiting for review or
   for changes end, and their contributors would have to submit again on another stage.
3. ✋ **Wait for:** "destroy <stage>". Then: `just destroy <stage>`. It stops the stage's
   running ingest executions (they would block the delete), deletes the stack and the log group
   CDK's S3 auto-delete helper leaves behind, and fails if the stack still exists.
4. ✋ Only when no stage is left in that account (every stage `archive.yaml` puts there is
   destroyed): offer removing the GitHub connection. What it does: deletes the
   `ResearchArchiveDeploy` stack (the OIDC provider and the deploy role) and the GitHub
   environment of every stage in that account; CI can no longer deploy to this account.
   **Wait for:** "remove the connection". Then, naming every stage in that account:

   ```
   cd packages/infra && npx cdk --app "npx tsx bin/deploy-access.ts" destroy -c githubRepo=<owner>/<name> --force
   for stage in <stage> <stage>; do gh api -X DELETE "repos/<owner>/<name>/environments/$stage"; done
   ```

   The CDK bootstrap stack stays; other CDK apps in the account may use it.
