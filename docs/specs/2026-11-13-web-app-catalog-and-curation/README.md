<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Web app (Plan 8)

`research-archive-in-a-box/web-app-catalog-and-curation` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans · 1 to write** → **Build · 7 of 15** → Sign off

PLAN1 built · PLAN2 can be written now · PLAN3 building · 0 of 8 done

## Pick up next

- **PARK1 Theme and species facets:** Add theme and species facets to search once the contract holds them (Plan 2's PARK5 and PARK6) and the search endpoint returns them.
- **PARK2 Map view:** A map of results from each row's bounding box, and drawing a box to filter search by bbox. Picks the map library then.
- **PARK3 In-browser data preview:** Preview a table's first rows on the dataset page with DuckDB-Wasm, reading the open file by range from /data, loaded on the dataset page only. Plan 7's PARK4 (previews derived at publish) is the other route.
- **PARK4 Branding from the config:** Folded into PLAN3 (visual design): themes, logo and colours from the archive config come with the designed look.
- **PARK5 Content-Disposition on restricted links:** Plan 6's presigned link for a restricted file sets no Content-Disposition, so a CSV or Markdown file may open in the tab and drop the in-memory sign-in. Add ResponseContentDisposition attachment in Plan 6's download route.
- **PARK6 Reindex pages match ingest pages:** Pages the reindex writes link only the version's data files (from the catalog items); ingest's pages also link datapackage.json, README.md and checksums.sha256. Feed both from the same file list so the two paths write the same page.
- **PARK7 Alert when the page step fails:** The reindex's catalog step alerts on failure; its page step doesn't. Add the same alert.
- **PARK8 Small dataset page fixes:** From the final review: a description-only dataset's 404 should say there is no file; limit manifest URLs in href to http(s); don't fail the versioned page when only the versions call fails; tighten the synth test's site/ filter.
- **PARK9 Destroy cleans the upload helper's logs:** just destroy deletes the S3 auto-delete helper's log group but not the one CDK's BucketDeployment helper leaves (/aws/lambda/ResearchArchive-&lt;stage>-CustomCDKBucketDeployment-*), which Plan 8 added. Delete both prefixes in the recipe.
- **PARK10 A signed-in mark in the header:** Nothing on the page says the reader is signed in; only the restricted buttons change from Sign in to download to Download. Show who is signed in, with Sign out, in the header.
- **PARK11 Custom domain moves passkeys:** When the custom-domain follow-up gives sign-in its own domain, the passkey relying party moves from the prefix domain to it, and readers must register their passkeys again. Say so in that change and in the deploy notes.

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
- **DCSN2 Our own look.** Which look should the archive have? The user chose A: Reading room: calm and scholarly.
- **DCSN3 Sign-in page.** Should readers sign in on Cognito's page themed to match the archive, or on a page of our own? The user chose A: Cognito's page, themed from the archive config.
- **DCSN4 UX review changes.** Which of the UX review's changes go into the reader's screens now? The user chose A: All ten, with the map as a drawn box.
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
- **AGNT11 Rebranding from one brand block.** One small brand section in archive.yaml: name (default the publisher), a one-paragraph intro for the home page, a contact email (shown on restricted pages and errors), logo and favicon files, a primary colour, and an optional font stack. A strict Brand model in the contract validates it (hex colour, file types, logo at most 200 KB, email shape). The app reads it at build time: CSS custom properties, the page title, the favicon, the header logo, the intro and the contact, so nothing flashes unthemed and the static dataset pages get it too. The same block generates Cognito's sign-in branding and the invitation email's subject and text at deploy. One shared function derives hover, active and text-on-colour shades so both surfaces match. The user kept it.
- **AGNT12 Passkeys through managed login.** Turn on choice-based sign-in with password and passkey as first factors (Essentials plan, which the pool already has). Managed login then offers a passkey to anyone who has one, and prompts a reader to add one after they sign in with a password; an invited user signs in with the temporary password first, then can add a passkey. The header's signed-in menu gets Add a passkey, which opens managed login's passkey registration page. The relying party is the sign-in domain: today the prefix domain (archive-&lt;stage>-&lt;account>.auth.&lt;region>.amazoncognito.com). User verification stays at Cognito's default, preferred. The web and CLI clients both allow it, so the CLI's sign-in takes a passkey too. The user kept it.

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

- [PLAN1](plans/1-reader-search-page-download.md) The reader's flow: built
  - TASK1 Task 1: The web app's groundwork: done. 29c0954: router, generated types under check-schema, api helpers, /app.js loader; web typecheck, test, build, check-schema exit 0
  - TASK2 Task 2: The search page: done. 3f8d9d9: search page with facets, date range, paging, URL state; web typecheck and test exit 0
  - TASK3 Task 3: The dataset page, open downloads and the usage panel: done. e1dabbd: dataset page, citation, open downloads, usage panel, static takeover; web typecheck and test exit 0
  - TASK4 Task 4: Sign-in and restricted downloads: done. d8f2d46: oidc-client-ts sign-in, tokens in memory, restricted downloads; web tests 34/34 exit 0
  - TASK5 Task 5: Shipping the app and auth-config.json: done. e917c7a: two site BucketDeployments, prune false, auth-config.json with four fields; infra tests 55/55 exit 0; just check exit 0 (457 Python, 55 infra, 34 web)
  - TASK6 Task 6: The page takeover and the reindex's page step: done. 6ee8f5e (rebased on Plan 7 PLAN1 and Plan 6 PLAN3): template gains div id app and /app.js, write_page added, reindex page step with put grant and SITE_DOMAIN; pytest backend 173, infra 81, just check exit 0
  - TASK7 Task 7: The walk on a test stage: done. #41 and #49 merged; ResearchArchive-web-test deployed, both samples published through Plan 7, headless walk 13/13 after three fixes (blank page, static CSS, ID token), Court's look: works, not attractive yet (PLAN3); destroyed, nothing left
- PLAN2 Submission review and policy screens: can be written now
- [PLAN3](plans/3-ux-review-and-branding.md) A look of our own, the UX review's changes, and themed sign-in with passkeys: building · 0 of 8 done
  - TASK8 Task 8: The brand block: not started
  - TASK9 Task 9: The Reading room look and the brand at build time: not started
  - TASK10 Task 10: Search: not started
  - TASK11 Task 11: The dataset page: not started
  - TASK12 Task 12: Download a resource whole, and Download all: not started
  - TASK13 Task 13: A static page for every version: not started
  - TASK14 Task 14: Themed sign-in, passkeys and the invitation email: not started
  - TASK15 Task 15: The walk on web-test: not started

## Steps

- STEP1 Walk the web app on a web-test stage with me: done
  1. The user · Go for deploying ResearchArchive-web-test · done: Go (2026-11-14 10:04, on the page)
  2. agent · Deploy web-test from main, publish the sample package open and again as restricted through Plan 7's pipeline, and invite you · done. deployed in 316 s at https://dckg0gpr35vyc.cloudfront.net; both published through submit, scan, checks, approve; /app.js no-cache, /auth-config.json four fields, dataset pages carry div id app; search empty until just reindex web-test (Plan 7's publish doesn't rewrite catalog.json, raised with the coordinator); invitation sent
  3. The user · Sign in for the first time and set your password · done: Didn't land back on the page (2026-11-14 10:29, on the page)
  4. agent · Fix the blank page after sign-in and the layout the static page's CSS broke, redeploy web-test, rewrite the dataset pages, and walk it in a headless browser · done. three bugs fixed test-first on plan8/walk-fixes (blank page on mount, static CSS leaking into the app, restricted downloads sent the access token instead of the ID token: 401); redeployed, just reindex web-test SUCCEEDED (pages 2); headless walk 13 of 13 checks pass, including sign-in through managed login back to the page and the restricted logger.csv download; throwaway user deleted
  5. The user · Look at it in your browser · done: Looks good. “it works but is not very attractive. if we're doing that later, that's ok. we should have a plan for that though.” (2026-11-14 11:10, on the page)
  6. agent · Open the PR with the walk fixes, merge it, and confirm /auth-config.json and /datasets/&lt;id> after just reindex · done. research-in-a-box#49 merged (54d96c0); /auth-config.json answers exactly cliClientId, cognitoDomain, region, webClientId; /datasets/&lt;open id> 200 after the reindex that wrote 2 pages
  7. The user · Go for the teardown · done: Go (2026-11-14 11:29, on the page)
  8. agent · Destroy ResearchArchive-web-test and confirm nothing is left · done. just destroy web-test exit 0; no web-test buckets, tables, functions, user pool or /research-archive/web-test parameters left; the site upload helper's log group was left behind and deleted by hand (PARK9)

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
| `documents/` | the agent and the user | Every other file the plan holds, of any type: CSV, PDF, Markdown, transcripts. |

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
