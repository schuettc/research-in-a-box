---
diazo: research-archive-in-a-box/web-app-catalog-and-curation
file: spec
status: approved
approved: 2026-11-14T00:47:32-06:00
hash: 1676bf49bfd833e1bfce8cfccc6b34065e79daa4a77d3c73000745d06ea12a70
rests_on: [AGNT9, AGNT4, AGNT7, AGNT3, AGNT6, AGNT5, DCSN1, AGNT2, AGNT10, AGNT1, AGNT8]
record: README.md
---

# Web app: the reader's flow first

## Goal

A reader can find a dataset by searching, open its page, and download its files, in the web app on a deployed stage. The app is the static React and Vite bundle in `packages/web`, today a stub that renders one heading. It is backed by Plan 6's read API, which is built and was walked on a test deploy. Findability is the problem the project set out to fix, so the reader's flow comes first. The contributor, curator and admin screens follow in a later plan, once Plan 7's submission endpoints exist.

## The plans

Two plans in this folder, built in turn.

- **PLAN1, the reader's flow.** Search, the dataset page, open and restricted downloads with sign-in, the optional usage form, the takeover of the static dataset page, the reindex rewriting every dataset page, and shipping the app with the stage's deploy. It is proven by a walk on a test stage.
- **PLAN2, the submission, review and policy screens.** Guided submission showing the same findings as the local tool, the curator's queue, a submission's findings and files, and approve, reject or request changes, and the admin's review policy. It is written once PLAN1 is built and Plan 7's `/api/submissions` endpoints are built, so it reads their real shapes. The curator's file list reads Plan 7's `GET /api/submissions/{id}/files`.

Rests on: AGNT9

## Routes

The app has four routes, handled by React Router.

| Route | What it shows |
| --- | --- |
| `/` | Search. The search's state is in the query string, so a search can be shared as a link. |
| `/datasets/<id>` | The dataset's current version. |
| `/datasets/<id>/v<n>` | That version, which is the URL the citation gives. A note links to the newer version when one exists. |
| `/auth/callback` | Finishes sign-in, then returns to the page the reader started from. |

Any other path shows a plain not-found page. CloudFront already sends `/datasets/<id>` to the dataset's static page and every other extensionless path to `index.html`, so no CloudFront change is needed.

Rests on: AGNT4

## Search

The search page calls `GET /api/search` and shows what it answers. It never downloads `catalog.json`.

- **The query.** A search box (`q`), with typing debounced by 300 ms. Facets for access, licence, format and project as checkboxes, each with the count the endpoint returns for the current filter. A from and to year for the date range. Twenty results a page, with Previous and Next.
- **A result card** shows the title (a link to `/datasets/<id>`), the description cut to three lines, and badges for access, licences, formats, the date range and the project or creators. It uses only the search row's own fields, so there is no request per result.
- **No results** says so and offers to clear the filters.
- **When the API can't be reached**, the page shows one line saying search is unavailable, with a Try again button.

Rests on: AGNT4, AGNT7

## The dataset page

The page calls `GET /api/datasets/{id}`, or `GET /api/datasets/{id}/versions/{version}` for a versioned URL, and lays the manifest out in the order of the generated `README.md`, as one page with no tabs.

1. **Title and description**, with badges for access, licence or rights status, and the published date.
2. **Cite this dataset**: the citation built the way the README builds it, ending with the versioned URL, and a Copy button.
3. **About**: creators, purpose, rights, project, keywords, temporal coverage and spatial coverage.
4. **Files**: each resource with its title, kind, file (and the count of its member files for a shapefile set or a raster), size, and a Download button. A linked resource shows Open link to its own URL.
5. **Columns**: for each table resource, its column dictionary (column, title, type, unit, description, codes). A column with no description says so.

The manifest's types come from the contract's JSON Schema, since the API returns the manifest as an untyped object.

Rests on: AGNT3, AGNT6

## Downloads and sign-in

- **An open file** downloads straight from `/data/<id>/<version>/<path>` on the CloudFront domain, with no request to the API.
- **A restricted file** shows Sign in to download to a reader who isn't signed in. Signing in goes through Cognito's managed login, with code and PKCE through the `web` app client and the callback `/auth/callback`. The region, sign-in domain and client id come from `/auth-config.json`, which this plan's site deployment writes (see Shipping the app). There is no sign-up screen, since accounts are by invitation. Once signed in, the button calls `GET /api/datasets/{id}/versions/{version}/download?path=` with the access token and follows the five-minute link it returns.
- **Tokens** are held in memory only, using oidc-client-ts, and the refresh token is discarded. Only the PKCE state and the page to return to sit in sessionStorage across the redirect. A reload means signing in again, which managed login's own session makes a single click.

Rests on: AGNT5

## The usage form

When a reader starts a download, a small panel appears under the file list: "Help this archive: how will you use this data?" It has the three optional answers from the contract's `UsageAnswers` (kind of organisation, purpose, and a note of up to 500 characters), with Send and No thanks buttons. Send posts them to `POST /api/datasets/{id}/usage`. The panel never blocks or delays the download, asks for no name or email, and isn't shown again in that visit once it has been answered or dismissed.

Rests on: DCSN1

## Taking over the static dataset page

Plan 7's publish writes a static page at `site/datasets/<id>/index.html` that reads on its own: the title, description, citation, version, file links, and schema.org JSON-LD in the head. Plan 8 owns that page's template from here, and Plan 7 still writes the pages.

