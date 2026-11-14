<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# API and search (Plan 6)

`research-archive-in-a-box/api-and-search` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 6 of 11** → Sign off

PLAN1 built · PLAN3 building · 0 of 5 done

## Pick up next

- **PARK1 Linked resource downloads:** A resource whose path is a URL (data held elsewhere) gets a file item, so the download route answers a /data or presigned link that doesn't resolve. Answer the resource's own URL instead.
- **PARK2 Expire CloudFront logs:** Nothing expires the derived bucket's logs/, and the daily rollup lists the whole prefix each run, so the listing grows forever. Add a lifecycle rule on logs/ (say 30 days, after the rollup has counted them) or list from the last counted day's key.
- **PARK3 First search after idle:** On the test deploy the first search after 17 idle minutes took 2.81 s (warm searches 0.14 s median), above the about one second the spec estimated: a cold API Lambda loading Powertools, boto3 and the catalog. Measure the parts and decide whether it matters once Plan 8's search page exists; options are trimming imports, more memory, or SnapStart for Python.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 2, folder 8da653f233f9, and Plan 4, the archive infrastructure.)
> 
> Brief: Plan 6 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the API and search (Plan 6). There is no relational database. Search is a catalog file filtered in the browser with DuckDB, plus an optional DynamoDB vector index. Plan the endpoints and the search design, and take the open questions with me one at a time.

## Decisions

