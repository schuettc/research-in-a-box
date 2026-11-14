---
diazo: research-archive-in-a-box/web-app-catalog-and-curation
file: PLAN1
status: done
approved: 2026-11-14T00:49:48-06:00
hash: f082f033dae320321876f533922e70d4a2eafcb99e663a571c400d3fe4632264
rests_on: [AGNT1, AGNT10, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, AGNT8, AGNT9, DCSN1]
record: README.md
---

# PLAN1: The reader's flow

## Spec

`spec.md` in this folder, approved. This plan builds everything it describes for readers: routes, search, the dataset page, downloads and sign-in, the usage panel, the takeover of the static dataset page, the reindex rewriting every dataset page, and shipping the app and `/auth-config.json` with the stage's deploy. The submission, review and policy screens are PLAN2.

## The change

`packages/web` goes from a stub to the reader's app: React Router with four routes, a search page over `GET /api/search`, a dataset page laid out like the generated README, open downloads from `/data`, restricted downloads after Cognito managed login, and the optional usage panel. Its API and manifest types are generated from the committed OpenAPI spec and the contract's JSON Schema, under the drift check. The build emits a stable `/app.js` loader.

`packages/infra` gains one BucketDeployment in the `Web` construct that writes the build and `/auth-config.json` into the derived bucket's `site/`, with pruning off. `Auth` exposes its managed login domain for that file.

`packages/backend` changes in two places once Plan 7's PLAN1 has merged: the dataset page template gains `<div id="app">` and the `/app.js` script, and the reindex gains a step that renders and writes every dataset's page.

Risk is low (spec, Risk and cost): the app only reads, pruning is off and pinned by a synth test, and Plan 7's `test_pages` pins the template's escaping. Gates are unit tests with the API mocked, the synth test, the reindex test, `just check`, and one walk on a test stage.

## Left out

- Theme and species facets, the map view, the in-browser data preview, and branding from the config (PARK1 to PARK4).
- The contributor, curator and admin screens (PLAN2).
- Tokens that survive a reload.
- Any change to Plan 6's API or to Plan 7's ingest.

## Where