- **The template** (`archive_backend.pages.render_page`) gains a root element around its readable content and one script tag for `/app.js`. It keeps escaping manifest text, which Plan 7's `test_pages` pins. The page stays readable with no JavaScript.
- **`/app.js`** is a small loader that the build emits and that is served with no-cache. It loads the current hashed bundle and stylesheet, so an app release never needs the dataset pages rewritten. `index.html` loads the app the same way.
- **On a dataset page**, the app leaves the static content in place until it has the dataset from the API, then renders over it. If the API can't be reached, the static content stays, so open data is still reachable.

This edit waits on Plan 7's PLAN1 merging. The root element and `/app.js` go in the handoff's Decision log.

Rests on: AGNT2, AGNT7

## The reindex rewrites dataset pages

After the reindex flips the active catalog table and writes `catalog.json`, it calls Plan 7's `render_page(manifest, dataset_id=, version=, domain=, files=)` and then `write_page(s3, bucket, html, dataset_id)` for every dataset, fed from the catalog items it has just loaded. This is its own checkpointed step, like the catalog file. Ingest is untouched. The reindex function gains permission to put under `site/datasets/*`, and an environment variable with the site's domain.

So a stage rebuilt by the reindex serves `/datasets/<id>`, and a template change reaches every published page with `just reindex`, which is Plan 10a's rebuild step after a deploy. This goes in the handoff's Decision log.

Rests on: AGNT10

## Shipping the app

The construct uploads the Vite build to the derived bucket's `site/` with a CDK BucketDeployment, so one `cdk deploy` ships the app with everything else.

- **Pruning is off.** The deployment never deletes what it didn't write: `catalog.json` and `datasets/` share the folder.
- **`/auth-config.json`** is written by the same deployment, with `Source.jsonData` from the construct's own values: `region`, `cognitoDomain`, `webClientId` and `cliClientId`, the fields Plan 9 agreed, sent with no-cache. The web app and Plan 9's clients only read it, so any client needs only the archive's URL. One deployment writes `site/`. This goes in the handoff's Decision log.
- **Caching:** `index.html` and `/app.js` are sent with no-cache. The hashed files under `assets/` cache for a year. Old hashed files stay, so a reader mid-session isn't broken by a release.
- **The build** runs before synth: `just check-ts` already builds the web app, and the default app's deploy builds it first. A synth fails if the build is missing.

Rests on: AGNT1

## How it is built

- **Dependencies added to `packages/web`:** React Router, oidc-client-ts, and as dev dependencies openapi-typescript, json-schema-to-typescript and axe-core for tests. No component library: plain CSS with a few variables.
- **Generated types:** the API's types from the committed `openapi.json` and the manifest's types from the contract's JSON Schema, both committed under `packages/web/src/generated` and checked for drift by `just check-schema`, like the other generated files.
- **The header** shows the archive's publisher. Themes and colours from the config are a follow-up.
- **Accessibility:** semantic HTML (one `h1` per page, labelled controls, real buttons and links), an axe check of each screen in the Vitest suite, and a keyboard pass in the walk.

Rests on: AGNT3, AGNT8

## Risk and cost

**Risk.** Low. The app only reads: it changes no data, and its one write is the anonymous usage form, which the contract already limits to three optional answers. What a mistake could do:

- **A deployment that prunes** would delete `catalog.json` and every dataset page. Pruning is off, and a synth test pins it. If it happened, `just reindex` rewrites both.
- **A template edit that stops escaping** manifest text would let a dataset's title inject script into its page. Plan 7's `test_pages` pins the escaping and runs in `just check`.
- **A token leak** would expose one reader's one-hour access to restricted data. Tokens stay in memory only.

The gates are sized to that: unit tests per screen with the API mocked, the synth test, the reindex step's test, and one walk on a test stage.

**Cost.** No new AWS service. The BucketDeployment adds one helper Lambda at deploy time. For you, there's one walk on a test stage at the end of PLAN1 (search, page, both downloads, a keyboard pass), and the test stage is destroyed after.

Rests on: AGNT1, AGNT5, DCSN1

## Left out

- **Theme and species facets** (PARK1): the contract has no such fields yet. They follow Plan 2's PARK5 and PARK6.
- **The map view** (PARK2), including drawing a box to filter by bbox, which also picks the map library.
- **The in-browser data preview** with DuckDB-Wasm (PARK3).
- **Branding and themes from the config** (PARK4).
- **The contributor, curator and admin screens:** PLAN2.
- **Tokens that survive a reload:** a reader signs in again after one.

Rests on: AGNT5, AGNT8, AGNT9

## How we'll know it works

- **`just check` passes:** the web app's tests (search, the dataset page, downloads, the usage panel, and an axe check of each screen), the synth test showing the BucketDeployment with pruning off, the cache headers and `auth-config.json`, the reindex test showing a page written per dataset, Plan 7's page tests, and the drift check on the generated types.
- **On a deployed test stage**, after the sample package is published as an open dataset and again as a restricted one through Plan 7's pipeline, and a user is invited:
  - a search for words in its title finds it, and checking a facet narrows the results with the counts shown;
  - its page at `/datasets/<id>` shows the citation, files and columns, and Copy puts the citation on the clipboard;
  - the citation's versioned URL opens that version;
  - `/auth-config.json` answers the four fields;
  - an open file downloads, and the usage panel appears and sends;
  - the restricted dataset's file asks for sign-in, and after the invited user signs in it downloads;
  - with JavaScript off, `/datasets/<id>` still shows the title, citation and file links;
  - after `just reindex`, `/datasets/<id>` still opens.

Rests on: DCSN1, AGNT1, AGNT2, AGNT9, AGNT10
