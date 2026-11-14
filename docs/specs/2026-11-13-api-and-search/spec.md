---
diazo: research-archive-in-a-box/api-and-search
file: spec
status: approved
approved: 2026-11-13T22:34:38-06:00
hash: efa1b5a93f7112fe9b6cff14c4cc1080bccf324ed32eb7c081e9c0f985e3eb41
rests_on: [DCSN5, DCSN1, DCSN4, AGNT1, AGNT8, AGNT2, AGNT3, AGNT4, DCSN2, AGNT9, AGNT7, DCSN3, AGNT10, AGNT5, AGNT6, AGNT11]
record: README.md
---

# API and search: the read API, server search and downloads

## Goal

Anyone can find a dataset in the archive and fetch it, from the web app, the CLI or an MCP server, with no relational database. A read API open to all answers search, dataset, version and project reads; signed-in users get short-lived links to restricted files; the archive counts downloads and, optionally, asks readers how they use the data. It works today on what Plan 4's reindex loads, and Plan 7's publish step plugs into it later. Semantic search follows as its own plan once there is a real corpus to judge it on.

## The plans

Plan 6 is two plans in this folder. PLAN1 is the read API and search described below, buildable now. PLAN3 is semantic search: the vector index on both catalog tables, the embedding model and its setting, and ranking semantic results with keyword results inside the same search endpoint; it is written once PLAN1 is built and Plan 5's corpus exists. Plan 7 owns everything under `/api/submissions`, including the review-policy setting, so there is no PLAN2.

Rests on: DCSN5, DCSN1

## Endpoints

Every route is served by one Python Lambda, declared in API Gateway one route at a time so the Cognito authorizer sits only on the signed-in ones. Plan 4's `/api/health` and `/api/whoami` stay as they are.

| Route | Sign-in | Answers |
|---|---|---|
| `GET /api/search` | no | One page of matching datasets with a count per facet value (below) |
| `GET /api/datasets/{id}` | no | The dataset, its current version's manifest and its files |
| `GET /api/datasets/{id}/versions` | no | Every version's number and prefix |
| `GET /api/datasets/{id}/versions/{version}` | no | That version's manifest and files |
| `GET /api/projects/{id}` | no | `projects/<id>/project.json` from the archive bucket, and the project's datasets from GSI1 |
| `GET /api/datasets/{id}/versions/{version}/download?path=` | yes | A five-minute link to one restricted file |
| `POST /api/datasets/{id}/usage` | no | Stores the optional usage answers |
| `GET /api/admin/usage?dataset=` | yes, `admin` group | The usage answers for one dataset |

Dataset, version and file reads come from the active catalog table, chosen by the `/research-archive/<stage>/catalog-active` parameter, cached for a minute as Plan 4's Lambdas do. The version item already holds the manifest text. Metadata is public at every access level; only files are restricted. A missing dataset, version or project answers 404.

Rests on: DCSN4, AGNT1, AGNT8

## Search

**The catalog file.** One function in `archive-backend` builds `catalog.json` from the active catalog table and writes it to the derived bucket's `site/`, so it is also public at `/catalog.json`. The reindex calls it after it flips the active table; Plan 7's publish step calls the same function. One row per published dataset at every access level: `id`, `version`, `title`, `description`, `keywords`, `access`, `licenses` (ids), `rightsStatus`, `project`, `creators`, `formats`, `start`, `end`, `ongoing`, `bbox` (west, south, east, north), `bytes` (the current version's total) and `published`. Theme and species join when the contract holds those fields (Plan 2's PARK5 and PARK6). It is written with Python's standard library; no DuckDB.

**The endpoint.** `GET /api/search` takes `q` (keywords), `access`, `license`, `format`, `project` (each repeatable), `from` and `to` (dates), `bbox` (`west,south,east,north`), `page` and `size` (default 20, at most 100). Each keyword must appear, ignoring case, in the title, description, keywords or creators. Date filters keep a dataset whose coverage overlaps the range; the box keeps a dataset whose box intersects it, including boxes that cross the antimeridian. Results with a keyword in the title come first, then the rest, newest published first. The answer is the page of rows (the same fields as the catalog file, so a result card needs no further call), the total, and a count for each value of `access`, `license`, `format` and `project` under the current filter.

**Freshness.** The search Lambda keeps the parsed catalog in memory and checks the object's ETag at most once a minute, re-reading it when it changed, so a publish or reindex reaches search within a minute. Filtering 10,000 datasets took 9 ms in a measurement on a laptop; past roughly 50,000 datasets, the next step is an index rather than an in-memory list.

Rests on: DCSN1, AGNT2, AGNT3, AGNT4

## Restricted downloads

