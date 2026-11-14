<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# API and search (Plan 6)

`research-archive-in-a-box/api-and-search` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans · 1 wait** → **Build · 0 of 5** → Sign off

PLAN1 building · 0 of 5 done · PLAN3 waits on PLAN1 being built

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

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The plans](spec.md#the-plans): rests on DCSN5, DCSN1
- [Endpoints](spec.md#endpoints): rests on DCSN4, AGNT1, AGNT8
- [Search](spec.md#search): rests on DCSN1, AGNT2, AGNT3, AGNT4
- [Restricted downloads](spec.md#restricted-downloads): rests on DCSN2, AGNT9
- [Download counts](spec.md#download-counts): rests on AGNT7
- [Usage form](spec.md#usage-form): rests on DCSN3, AGNT10
- [Sign-in for the CLI and MCP server](spec.md#sign-in-for-the-cli-and-mcp-server): rests on AGNT5
- [How it is built](spec.md#how-it-is-built): rests on DCSN4, AGNT6, AGNT11
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN2, DCSN4
- [Left out](spec.md#left-out): rests on DCSN5, DCSN3, AGNT5
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, DCSN3, DCSN4

## Plans

- [PLAN1](plans/1-read-api-and-catalog-search.md) The read API, server search and downloads: building · 0 of 5 done
  - TASK1 Task 1: The catalog file and its writer: not started
  - TASK2 Task 2: The API Lambda: not started
  - TASK3 Task 3: The download rollup: not started
  - TASK4 Task 4: The infrastructure: not started
  - TASK5 Task 5: The test deploy: not started
- PLAN3 Semantic search: waits on PLAN1 being built

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
