<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Web app (Plan 8)

`research-archive-in-a-box/web-app-catalog-and-curation` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans · 1 to write** → Build → Sign off

PLAN1 can be written now · PLAN2 waits on PLAN1 being built

## Pick up next

- **PARK1 Theme and species facets:** Add theme and species facets to search once the contract holds them (Plan 2's PARK5 and PARK6) and the search endpoint returns them.
- **PARK2 Map view:** A map of results from each row's bounding box, and drawing a box to filter search by bbox. Picks the map library then.
- **PARK3 In-browser data preview:** Preview a table's first rows on the dataset page with DuckDB-Wasm, reading the open file by range from /data, loaded on the dataset page only. Plan 7's PARK4 (previews derived at publish) is the other route.
- **PARK4 Branding from the config:** Themes, logo and colours from the archive config, once an adopter asks for them.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 6, the API and search, and Plan 7, the ingest pipeline, for the submission screens.)
> 
> Brief: Plan 8 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the web app (Plan 8): a static React with Vite app on S3 and CloudFront, backed by the API. Start with the reader's flow from search to dataset page to download, since findability is the main problem we set out to fix. The generated `README.md` in `practice-data/packages/ozone-bioindicators/` shows what a dataset page has to present.

## Decisions

- **DCSN1 Usage form on the page.** Should the dataset page ask readers, optionally, how they will use the data? The user chose A: After a download, a small optional panel.
- **AGNT1 Shipped by the stage's deploy.** The construct uploads the Vite build to the derived bucket's site/ with one CDK BucketDeployment, with pruning off, so files other plans write there (catalog.json, datasets/) are never deleted. The same deployment writes /auth-config.json with Source.jsonData from the construct's own values: region, cognitoDomain, webClientId, cliClientId (the fields Plan 9 agreed), sent no-cache. Plan 9 only reads it. index.html and the loader are no-cache; hashed assets cache for a year. One cdk deploy ships the app and its settings. The user kept it.
- **AGNT2 Takeover by a stable loader.** Plan 8 owns the dataset page template from here (the coordinating session settled it with Plans 7 and 10a); Plan 7's publish writes the pages. The build emits a small loader at /app.js, served no-cache, that loads the current hashed bundle. The template gains a root element around its readable content and one script tag for /app.js. When the app has the dataset from the API it renders over that content; with no JavaScript or no API, the static page stays readable (title, citation, file links and schema.org stay in the HTML). A new app release never needs the dataset pages rewritten. Plan 8 edits archive_backend.pages after Plan 7's PLAN1 merges, and records the root element and /app.js in the Decision log. The user kept it.
- **AGNT3 Types generated, drift-checked.** openapi-typescript generates the API's types from the committed openapi.json, and json-schema-to-typescript the manifest's types from the contract's JSON Schema (the dataset answer's manifest is an untyped object in the API). Both are committed under packages/web/src/generated and checked by just check-schema like the others. The user kept it.
- **AGNT4 React Router, four routes.** React Router with four routes: / (search, its state in the query string), /datasets/&lt;id> (the current version), /datasets/&lt;id>/v&lt;n> (that version, which is the dataset's cited identifier, with a note when a newer one exists) and /auth/callback. Anything else shows a plain not-found page. The user kept it.
- **AGNT5 Sign-in tokens in memory.** oidc-client-ts with code and PKCE against the web app client, settings from /auth-config.json. Tokens are kept in memory only and the refresh token is discarded, as the CLI does; only the PKCE state and the page to return to sit in sessionStorage across the redirect. A reload means signing in again, which managed login's own session makes a click. The user kept it.
- **AGNT6 One page, no tabs.** One page in the README's order: title, description, badges, citation, about, files, then a column dictionary per table. A reader's browser search finds any column. The user kept it.
- **AGNT7 When the API is down.** Search shows one line saying search is unavailable, with a Try again button. A dataset page keeps Plan 7's static content (title, description, citation, file links), so open data stays reachable. The user kept it.
- **AGNT8 Plain CSS, checked by keyboard.** Plain CSS with a few variables, no component library. Semantic HTML (one h1, labelled controls, real buttons and links), with an axe check of each screen in the Vitest suite and a keyboard pass in the walk. The header says the archive's publisher from the config; theming from the config is a follow-up. The user kept it.
- **AGNT9 Walk waits on Plan 7's publish.** Screens are built and tested against the generated types right away. The takeover task and the walk wait on Plan 7's TASK5 (publish and the dataset page): the walk publishes the sample package through Plan 7's pipeline on a test stage, invites a user, and walks search, page and both downloads. The user kept it.
- **AGNT10 Reindex rewrites dataset pages.** In PLAN1: after the reindex flips the active table and writes catalog.json, it calls Plan 7's archive_backend.pages.render_page(manifest, dataset_id=, version=, domain=, files=) and then write_page(s3, bucket, html, dataset_id) for every dataset, fed from the catalog items, the same way it calls Plan 6's catalog-file writer. Ingest is untouched. One path, no second command: a stage rebuilt by reindex serves /datasets/&lt;id>, and a template change rolls out with just reindex (Plan 10a's rebuild step after a deploy). The reindex Lambda gains put on site/datasets/* and the site's domain. Template edits keep escaping manifest text, which Plan 7's test_pages pins. Recorded in the Decision log. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The plans](spec.md#the-plans): rests on AGNT9
- [Routes](spec.md#routes): rests on AGNT4
- [Search](spec.md#search): rests on AGNT4, AGNT7
- [The dataset page](spec.md#the-dataset-page): rests on AGNT3, AGNT6
- [Downloads and sign-in](spec.md#downloads-and-sign-in): rests on AGNT5
- [The usage form](spec.md#the-usage-form): rests on DCSN1
- [Taking over the static dataset page](spec.md#taking-over-the-static-dataset-page): rests on AGNT2, AGNT7
- [The reindex rewrites dataset pages](spec.md#the-reindex-rewrites-dataset-pages): rests on AGNT10
- [Shipping the app](spec.md#shipping-the-app): rests on AGNT1
- [How it is built](spec.md#how-it-is-built): rests on AGNT3, AGNT8
- [Risk and cost](spec.md#risk-and-cost): rests on AGNT1, AGNT5, DCSN1
- [Left out](spec.md#left-out): rests on AGNT5, AGNT8, AGNT9
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, AGNT1, AGNT2, AGNT9, AGNT10

## Plans

- PLAN1 Reader search page download: can be written now
- PLAN2 Submission review and policy screens: waits on PLAN1 being built

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |

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