Open files are fetched straight from CloudFront at `/data/<datasetId>/<version>/<path>`; the API isn't involved. For a restricted dataset, a signed-in user calls the download route and gets an S3 presigned link to `restricted/<datasetId>/<version>/<path>` that lasts five minutes. Anyone signed in qualifies; signing up is self-service with email. The path must be one of the version's file items, so the route can't be used to reach any other key. A by-request dataset answers 403 until Plan 7's request workflow can grant access, which this check will then read. Description-only datasets have no files. An open dataset's download route answers its `/data` URL.

Rests on: DCSN2, AGNT9

## Download counts

DownloadCounts keeps, per dataset and month, `open` (downloads through CloudFront) and `restricted` (links issued). The download route adds one to `restricted` when it issues a link. A scheduled function runs daily, reads the previous day's CloudFront standard logs under the derived bucket's `logs/`, and adds one to `open` per `GET` under `/data/` that answered 200; range reads (206) and `HEAD` don't count, so a data preview that reads by range doesn't inflate the numbers. The last day rolled up is kept as a Settings item, `downloads-rolled-up-through`, so a rerun never counts a day twice.

Rests on: AGNT7

## Usage form

Before a download, a reader may answer three optional questions, with no sign-in and no name or email: the kind of organisation (university, government, nonprofit, company, individual, other), what the data is for (research, teaching, policy or management, commercial, personal, other), and a note of up to 500 characters. The question list is a model in the contract. Answers go to a UsageResponses table that Plan 6 adds (`datasetId`, sort key `<month>#<uuid>`, on-demand, point-in-time recovery like the other operational tables). Admins read them through `GET /api/admin/usage`.

Rests on: DCSN3, AGNT10

## Sign-in for the CLI and MCP server

The browser signs in through Plan 4's `web` client as built. The CLI and the MCP server use authorization code with PKCE through Plan 4's `cli` client: they open the browser to Cognito's managed login and listen on `http://localhost:8765/callback`. They keep the one-hour access and ID tokens and discard the refresh token, so they hold short-lived tokens only. Plan 6 records this in the handoff's Decision log; the client code is built by its first user, Plan 9.

Rests on: AGNT5

## How it is built

The routes live in one module of `archive-backend` on Powertools' `APIGatewayRestResolver` with validation on, each with Pydantic request and response models. A `just openapi` recipe writes the OpenAPI spec from those routes to a committed file, and CI fails when the committed file and the code disagree, as it already does for the contract's JSON Schema; Plan 8 generates its TypeScript types from it. The CDK side is one internal construct in `packages/infra` that `ResearchArchive` creates: the API Lambda and its routes on Plan 4's `api` and `authorizer`, the UsageResponses table, the daily download rollup on a schedule, and the reindex's call to the catalog writer. Any Lambda that needs the archive config reads it from `/research-archive/<stage>/archive-config`; PLAN1's need nothing from it.

Rests on: DCSN4, AGNT6, AGNT11

## Risk and cost

**Risk.** A mistake could hand a restricted file to someone it shouldn't reach, for instance a download route that signs any key it is given. Links last five minutes, the route signs only paths listed in the version's file items, and CloudFront is denied `restricted/*` outright, so a fix and a redeploy close it; tests cover a signed-out call, a path outside the version, and a by-request dataset. Nothing here deletes or rewrites a package: every endpoint reads, and the only writes are counts, usage answers and the derived catalog file, all rebuildable or disposable.

**Cost.** One test deploy to an AWS account you choose and its teardown, each a step for you on the page. No new programs on your machine; `aws-lambda-powertools` joins `archive-backend`. Running cost is one Lambda call per search and per read, a daily rollup and a small table, pennies a month for a small archive.

Rests on: DCSN2, DCSN4

## Left out

- Submission, review and review-policy endpoints: Plan 7's.
- Semantic search, the embedding model and the vector index: PLAN3.
- Theme and species facets: when Plan 2's PARK5 and PARK6 add the fields.
- The CLI and MCP sign-in client code: Plan 9, its first user.
- An admin route to start a reindex: stays Plan 4's follow-up PARK1.
- Config-defined usage questions, or asking for an email: until an archive asks.
- A search index for archives past about 50,000 datasets.

Rests on: DCSN5, DCSN3, AGNT5

## How we'll know it works

- `just check` passes, including tests for search filters, facet counts, paging and the antimeridian box; for the download route refusing a signed-out call, a path outside the version and a by-request dataset; for the rollup counting 200s only and never counting a day twice; and the OpenAPI drift check.
- On one test deploy with two datasets loaded by `just reindex` (one open, one restricted): `GET /api/search?q=` finds each by a word in its description and the facet counts add up; `GET /api/datasets/<id>` returns the manifest and files; a signed-in user's download link fetches the restricted file and expires; the same call signed out answers 401; a usage answer posts and an admin reads it back; after an open download through `/data` and a run of the rollup, DownloadCounts shows it.
- The round trip of a search through CloudFront, warm and after idle, is measured on that deploy and written in the plan's result.

Rests on: DCSN1, DCSN2, DCSN3, DCSN4
