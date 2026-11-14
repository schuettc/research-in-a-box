<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Archive infrastructure (Plan 4)

`research-archive-in-a-box/archive-infrastructure-cdk-construct` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → ✓ Build → **Sign off · due**

PLAN1 built · PLAN2 built · PLAN3 built

## Pick up next

- **PARK1 Reindex from cruise:** Let a signed-in admin start and follow a reindex from cruise through an admin API route with a short-lived token, so no AWS credentials are needed. Needs an admin route from Plan 6.
- **PARK2 Custom domain:** Let the config name a domain and an existing us-east-1 ACM certificate so CloudFront and Cognito's managed login serve under the archive's own domain. Left out of Plan 4 until an adopter needs it; the CloudFront domain is already a stable URL.
- **PARK3 ORCID sign-in:** Optional ORCID sign-in as a Cognito OIDC identity provider, with the client secret in an SSM SecureString the config names. Left out of Plan 4 at the coordinating session's review: nobody has an ORCID client to test it with yet.
- **PARK4 University sign-in:** Optional university single sign-on as a Cognito SAML identity provider from a metadata URL in the config. Left out of Plan 4 at the coordinating session's review until an adopter has SAML metadata to test with.
- **PARK5 Reindex catch-up:** Before flipping the active catalog, re-put every package published after the reindex's snapshot time, so a publish during a run isn't lost from the new table. Needed once Plan 7 publishes; until then a reindex runs while publishing is quiet.
- **PARK6 Projects in reindex:** Load project records into the catalog on reindex once Plan 7 decides where a project.json lives in the archive bucket. Until then reindex loads datasets, versions and files only.
- **PARK7 Reserved stage names:** A stage name containing a Cognito reserved word (aws, amazon, cognito) makes the user pool domain prefix fail at deploy. Refuse such names in the Stage model, or encode the prefix, if an adopter ever hits it.
- **PARK8 Reindex at scale:** The reindex's list step checkpoints every manifest key in one result, capped at 256 KB (about 4,000 versions). Write the key list to S3, or list inside each write step, when an archive nears that.
- **PARK9 Reindex failure alerts:** A reindex that fails before the load, or whose status check keeps failing, ends with no reindex alert; only the function's errors alarm fires. Send the reindex alert from those paths too.
- **PARK10 Oversized manifests:** A manifest over DynamoDB's 400 KB item limit fails its version item, so the reindex ends COMPLETED_WITH_ERRORS and never flips. Store large manifests by reference (an S3 key) instead of inline.
- **PARK11 Missing data file is 403:** A request for an open file that doesn't exist returns 403 from /data, not 404: CloudFront's origin access control has GetObject but not ListBucket, so S3 answers 403. Grant s3:ListBucket scoped to open/, or map 403 to 404 on the /data behaviour, so readers and link checkers see a plain not found.
- **PARK12 Leftover helper log group:** Destroying a non-prod stage leaves the log group of CDK's S3 auto-delete helper, which Lambda creates outside CloudFormation. Plan 10a's teardown should delete /aws/lambda/ResearchArchive-&lt;stage>-CustomS3AutoDeleteObjects* after cdk destroy.

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

- [PLAN1](plans/1-config-storage-and-tables.md) Config, storage and tables: built
  - TASK1 Task 1: The infrastructure section of the archive config: done. 1bec0bd; test_config.py exit 0 (11 passed); just check-python check-schema exit 0
  - TASK2 Task 2: Generated config type and the default app: done. 6cbe86d; infra tests and typecheck exit 0; drift check fails (exit 1) on an unregenerated field, passes once regenerated
  - TASK3 Task 3: Storage: done. ab49b4b; infra tests exit 0
  - TASK4 Task 4: Tables and the active-catalog parameter: done. 99e5b52; just check exit 0; review approved, no findings; research-in-a-box#10 CI green, merged as 213f95c