| Path | What changes |
| --- | --- |
| `packages/web/` | The app: `src/routes/`, `src/api.ts`, `src/auth.ts`, `src/generated/`, `src/styles.css`, `vite.config.ts` (the loader and the publisher), `package.json` |
| `justfile` | `check-schema` and a new `web-types` recipe regenerate and diff the web types; `check-ts` builds the web app before the tests |
| `packages/infra/src/web.ts`, `auth.ts`, `research-archive.ts`, `reindex.ts` | The site deployment, the managed login domain, the reindex's page permission and domain |
| `packages/infra/test/web.test.ts`, `reindex.test.ts` | Synth tests for the deployment and the reindex's new grant |
| `packages/backend/src/archive_backend/pages.py`, `reindex.py` and their tests | The template takeover and the reindex's page step |
| `docs/planning-handoff.md` | Already holds the three Decision log rows (research-in-a-box#31) |

### Task 1: The web app's groundwork

**Does:** Adds React Router, oidc-client-ts, and as dev dependencies openapi-typescript, json-schema-to-typescript and axe-core. Generates `src/generated/api.ts` from `src/schema/openapi.json` and `src/generated/manifest.ts` from `src/schema/archive-contract.schema.json`, through a `just web-types` recipe that `just check-schema` also runs and diffs. Adds `src/api.ts` (typed fetch helpers for the four routes the reader uses, and one error type for an unreachable API), the router with `/`, `/datasets/:id`, `/datasets/:id/v:version`, `/auth/callback` and a not-found page, a header showing the publisher, and `src/styles.css` with a few variables. The publisher is read at build time in `vite.config.ts` from the archive config (`ARCHIVE_CONFIG`, else the root `archive.yaml`) and injected with `define`. A small Vite plugin emits `dist/app.js`, a loader that imports the hashed entry chunk and adds the hashed stylesheet link, and `index.html` loads the app only through `/app.js`. The app mounts into `#app`.
**Files:** `packages/web/package.json`, `packages/web/vite.config.ts`, `packages/web/index.html`, `packages/web/src/main.tsx`, `packages/web/src/App.tsx`, `packages/web/src/api.ts`, `packages/web/src/generated/*`, `packages/web/src/styles.css`, `justfile`, `package-lock.json`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`, `npm run build -w packages/web` (and `test -f packages/web/dist/app.js`), `just check-schema`
**Serves:** none (rests on calls AGNT3, AGNT4, AGNT8)

- A test renders each route and finds its heading; the not-found page renders for an unknown path.
- `just check-schema` fails when `openapi.json` changes and `src/generated/api.ts` doesn't.
- The loader must work for both `index.html` and a dataset page: it resolves the hashed files from the build's manifest at build time, not at run time.

### Task 2: The search page

**Does:** Builds `/` over `GET /api/search`: the search box (`q`, debounced 300 ms), checkboxes for access, licence, format and project with the endpoint's counts, a from and to year, twenty results a page with Previous and Next, and result cards from the row's fields alone (title linking to `/datasets/<id>`, description cut to three lines, badges for access, licences, formats, the date range, project or creators). Every part of the search lives in the query string, so the back button and a shared link restore it. No results says so with a Clear filters button. An unreachable API shows one line and Try again.
**Files:** `packages/web/src/routes/Search.tsx`, `packages/web/src/routes/Search.test.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** none (rests on calls AGNT4, AGNT7)

- Tests with fetch mocked: typing sends one request after the debounce; checking a facet adds a repeated parameter and keeps the others; a search URL loaded fresh sends the same request; no results; unreachable API; an axe check of the page finds no violations.

### Task 3: The dataset page, open downloads and the usage panel

**Does:** Builds `/datasets/:id` (calls `GET /api/datasets/{id}`) and `/datasets/:id/v:version` (calls `GET /api/datasets/{id}/versions/{version}`, and `/versions` to show a note linking to the newer version when there is one). Lays the manifest out as one page: title and description with badges for access, licence or rights status and the published date; Cite this dataset, built as the generated README builds the citation and ending with the versioned URL, with a Copy button; About (creators, purpose, rights, project, keywords, temporal and spatial coverage); Files (title, kind, file and member count, size, Download, or Open link for a linked resource's own URL); a column dictionary for each table resource, saying when a column has no description. An open file's Download is a link to `/data/<id>/<version>/<path>`. When a download starts, the usage panel appears under the file list with the three optional answers from `UsageAnswers`, Send (posts to `POST /api/datasets/{id}/usage`) and No thanks; it never blocks the download, and once answered or dismissed it isn't shown again in the visit (sessionStorage). On a static dataset page, the app leaves the static content in `#app` until it has the dataset, then renders over it; if the API can't be reached, the static content stays.
**Files:** `packages/web/src/routes/Dataset.tsx`, `packages/web/src/routes/Dataset.test.tsx`, `packages/web/src/UsagePanel.tsx`, `packages/web/src/citation.ts` and its test, `packages/web/src/main.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN1 (rests on calls AGNT2, AGNT6, AGNT7)

- Tests use the sample package's `datapackage.json` (`examples/sample-package/`) as the mocked manifest: every resource kind shows; the citation matches the one in the sample package's README apart from the URL; Copy writes it; the versioned route shows the newer-version note; the usage panel appears after a download, sends the answers, and stays gone after No thanks; with the API failing, existing `#app` content is kept; an axe check finds no violations.

### Task 4: Sign-in and restricted downloads

**Does:** Adds `src/auth.ts` on oidc-client-ts: settings from `/auth-config.json` (`region`, `cognitoDomain`, `webClientId`), code with PKCE, redirect to `/auth/callback`, user store in memory (`InMemoryWebStorage`), the refresh token not requested or kept, and only the PKCE state and return path in sessionStorage. `/auth/callback` finishes sign-in and returns to the page the reader came from. A restricted dataset's Download reads Sign in to download until the reader is signed in; then it calls `GET /api/datasets/{id}/versions/{version}/download?path=` with the access token and follows the link. A 401 means sign in again; a 403 says the file isn't available to this account.
**Files:** `packages/web/src/auth.ts`, `packages/web/src/auth.test.ts`, `packages/web/src/routes/Callback.tsx`, `packages/web/src/routes/Dataset.tsx`, `packages/web/src/routes/Dataset.test.tsx`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** none (rests on call AGNT5)

- Tests: the sign-in redirect carries the client id, PKCE challenge and callback URL from a mocked `/auth-config.json`; after the callback, the download request carries the bearer token; nothing token-shaped is written to localStorage or sessionStorage.

### Task 5: Shipping the app and auth-config.json

**Does:** `Auth` exposes its managed login domain (`cognitoDomain`, the domain's base URL). `Web` gains one `s3deploy.BucketDeployment` into the derived bucket under `site/`, with `prune: false`: the web build's `dist/` (with `Cache-Control: no-cache` on `index.html` and `app.js`, and a year, immutable, on `assets/`) and `Source.jsonData('auth-config.json', { region, cognitoDomain, webClientId, cliClientId })` with no-cache. The deployment runs after the app clients exist and invalidates `/index.html`, `/app.js` and `/auth-config.json`. Synth fails with a plain message when `packages/web/dist` is missing. `check-ts` builds the web app before the workspace tests, so the infra tests synth against a real build.
**Files:** `packages/infra/src/web.ts`, `packages/infra/src/auth.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/web.test.ts`, `justfile`
**Checks:** `npm run build -w packages/web`, `npm test -w packages/infra`, `npm run typecheck -w packages/infra`
**Serves:** none (rests on call AGNT1)

- The synth test asserts the deployment's prune is false, its destination prefix is `site/`, and its sources include the JSON with exactly the four fields; and that no other deployment writes into `site/`.
- If two BucketDeployments are needed for the two cache settings, both keep `prune: false`; the test covers both.

### Task 6: The page takeover and the reindex's page step

**Does:** Once Plan 7's PLAN1 has merged (its `archive_backend.pages` with `render_page` and `write_page`), wraps the template's readable content in `<div id="app">` and adds `<script type="module" src="/app.js"></script>`, keeping every escape and the JSON-LD. Adds a checkpointed step to the reindex, after it writes `catalog.json`, that reads every dataset's current version from the newly active table and calls `render_page(manifest, dataset_id=, version=, domain=, files=)` then `write_page(...)`. The `Reindex` construct grants put on the derived bucket's `site/datasets/*` and passes the distribution's domain as `SITE_DOMAIN`.
**Files:** `packages/backend/src/archive_backend/pages.py`, `packages/backend/tests/test_pages.py`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_reindex.py`, `packages/infra/src/reindex.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/reindex.test.ts`
**Checks:** `uv run pytest packages/backend`, `uv run mypy packages`, `npm test -w packages/infra`, `just check`
**Serves:** none (rests on calls AGNT2, AGNT10)

- `test_pages` gains: the root element and the script are present; a title with `<script>` is still escaped inside `#app`.
- `test_reindex` gains: after a run over two datasets, two pages are written at `site/datasets/<id>/index.html`; a replay doesn't write them twice.
- The synth test shows the reindex's put grant on `site/datasets/*` and its `SITE_DOMAIN`.

### Task 7: The walk on a test stage

**Does:** Opens the PR with tasks 1 to 6 and enables auto-merge; after it merges and the user gives a Go, deploys `ResearchArchive-web-test` from main with `ARCHIVE_CONFIG` pointing at a test config, publishes the sample package through Plan 7's pipeline as an open dataset and again under another id as restricted, invites a test user, and walks with the user: a search for words in the title finds it and a facet narrows it with counts; `/datasets/<id>` shows the citation, files and columns, and Copy works; the versioned URL opens that version; `/auth-config.json` answers the four fields; an open file downloads and the usage panel sends; the restricted file asks for sign-in and downloads after it; with JavaScript off the page shows the title, citation and file links; after `just reindex`, `/datasets/<id>` still opens; a keyboard pass through search and the page. Then, on the user's second Go, destroys the stage and checks nothing is left.
**Files:** none changed; the walk's notes go in the task's result
**Checks:** `just check` on main, `cdk deploy` and `cdk destroy` of `ResearchArchive-web-test` exit 0
**Serves:** DCSN1 (rests on calls AGNT1, AGNT9, AGNT10)

- The walk is a step on this folder's page, with the user's actions and the agent's in order, starting with a Go before the deploy and with a Go before the teardown.
- The stage is named `web-test`, so it can't collide with another plan's test stage.
- On any AWS auth error, stop and report; never copy or export credentials.
