---
diazo: research-archive-in-a-box/api-and-search
file: wrap-up
status: printed
hash: b99928af09f3cb7a0a5f0cc060d83bdd401036f50d2f101fbe21863cd34b0329
rests_on: [PLAN1, PLAN3]
record: README.md
---

# Anyone can now find and fetch a dataset through the archive's API, by its words or by its meaning.

## How it works now

The archive answers search, dataset, version and project reads to anyone, from the web app, the CLI or an MCP server, through one endpoint, `/api/search`, and a handful of read routes. Search ranks datasets by how many of the reader's words they match, and an archive can switch on semantic search in `archive.yaml` so that searches like "air pollution" find the aerosol dataset even when those words never appear. Restricted files reach only people the archive invited: sign-up is off, an admin invites with `just invite-user`, and a signed-in user gets a five-minute link. The archive counts downloads every day and can ask readers, optionally, how they use the data.

## Results

- The read API, server search over catalog.json, restricted links, download counts and the usage form: PLAN1, research-in-a-box#22.
- Invitation-only accounts and `just invite-user`: PLAN1, research-in-a-box#26.
- Ranked keyword search and optional semantic search with Titan v2 and a DynamoDB vector index: PLAN3, research-in-a-box#30.
- Semantic search on Plan 7's publish step: PLAN3, research-in-a-box#38.

## Different from the plan

- The handoff planned search in the browser with DuckDB; after measuring, you chose search on the server instead.
- PLAN2 (submission, review and settings endpoints) was dropped when Plan 7 took everything under `/api/submissions`.
- PLAN1 gained Task 6, invitation-only accounts, at your word during its test deploy.
- PLAN3 gained Task 12, the embedding call in Plan 7's publish, because Plan 7's publish landed first.
- The search keyword matching changed from every word to any word ranked by matches, after measuring it on Plan 5's datasets.