- **DCSN1 Where search runs.** Where should the catalog be searched: in the reader's browser, or by the API? The user chose C: On the server, through a search endpoint.
- **DCSN2 Who reads restricted data.** Who may download a dataset marked restricted? The user chose A: Anyone signed in.
- **DCSN3 Optional usage form.** Should the optional 'who are you and how will you use this' form be built now, or later? The user chose B: Now.
- **DCSN4 How the API is built.** Should the endpoints be one Lambda using Powertools' router, or one Lambda per endpoint? The user chose A: One API Lambda with Powertools' REST router.
- **DCSN5 Keep or drop PLAN2.** Plan 7 now owns the submission and review endpoints. Should PLAN2 be dropped? The user chose A: Drop PLAN2.
- **DCSN6 Semantic search now or later.** Should PLAN3 build semantic search now, or first fix keyword search and add semantic search once the search page has real readers? The user chose B: Fix keyword search and build semantic search now.
- **DCSN7 Embedding model.** Which Bedrock model should turn datasets and searches into vectors: Amazon Titan Text Embeddings v2 or Cohere Embed v4? The user chose A: Amazon Titan Text Embeddings v2.
- **DCSN8 Merging keyword and semantic.** How should /api/search combine the keyword matches and the semantic matches into one list? The user chose A: Reciprocal rank fusion.
- **AGNT1 Reads from the active table.** `GET /api/datasets/{id}`, `GET /api/datasets/{id}/versions` and `GET /api/datasets/{id}/versions/{version}` read the active catalog table (the version item already holds the manifest text, plus the file items). Finding datasets is search's job (DCSN1), not a separate list endpoint. The user kept it.
- **AGNT2 One catalog writer.** One function in archive-backend builds the catalog file from the active catalog table and writes it to the derived bucket's `site/`. The reindex calls it after it flips the table; Plan 7's publish step calls the same function later. The user kept it.
- **AGNT3 Catalog fields.** One row per published dataset, every access level: id, current version, title, description, keywords, access, license ids and rights status, project, creators, resource formats, temporal start, end and ongoing, the bounding box (west, south, east, north), total bytes and published date. Theme and species facets join when the contract holds those fields: Plan 2's follow-ups PARK5 (archive:themes) and PARK6 (taxonomic coverage), timing yours. The user kept it.
- **AGNT4 Catalog freshness.** The search Lambda keeps `catalog.json` in memory and checks the object's ETag in S3 at most once a minute, re-reading it when it changed. A publish or reindex reaches search within a minute, with no invalidation or notification. The user kept it.
- **AGNT5 CLI and MCP sign-in.** Authorization code with PKCE through Plan 4's `cli` app client: the client opens the browser to managed login and listens on `http://localhost:8765/callback`. It keeps the one-hour access and ID tokens and discards the refresh token, so it holds short-lived tokens only. Plan 6 records the flow in the Decision log; the client code lands with its first user, Plan 9. The user kept it.
- **AGNT6 OpenAPI is committed.** The OpenAPI spec is written to a committed file by a `just` recipe and CI fails when it drifts from the code, the same way the contract's JSON Schema is checked. Plan 8 generates its TypeScript types from it. The user kept it.
- **AGNT7 What counts as a download.** A daily scheduled function reads the new CloudFront log files under the derived bucket's `logs/` and adds one per GET under `/data/` that answered 200, per dataset and month. Range reads (206) and HEAD are not counted, so the in-browser data preview, which reads by range, doesn't inflate counts. A restricted download counts when its link is issued. The user kept it.
- **AGNT8 Project reads from the archive.** `GET /api/projects/{id}` reads `projects/&lt;projectId>/project.json` from the archive bucket (the home Plan 7 and the coordinating session settled) and lists the project's datasets from the active catalog table's GSI1. No reindex change: the record is read where it lives. The user kept it.
- **AGNT9 Link lifetime.** Five minutes: long enough to start a large download, short enough that a shared link stops working. The user kept it.
- **AGNT10 Usage form shape.** Three optional answers, no sign-in needed and no email or name asked: what kind of organisation (university, government, nonprofit, company, individual, other), what the data is for (research, teaching, policy or management, commercial, personal, other), and a free-text note of up to 500 characters. `POST /api/datasets/{id}/usage` stores them in a new UsageResponses table Plan 6 adds (key `datasetId`, sort `&lt;month>#&lt;uuid>`), and `GET /api/admin/usage?dataset=&lt;id>` lets the admin group read them. The question list is fixed in the contract, not set in the config. The user kept it.
- **AGNT11 Config read from SSM.** Through the SSM parameter `/research-archive/&lt;stage>/archive-config` that Plan 7's spec has the CDK app write at synth from the validated archive.yaml. PLAN1's Lambdas need nothing from it yet; PLAN3's embeddings setting will be read the same way. The user kept it.
- **AGNT12 Embeddings off by default.** A new optional module in the archive config, `infrastructure.modules.embeddings` with the model id, off by default like WAF and write-once locking. Switched on, the construct adds the vector index to both catalog tables and grants Bedrock; the API reads the setting from the archive-config parameter. Off, search is the improved keyword search alone. The user kept it.
- **AGNT13 How many semantic matches.** SearchVectors asks for the 50 nearest (the service allows at most 100), the search's filters (access, licence, format, project, dates, box) are applied to them in the Lambda as they are to keyword matches, and the merged list is paged as today. The total counts the merged list. The user kept it.
- **AGNT14 Vector index shape.** One index, `datasets`, on both catalog tables: attribute `embedding` on the dataset's META item (a list of 1,024 numbers from Titan v2, normalised), COSINE distance, KEYS_ONLY projection, and no vector partition key. Each archive has its own tables, so the whole index is one archive, which is how 'one partition key per archive' in the handoff is met. The user kept it.
- **AGNT15 When Bedrock fails.** The keyword results alone, with a warning in the function's log, so the reader still gets a page. Errors on reindex or publish stop that run, as any other failed step does. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The plans](spec.md#the-plans): rests on DCSN5, DCSN1, DCSN6
- [Endpoints](spec.md#endpoints): rests on DCSN4, AGNT1, AGNT8
- [Search](spec.md#search): rests on DCSN1, AGNT2, AGNT3, AGNT4, DCSN6
- [Semantic search](spec.md#semantic-search): rests on DCSN6, DCSN7, DCSN8, AGNT12, AGNT13, AGNT14, AGNT15, AGNT11
- [Restricted downloads](spec.md#restricted-downloads): rests on DCSN2, AGNT9
- [Download counts](spec.md#download-counts): rests on AGNT7
- [Usage form](spec.md#usage-form): rests on DCSN3, AGNT10
- [Sign-in for the CLI and MCP server](spec.md#sign-in-for-the-cli-and-mcp-server): rests on AGNT5
- [How it is built](spec.md#how-it-is-built): rests on DCSN4, AGNT6, AGNT11
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN2, DCSN4, DCSN7
- [Left out](spec.md#left-out): rests on DCSN5, DCSN3, AGNT5
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, DCSN3, DCSN4, DCSN6, DCSN8

## Plans

- [PLAN1](plans/1-read-api-and-catalog-search.md) The read API, server search and downloads: built
  - TASK1 Task 1: The catalog file and its writer: done. 160a71b, fc3b233: catalog writer, publishedAt from Manifest.published, reindex step; pytest backend+contract exit 0, check-python 0, check-schema 0
  - TASK2 Task 2: The API Lambda: done. 9fb6870: search.py, Powertools api.py with 8 routes, UsageAnswers, openapi.json under check-schema; all checks exit 0
  - TASK3 Task 3: The download rollup: done. d39cfe3: daily rollup with the rolled-up-through marker; pytest backend exit 0, check-python 0
  - TASK4 Task 4: The infrastructure: done. 17f937d plus review fixes 8ab0e43, 1e70452, 6fa02b8; merged as research-in-a-box#22 (6608bba), CI python and typescript pass
  - TASK5 Task 5: The test deploy: done. ResearchArchive-test deployed from main and walked: reindex wrote catalog.json, search filters and facets right, reads, restricted link (checksum match, traversal 404, signed-out 401), invited sign-in, usage form and admin read, rollup counted once; search warm median 0.14 s, after idle 2.81 s (PARK3); destroyed with nothing left
  - TASK6 Task 6: Invitation-only accounts: done. 2989c53: selfSignUpEnabled false (synth test RED then GREEN), just invite-user, Decision log row; just check exit 0; merged as research-in-a-box#26 (aa90504)
- [PLAN3](plans/3-semantic-search.md) Ranked keyword search and semantic search: building · 0 of 5 done
  - TASK7 Task 7: Ranked keyword matching: not started
  - TASK8 Task 8: The embeddings setting and the shared function: not started
  - TASK9 Task 9: Semantic results in /api/search: not started
  - TASK10 Task 10: The vector index and permissions: not started
  - TASK11 Task 11: The test deploy: not started

## Steps

- STEP1 Walk the test deploy of Plan 6's read API and search with me: done
  1. The user · Name the AWS profile and the alert email address · done. “personal court@subaud.io” (2026-11-13 22:41, on the page)
  2. agent · Open the PR for Tasks 1 to 4, merge it once CI's python and typescript checks pass, and check the profile's identity · done. research-in-a-box#22 merged as 6608bba after python and typescript passed; profile personal is account 316091283514, us-east-1
  3. The user · Go for the deploy · done: Go (2026-11-13 23:10, on the page)
  4. agent · Build the Lambda assets, deploy ResearchArchive-test, upload two sample packages (one open, one restricted, each with archive:published), run just reindex test, and check catalog.json, search, reads and a signed-out download refused · done. deploy exit 0; reindex SUCCEEDED (B, 30 items, catalog 2 rows); /catalog.json 200 max-age=60, 2 rows; search 'stream temperature' 2 hits, access=restricted 1, facets add up; dataset read returns manifest + 13 files; unknown dataset 404; signed-out download 401
  5. agent · Merge Task 6 (invitation-only accounts, research-in-a-box#26) and update the stack so sign-up is off, then invite you with just invite-user test · done. #26 merged as aa90504; stack update exit 0 in 51 s; AllowAdminCreateUserOnly true; just invite-user test court@subaud.io: FORCE_CHANGE_PASSWORD, invitation emailed
  6. The user · Sign in with the invitation and paste back the URL you land on · done. “why is this still failing on the callback” (2026-11-13 23:28, on the page)
  7. agent · Exchange the code, fetch the restricted file through its link, post a usage answer, see the admin read refused, then add you to the admin group · done. PKCE exchange 200 (1-hour tokens); whoami court@subaud.io, no groups; restricted link 200, file fetched, SHA-256 matches checksums.sha256; ../../ path 404; open link answers its /data URL; DownloadCounts restricted=1 for 2026-11; usage POST 204; admin read 403; added to admin
  8. The user · Sign in again and paste back the URL · done (2026-11-13 23:34, on the page)
  9. agent · Read the usage answer as admin, count an open download through the rollup, and time searches warm and after idle · done. whoami groups [admin]; admin usage read 200 with the posted answer; rollup through today counted the /data download (open=1 for 2026-11), a rerun counted 0; search through CloudFront: warm median 0.14 s (min 0.09, max 0.27, n=10), after 17 idle minutes 2.81 s, then 0.15 s
  10. The user · Go for the teardown · done: Go (2026-11-13 23:53, on the page)
  11. agent · Destroy ResearchArchive-test and confirm its stack, buckets and tables are gone · done. cdk destroy exit 0; stack does not exist; no researcharchive-test buckets, tables or functions; user pool and /research-archive/test parameters gone; the S3 auto-delete helper's leftover log group deleted by hand; nothing left

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
