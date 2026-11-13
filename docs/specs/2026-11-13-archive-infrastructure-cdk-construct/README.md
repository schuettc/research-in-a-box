<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Archive infrastructure (Plan 4)

`research-archive-in-a-box/archive-infrastructure-cdk-construct` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans · 2 wait** → **Build · 0 of 4** → Sign off

PLAN1 building · 0 of 4 done · PLAN2 waits on PLAN1 being built · PLAN3 waits on PLAN2 being built

## Pick up next

- **PARK1 Reindex from cruise:** Let a signed-in admin start and follow a reindex from cruise through an admin API route with a short-lived token, so no AWS credentials are needed. Needs an admin route from Plan 6.
- **PARK2 Custom domain:** Let the config name a domain and an existing us-east-1 ACM certificate so CloudFront and Cognito's managed login serve under the archive's own domain. Left out of Plan 4 until an adopter needs it; the CloudFront domain is already a stable URL.
- **PARK3 ORCID sign-in:** Optional ORCID sign-in as a Cognito OIDC identity provider, with the client secret in an SSM SecureString the config names. Left out of Plan 4 at the coordinating session's review: nobody has an ORCID client to test it with yet.
- **PARK4 University sign-in:** Optional university single sign-on as a Cognito SAML identity provider from a metadata URL in the config. Left out of Plan 4 at the coordinating session's review until an adopter has SAML metadata to test with.
- **PARK5 Reindex catch-up:** Before flipping the active catalog, re-put every package published after the reindex's snapshot time, so a publish during a run isn't lost from the new table. Needed once Plan 7 publishes; until then a reindex runs while publishing is quiet.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 1, repo layout, folder d65ecf18be29, and the manifest shape from Plan 2, folder 8da653f233f9.)
> 
> Brief: Plan 4 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the archive infrastructure as a TypeScript CDK construct (Plan 4). The service choices are decided and listed under "Infrastructure". Do not reopen them. Plan the resources, the DynamoDB design and the construct's interface, and take the open questions with me one at a time.

## Decisions

- **DCSN1 Table layout.** How should the DynamoDB data be split across tables? The user chose D: One catalog table, one table per kind of operational record.
- **DCSN2 Config to construct.** How should the archive config file reach the TypeScript construct? The user chose A: One file, an infrastructure section in the contract, typed construct props.
- **DCSN3 Who starts a reindex.** Where should a reindex run: in a Lambda in the archive, or from an admin's machine? The user chose A: A durable Lambda in the archive, started by an admin.
- **DCSN4 Dev and prod stages.** How should dev and prod be laid out? The user chose C: Prod only by default.
- **AGNT1 Modules switched by config.** A modules section in the archive config; the construct builds each part only when its switch is on. The user kept it.
- **AGNT2 Python Lambda packaging.** arm64 functions. A just recipe uses uv to install locked dependencies as manylinux aarch64 wheels (--only-binary) into an asset folder before synth; no Docker. One helper on the construct builds a function from archive-backend so Plans 6 and 7 package the same way. The user kept it.
- **AGNT3 Vector index in Plan 6.** Plan 6 adds it to both catalog tables, along with the embedding model it chooses and the embeddings config setting. Plan 4 makes the catalog tables on-demand and exposes them, so Plan 6 adds the index without changing Plan 4's design. Moved at the coordinating session's review. The user kept it.
- **AGNT4 On-demand tables.** On-demand for both tables. The user kept it.
- **AGNT5 Users live in Cognito.** Cognito holds each user, with groups for contributor, curator and admin. A user-profiles table keeps only what Cognito can't hold: the display name for citations, the ORCID iD and notification settings. The user kept it.
- **AGNT6 Download logs.** Plan 4 turns on CloudFront standard logs into the derived bucket's logs/ prefix and creates the DownloadCounts table. Rolling the logs up into counts belongs to Plan 6, whose brief holds download counts. The user kept it.
- **AGNT7 Integrity check.** Objects are written with S3 SHA-256 checksums. A weekly EventBridge Scheduler job runs a Lambda that compares each archived object's stored checksum with the package's checksums.sha256 and alerts on any mismatch or missing object. The user kept it.
- **AGNT8 Reindex from the CLI.** Two just recipes: reindex &lt;stage> invokes the reindex durable function asynchronously with the AWS CLI and prints the execution ARN, and reindex-status &lt;stage> reports the execution's state and the bulk put outcome. The function name comes from a stack output. The user kept it.
- **AGNT9 Adding a stage.** The config's infrastructure section has a stages list holding prod by default. Each entry has a name and optionally an account and region; the default app makes one stack per entry, named ResearchArchive-&lt;stage>. A stage named prod keeps data on delete (retain and deletion protection); any other stage is set to be torn down cleanly. The user kept it.
- **AGNT10 Catalog switch.** CDK creates two catalog tables, A and B, with the same keys. An SSM parameter per stage names the active one, and every Lambda reads it (cached briefly). Reindex empties the inactive table, bulk-loads it, checks the report, then flips the parameter. It runs while publishing is quiet; catching up packages published during a run is follow-up PARK5. The user kept it.
- **AGNT11 REST API behind CloudFront.** A REST API, with stage throttling and an optional regional WAF attached directly to it. CloudFront routes /api/* to it, so the web app calls the API on its own origin with no CORS. The user kept it.
- **AGNT12 Backups for what can't be rebuilt.** Point-in-time recovery on every operational table (submissions, reviews, settings, user profiles, download counts). None on the catalog tables, which reindex rebuilds from S3. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The parts](spec.md#the-parts): rests on DCSN2, AGNT1
- [Storage](spec.md#storage): rests on AGNT7
- [Tables](spec.md#tables): rests on DCSN1, AGNT3, AGNT4, AGNT5, AGNT12
- [Reindex](spec.md#reindex): rests on DCSN1, DCSN3, AGNT8, AGNT10
- [Config and the construct's interface](spec.md#config-and-the-constructs-interface): rests on DCSN2, AGNT1
- [Python Lambdas](spec.md#python-lambdas): rests on AGNT2
- [Auth](spec.md#auth): rests on AGNT5
- [API shell and web](spec.md#api-shell-and-web): rests on AGNT6, AGNT11
- [Operations and stages](spec.md#operations-and-stages): rests on DCSN4, AGNT9
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN4, AGNT10, AGNT12
- [Left out](spec.md#left-out): rests on DCSN3, AGNT1, AGNT3
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, DCSN3, DCSN4, AGNT8, AGNT10

## Plans

- [PLAN1](plans/1-config-storage-and-tables.md) Config, storage and tables: building · 0 of 4 done
  - TASK1 Task 1: The infrastructure section of the archive config: not started
  - TASK2 Task 2: Generated config type and the default app: not started
  - TASK3 Task 3: Storage: not started
  - TASK4 Task 4: Tables and the active-catalog parameter: not started
- PLAN2 Auth api web and operations: waits on PLAN1 being built
- PLAN3 Reindex and test deploy: waits on PLAN2 being built

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
| `diagrams/` | diazo | The drawn picture (SVG) of each mermaid diagram in the folder. |

## Ids

Every card has an id: its prefix, then a number.

- `DCSN`: a decision the user makes
- `AGNT`: a call the agent made, which the user may reverse
- `PRIN`: a principle
- `PARK`: a follow-up, for later
- `STEP`: a step only the user can do
- `ASK`: an ask of someone other than the user
- `PLAN`: a plan
- `TASK`: a task of a plan

The full record is `decisions.json`; its schema is [schema/record.json](https://github.com/subaud-tools/diazo/blob/main/schema/record.json).