- [PLAN2](plans/2-auth-api-web-and-operations.md) Auth, API, web and operations: built
  - TASK5 Task 1: Lambda packaging, pythonFunction and operations: done. 878a540; just lambda-assets exit 0 (aarch64 pydantic_core .so present); infra tests exit 0
  - TASK6 Task 2: The health and whoami handlers, and the integrity check code: done. 52169bf; pytest packages/backend exit 0 (7 passed); just check-python exit 0
  - TASK7 Task 3: Auth, the API shell and the integrity schedule: done. 0ae57d1; infra tests exit 0
  - TASK8 Task 4: CloudFront: done. 2f63c81 + review fixes; just check exit 0; research-in-a-box#12 CI green (infra files 4-7 s each on CI), merged as 15596b4
- [PLAN3](plans/3-reindex-and-test-deploy.md) Reindex and the test deploy: built
  - TASK9 Task 1: The reindex function: done. 88a218b; pytest packages/backend exit 0 (21 passed, 13 reindex); just check-python exit 0
  - TASK10 Task 2: The reindex in the construct, the just recipes and a test-stage config: done. 7dec535 + review fix; just check exit 0 (343 Python, 41 infra); research-in-a-box#13 CI green, merged as 97151a2
  - TASK11 Task 3: The test deploy: done. ResearchArchive-test deployed from main and every spec check passed after fixes #14 (f1bea57) and #15 (2d8ac81); destroyed cleanly, nothing left in the account

## Steps

- STEP1 Walk the test deploy of the archive with me: done
  1. The user · Name the AWS profile and the alert email address · done: Ready (2026-11-13 16:33, on the page)
  2. The user · Write the profile and the alert email in the note · done. “personal court@subaud.io” (2026-11-13 16:35, on the page)
  3. agent · Check the profile's identity and bootstrap the account and region if needed · done. sts: account 316091283514, AdministratorAccess via SSO; CDKToolkit in us-east-1 already at bootstrap version 28, so no bootstrap; no ResearchArchive-test stack exists yet
  4. agent · Merge the reindex code (PLAN3 tasks 1 and 2) so the deploy runs from main · done. research-in-a-box#13 CI green on all four runs, merged as 97151a2
  5. The user · Go for the deploy · done: Go (2026-11-13 16:58, on the page)
  6. agent · Build the Lambda assets and deploy ResearchArchive-test · done. cdk deploy exit 0 in 206 s, 79 of 79 resources CREATE_COMPLETE; distribution d15sl9pkxent0z.cloudfront.net Deployed
  7. agent · Check health, throttling, an open download, and that restricted data is refused · done. /api/health 200 {"status": "ok"}; /api/whoami without a token 401; 400 requests at 100 concurrent: 383 x 200, 17 x 429; open/sample/1/data/hello.csv downloads from /data/sample/1/data/hello.csv with the same bytes; restricted/ object 403 from /data (also with /data/../restricted); direct S3 URL 403
  8. The user · Confirm the alert subscription email · done (2026-11-13 17:16, on the page)
  9. The user · Sign up once and paste back the URL you land on · done. “screenshot of localhost:8765/callback?code=a6976b99-... from the note” (2026-11-13 17:17, in the terminal)
  10. agent · Exchange the code for a token and call /api/whoami with it · done. PKCE token exchange 200 (access, id, refresh tokens); /api/whoami with the ID token 200: {"email": "court@subaud.io", "groups": []}
  11. agent · Run the integrity check clean, then after one file is overwritten, and check the alert email went out · done. clean run: checked 30, problems 0; after overwriting open/second-sample/1/data/logger.csv: problems 1; alert email "mismatch open/second-sample/1/data/logger.csv" arrived at court@subaud.io (your screenshot)
  12. agent · Upload two sample packages, run just reindex test, and check the catalog flipped to table B · done. after fixes #14 (f1bea57) and #15: just reindex-status test SUCCEEDED {target B, status COMPLETED, items 30, flipped true}; /research-archive/test/catalog-active = B; table B holds DATASET#stream-temperature-sample and DATASET#second-sample, 30 items
  13. The user · Go for the teardown · done: Go (2026-11-13 21:07, on the page)
  14. agent · Destroy ResearchArchive-test and confirm its stack, buckets and tables are gone · done. cdk destroy exit 0; stack does not exist; no researcharchive-test-* buckets, no ResearchArchive-test-* tables or functions, user pool and parameter gone; the CDK auto-delete helper's log group (created by Lambda outside the stack) deleted by hand; nothing left

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
| `screenshots/` | the user | The screenshots the user pasted into a note or the opening. |
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
