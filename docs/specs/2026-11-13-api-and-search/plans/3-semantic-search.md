---
diazo: research-archive-in-a-box/api-and-search
file: PLAN3
status: approved
approved: 2026-11-14T00:23:08-06:00
hash: 0cb69533179c64e634fb8e2aae834c93e901549596c38885654aa3fd5a54ab32
rests_on: [AGNT11, AGNT12, AGNT13, AGNT14, AGNT15, DCSN6, DCSN7, DCSN8]
record: README.md
---

# PLAN3: Ranked keyword search and semantic search

## Spec

`docs/specs/2026-11-13-api-and-search/spec.md`, sections "Search", "Semantic search", "Risk and cost" and "How we'll know it works". PLAN1 is built and merged (research-in-a-box#22, #26): build on `archive_backend.search`, `archive_backend.api`, `archive_backend.reindex` (`catalog_items`, `dataset_item`), `archive_backend.catalog_file`, the `ReadApi` construct and Plan 4's `Tables`. The handoff's Decision log holds the catalog item shapes. The measurements behind DCSN6 to DCSN8 are on those cards. The implementer reads the spec beside this plan.

## The change

Keyword search ranks by how many words match instead of requiring every word. An optional `embeddings` module adds a vector index to both catalog tables, one shared function puts a Titan v2 embedding on each dataset item before it is written, and `/api/search` merges the vector index's nearest datasets with the keyword ranking by reciprocal rank fusion. Then one test deploy with Plan 5's ten datasets, embeddings on and then off, and the stack is destroyed.

**Risk:**

- Tasks 1 to 4 are local code and CI; a mistake is undone by reverting the PR.
- Nothing here can expose a restricted file: search returns catalog rows, which are public at every access level.
- A bad embedding or a dropped one only changes ranking, and a reindex rebuilds every embedding.
- Task 5 creates real resources under a non-prod stage, all deleted with the stack, plus a few cents of Bedrock calls.

**Cost:**

- One walkthrough step for you (STEP2): Go for the deploy and Go for the teardown. No sign-in is needed; search is public.
- New permissions only when the module is on: `bedrock:InvokeModel` on Titan v2 and `dynamodb:SearchVectors` on the index.
- No new dependency: boto3 already has Bedrock and DynamoDB.

## Left out

- A score cut-off for semantic matches, and any model besides Titan v2 (spec, Left out).
- Embedding the CLI or MCP server's own searches: they call `/api/search` like the web app.
- Plan 7's call to the embedding function: whichever of Plan 6 and Plan 7 lands second adds it (muster thread 955).
- The first search after idle (PARK3) stays its own follow-up; Task 5 measures it again with embeddings on.

## Where

- Worktree `/Users/courtschuett/GitHub/personal/.worktrees/research-archive-in-a-box/plan6/semantic-search`, branch `plan6/semantic-search` from `origin/main`. Confirm with `git -C <wt> branch --show-current` before editing.
- Python: `packages/contract/src/archive_contract/config.py` with its test, `packages/backend/src/archive_backend/{search,embeddings,api,reindex}.py` with their tests.
- TypeScript: `packages/infra/src/tables.ts`, `packages/infra/src/read-api.ts`, `packages/infra/src/reindex.ts`, `packages/infra/src/research-archive.ts`, their tests, and the regenerated `packages/infra/src/generated/archive-config.ts`.
- `packages/web/src/schema/archive-contract.schema.json` and `openapi.json` (regenerated), `docs/planning-handoff.md` (Decision log).
- Global constraints:
  - Lambdas read the embeddings setting only from the archive-config parameter, `/research-archive/<stage>/archive-config`, which Plan 7's PLAN1 adds. If it isn't on `origin/main` when Task 2 starts, Tasks 1 to 2's pure code goes ahead and the reading waits for it; never add a second way to read the config.
  - The embedding is set on the item before it is written, never by a later UpdateItem (muster thread 955).
  - `just check` must exit 0. Nothing reaches AWS in Tasks 1 to 4.
  - Task 5 runs only with your Go on STEP2, under the `personal` profile, on a stage named `search-test`, never `prod`.
  - On any AWS auth error, stop and report; never copy or export credentials.

### Task 7: Ranked keyword matching

**Does:** Changes `archive_backend.search` so a dataset matches when any word of `q` matches, ranked by how many words match with title words counting half again, common words ignored and plurals matched.
**Files:** `packages/backend/src/archive_backend/search.py`, `packages/backend/tests/test_search.py`
**Checks:** `uv run pytest packages/backend` exits 0; `just check-python` exits 0.
**Serves:** DCSN6

- Words: lower-case `[a-z0-9]+` runs of `q`, minus a fixed stop list (`a an and the of on in near from for to with by at as or`), each reduced by stripping a trailing `ies`, `es` or `s`; a field matches a word when the reduced word appears in it.
- Score: count of words found in title, description, keywords or creators, plus 0.5 per word found in the title. A row with score 0 doesn't match when `q` is given.
- Order: score descending, then `published` newest first with rows lacking it last, then `id`. With no `q`, order as today.
- Facets: the `q` filter counts as "score above 0", so facet counting is unchanged otherwise.
- Expose `keyword_ranking(rows, q) -> list[str]` (ids in order) for Task 9's merge.
- Tests: "ozone damage on plants" finds the ozone row first; a title word outranks a description-only word; "species" matches "Species"; "on the" alone matches nothing; existing filter, facet and paging tests keep passing.

### Task 8: The embeddings setting and the shared function

**Does:** Adds the optional `infrastructure.modules.embeddings` setting to the contract, and `archive_backend.embeddings.with_embedding(item, manifest, bedrock)`, which returns the dataset item with `embedding` set; the reindex calls it on every dataset item when the setting is on.
**Files:** `packages/contract/src/archive_contract/config.py`, `packages/contract/tests/test_config.py`, `packages/web/src/schema/archive-contract.schema.json`, `packages/infra/src/generated/archive-config.ts`, `packages/backend/src/archive_backend/embeddings.py`, `packages/backend/tests/test_embeddings.py`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_reindex.py`, `docs/planning-handoff.md`
**Checks:** `uv run pytest packages/backend packages/contract` exits 0; `just check-python` exits 0; `just check-schema` exits 0.
**Serves:** DCSN6, DCSN7 (rests on calls AGNT11, AGNT12, AGNT14)

- Contract: `Modules.embeddings: Embeddings | None` (alias `embeddings`), where `Embeddings` is a strict model with `model: Literal["amazon.titan-embed-text-v2:0"]` defaulting to that value. Present means on. Run `just schema`.
- `MODEL`, `DIMENSIONS = 1024`. `embedding_text(manifest)` is the title, description and keywords joined by newlines, as measured. `embed(bedrock, text)` calls `invoke_model` with `{"inputText": text, "dimensions": 1024, "normalize": true}` and returns the list. `with_embedding(item, manifest, bedrock)` returns a copy of the DynamoDB-JSON item with `"embedding": {"L": [{"N": ...}, ...]}`.
- Reindex: read the archive config from the archive-config parameter once per run; when `infrastructure.modules.embeddings` is set, each dataset item passes through `with_embedding` inside the write step, before the lines are written. Off, nothing changes.
- One Decision log row: the setting's name, `with_embedding` as the one way an embedding is set, called before the put by reindex and by Plan 7's publish.
- Tests with a fake Bedrock: the item gains a 1,024-number list and keeps every other attribute; the reindex calls it once per dataset when on and never when off.

### Task 9: Semantic results in /api/search

**Does:** When the setting is on and `q` is given, `/api/search` embeds `q`, asks the index for 50 nearest datasets, and merges them with the keyword ranking by reciprocal rank fusion before filtering and paging; on a Bedrock or index error it answers the keyword ranking alone.
**Files:** `packages/backend/src/archive_backend/search.py`, `packages/backend/src/archive_backend/api.py`, `packages/backend/tests/test_search.py`, `packages/backend/tests/test_api.py`, `packages/web/src/schema/openapi.json`
**Checks:** `uv run pytest packages/backend` exits 0; `just check-python` exits 0; `just check-schema` exits 0.
**Serves:** DCSN6, DCSN8 (rests on calls AGNT13, AGNT15)

- `search(rows, query, semantic: list[str] | None = None)`: with `semantic`, the candidates are the union of keyword matches and the semantic ids, ordered by `fuse(keyword_ids, semantic_ids)` where each id scores the sum of `1 / (60 + place)` over the lists it appears in (place from 1), ties by `id`. Filters other than `q`, facets, total and paging work on that list as they do today.
- `api.py`: read the setting from the archive-config parameter (cached like the active table); with it on and `q` non-empty, `embed(q)` then `dynamodb.search_vectors(TableName=<active table>, IndexName="datasets", SearchVector=..., TopK=50)` and take the ids from the returned keys. Verify the boto3 parameter and response names against the installed botocore, not this plan.
- Any exception from Bedrock or `search_vectors` logs a warning, emits one `SemanticFallback` count in CloudWatch embedded metric format (namespace `ResearchArchive`, dimension `Stage`, from the `STAGE` environment variable), and calls `search` without `semantic`.
- Tests: fusion order on two hand-made lists; a semantic-only id appears and a filter still removes it; facets count the merged list; the error path answers keyword results and prints one metric line; with the setting off Bedrock is never called.

### Task 10: The vector index and permissions

**Does:** When `infrastructure.modules.embeddings` is set, adds the `datasets` vector index to both catalog tables, grants the API and reindex functions Bedrock on Titan v2 and the API `SearchVectors`, and puts the `SemanticFallback` count on the dashboard with an alarm.
**Files:** `packages/infra/src/tables.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/src/read-api.ts`, `packages/infra/src/reindex.ts`, `packages/infra/src/operations.ts`, `packages/infra/test/tables.test.ts`, `packages/infra/test/read-api.test.ts`, `packages/infra/test/reindex.test.ts`, `packages/infra/test/operations.test.ts`
**Checks:** `npm test -w packages/infra` exits 0; `just check` exits 0.
**Serves:** DCSN6, DCSN7 (rests on calls AGNT12, AGNT14)

- `Tables` takes `embeddings: boolean`. When true, on each catalog table's `node.defaultChild as dynamodb.CfnTable`, set `vectorIndexes` to one entry: `indexName: "datasets"`, `vectorAttribute: { attributeName: "embedding" }`, `dimensions: 1024`, `distanceFunction: "COSINE"`, `projection: { projectionType: "KEYS_ONLY" }`, no `searchSchema`. Plain `dynamodb.Table` stays (Decision log: bulk put items needs it).
- Grants when on: `bedrock:InvokeModel` on `arn:aws:bedrock:<region>::foundation-model/amazon.titan-embed-text-v2:0` for the API and reindex functions; `dynamodb:SearchVectors` on `<table arn>/index/datasets` for both tables, for the API function.
- The API function gets `STAGE`. When on, the operations dashboard gains a `SemanticFallback` widget, and one alarm on its sum, at least 5 in 15 minutes for 2 periods, notifies the alert topic, so an admin learns the module is failing rather than seeing weaker search.
- Synth tests: with the module the index, grants, widget and alarm exist; without it, the template has no `VectorIndexes`, no Bedrock statement and no fallback alarm.

### Task 11: The test deploy

**Does:** Merges Tasks 7 to 10, deploys `ResearchArchive-search-test` with embeddings on, loads Plan 5's ten datasets, checks the spec's semantic checks, turns embeddings off and checks again, then destroys the stack.
**Files:** none (results go in the task's result line and the build thread)
**Checks:** every action in STEP2 is done; `aws cloudformation describe-stacks --stack-name ResearchArchive-search-test` fails with "does not exist" at the end.
**Serves:** DCSN6, DCSN7, DCSN8

STEP2's actions, in order:

1. Agent: open the PR for Tasks 7 to 10 and merge it once CI's `python` and `typescript` checks pass.
2. You: Go for the deploy.
3. Agent: deploy with a test config that has `stages: [search-test]` and `modules.embeddings: {}`; upload only each of Plan 5's ten packages' `datapackage.json` from `practice-data/packages/` (never committed), with `archive:published` set, under `open/` or `restricted/` by its access: the reindex and search read manifests only, and no FEMC data file is put where the test stage's CloudFront could serve it; `just reindex search-test`; check each dataset item has a 1,024-number `embedding`; run the 22 searches from DCSN6 through CloudFront and record found-first and top-3 counts; check `q=air pollution` puts the IMPROVE aerosol dataset first; time ten warm searches and one after 15 idle minutes.
4. Agent: redeploy with the module removed; check `q=air pollution` answers keyword results (none) with no error, and `q=ozone` still finds the ozone dataset.
5. You: Go for the teardown.
6. Agent: destroy the stack and confirm the stack, buckets, tables and leftover log groups are gone.
