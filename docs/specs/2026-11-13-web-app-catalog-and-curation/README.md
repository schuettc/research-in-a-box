<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Web app (Plan 8)

`research-archive-in-a-box/web-app-catalog-and-curation` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 15 of 22** → Sign off

PLAN1 built · PLAN2 building · 0 of 7 done · PLAN3 built

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
- **PARK12 Integrity check covers the zips:** The weekly integrity check verifies only the files in checksums.sha256, so a zip under _zips/ damaged in S3 goes unnoticed. Add _zips/ to the check against each zip's full-object SHA-256.
- **PARK13 Site address in the invitation email:** The invitation email names the archive but not its address: putting the CloudFront domain on the user pool makes a CloudFormation dependency loop. A custom-message trigger, or the custom domain, would add it.
- **PARK14 Large zips and the reindex checkpoint:** From PLAN3's review: a zip over 5 GB can't be one PUT and a version near 10 GiB overflows the reindex's /tmp, failing publish or the reindex with no alert (M2); the reindex's versions step checkpoints every manifest's text, which may exceed the durable checkpoint size on a big archive (M3). Add a size guard with a note and an alert, and checkpoint ids only.
- **PARK15 Zip sizes and brand file checks:** From PLAN3's review: zip file items carry no size or hash and Download all shows no size (M4, M9); the font pattern differs between Python and Vite (M5); brand SVGs aren't checked for script or Cognito's allow-list, and Vite doesn't re-check the logo extension (M6, M8).
- **PARK16 Cognito's SVG allow-list:** Cognito's managed login refused the example logo's role and aria-label attributes (Plan 9's deploy, research-in-a-box#54 fixes it and refuses role, aria-*, script, handlers and foreignObject at config load). Cognito's full SVG allow-list isn't documented where we looked; if a deploy refuses another element or attribute (text is a suspect), add it to the Brand check.
- **PARK17 Facet counts read twice:** A facet label reads "Open access 1 (1)" to a screen reader: the visible count plus a visually hidden copy. Keep one.
- **PARK18 Reindex result counts zips:** The reindex result reports pages but not zips written; add a zips count so a run shows what it rewrote.
- **PARK19 Build packages in the browser:** DCSN5 chose C: an in-browser package builder (a step-by-step form that writes datapackage.json and checksums.sha256 from raw files, inferring column types) is planned once contributors have used the cruise-package upload. Mockup: mockups/submit-options.html tab B.

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
- **DCSN5 How contributors submit.** How should a contributor submit a dataset in the web app? The user chose C: A first, B later as its own plan.
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
- **AGNT13 PLAN2 screens and their gaps.** Three areas in the Reading room look, one frame on every view (PRIN1): contributor (Submit, My submissions, a submission's status, findings and history, resubmit on needs-changes), curator (the review queue by status with stale and new-version marked, a submission's findings, held files with links and the in-browser table preview of a CSV's first rows read through its short-lived link, its history, and Approve, Reject or Request changes with a note, waiting correctly for a second curator), and admin (the review policy form generated from the ReviewPolicy JSON Schema). Nav entries appear only for the groups a reader is in. The gaps: a CORS rule on the staging bucket for the site's origin (PUT and GET), typed submission routes in the committed OpenAPI spec so the screens use generated types, a way to show people as emails rather than Cognito ids and to pick curators for named reviewers, and new upload links for an expired round-1 draft. I'm asking the coordinating session who builds the backend parts (Plan 7's code); PLAN2 is written once that's settled. The user kept it.
- **PRIN1** Nothing moves when changing views: the header, navigation, page heading and content column sit in the same place on every page and in every state (loading, loaded, error), so switching tabs or pages never shifts text.

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
- [PLAN2](plans/2-submission-review-and-policy-screens.md) The contributor, curator and admin screens: building · 0 of 7 done
  - TASK16 Task 16: Close Plan 7's API gaps: not started
  - TASK17 Task 17: The submissions API in the OpenAPI spec: not started
  - TASK18 Task 18: Signed-in areas in the frame: not started
  - TASK19 Task 19: The contributor's screens: not started
  - TASK20 Task 20: The curator's screens: not started
  - TASK21 Task 21: The admin's review policy: not started
  - TASK22 Task 22: The walk on web-test: not started
- [PLAN3](plans/3-ux-review-and-branding.md) A look of our own, the UX review's changes, and themed sign-in with passkeys: built
  - TASK8 Task 8: The brand block: done. c4990d5: Brand model and ArchiveConfig.brand, schema and config type regenerated, brand block in archive.yaml; contract 317 passed, mypy 0, check-schema 0
  - TASK9 Task 9: The Reading room look and the brand at build time: done. e2fb9bc: Reading room CSS on brand properties, build-time brand plugin, masthead, About, footer, page titles, focus, skip link; web 62 passed, build 0
  - TASK10 Task 10: Search: done. 18d0592: decision-ready entries, word labels, phone filters, facets on no results, submit, year range, pager; web 75 passed
  - TASK11 Task 11: The dataset page: done. ee07faf: reordered page fitting 390, restricted banner with one Sign in, signed-in header with Sign out and Add a passkey, coverage box, Methods, versions, usage beside Download, dictionary fixes, error states; web 88 passed; just check exit 0; headless screenshots at 1280 and 390, no sideways scroll, axe clean
  - TASK12 Task 12: Download a resource whole, and Download all: done. eb1ea40: package.zip and per-resource zips under _zips/ from checksums.sha256, written by publish and reindex, listed as file items; Download all and set downloads on the page; backend 186 passed
  - TASK13 Task 13: A static page for every version: done. c5f21f3: site/datasets/&lt;id>/v&lt;n>/index.html per version at publish and reindex, branded rule and logo, site function rewrite; backend 191 passed, just check 0
  - TASK14 Task 14: Themed sign-in, passkeys and the invitation email: done. d63c515: managed login branding from the brand block on both clients via the shared shade function, choice-based sign-in with password and passkey, ALLOW_USER_AUTH, branded invitation email (name only); infra 101 passed; just check 0 (692 Python, 101 infra, 90 web)
  - TASK15 Task 15: The walk on web-test: done. #51, #54 (Cognito-safe logo), #55 (steady layout) and #56 (Account menu, usage modal, plain sign-in background) merged; web-test deployed from main, walked headless (every app check passing at 1280 and 390, passkey added and used, zips match checksums), two looks by Court approved; destroyed, nothing left

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
- STEP2 Walk the new look and sign-in on a web-test stage with me: done
  1. agent · Merge research-in-a-box#51 once its checks pass · done. research-in-a-box#51 merged as 6e111a2 after CI passed on eab1b96
  2. agent · Keep one frame on every view (PRIN1): measure the header, nav, heading, content and footer on every view, fix what moves · done. 8 views at 1280 and 390: the scrollbar gutter is always reserved, the dataset page's eyebrow line is gone so every h1 starts at y=130 (154 on a phone), and the footer stays at the window's bottom on short pages; header, nav, h1 and content identical on every view; web 95/95, tsc 0; 454e6ac on plan8/steady-layout
  3. The user · Look locally: change views and check nothing moves · done: Looks good: deploy it (2026-11-14 14:16, on the page)
  4. The user · Go for deploying ResearchArchive-web-test · done: Go (2026-11-14 14:16, on the page)
  5. agent · Deploy, publish the sample package open and restricted, run just reindex, and walk it headless at 1280 and 390: the look and a second brand, search, the dataset page, the restricted banner, themed sign-in, a passkey with a virtual authenticator, Download all and a shapefile zip against their checksums, a cited /v1 page with the API cut off, no movement between views, and axe · done. deployed from 4bbba59 in 326 s, Cognito accepted the branding and passkeys; reindex SUCCEEDED (pages 4); every app check passes at 1280 and 390: search and facets, no movement between views, no sideways scroll, Download all and the shapefile zip match checksums.sha256, themed sign-in, Signed in as, restricted file and Download all, passkey added and signed in with, /v1 readable with the API blocked, axe clean on every app screen, second brand rebuilt; axe flags Cognito's own page (no h1); throwaway user deleted; court@subaud.io invited
  6. The user · Look at it, and sign in with a passkey on your own device · done: Looks good (2026-11-14 15:11, on the page)
  7. agent · An Account dropdown in the header, the usage question as a modal, and Cognito's page on the archive's paper (your note) · done. 0eef1af on plan8/menu-and-modal, web 96/96, just check 0; redeployed web-test; headless: sign-in page plain paper background (rgb 251,249,245, no image) with Back in the brand colour, Account menu names the reader with Add a passkey and Sign out, nav didn't move signing in, download opens a modal and the Files heading moved 0 px, no page errors; throwaway user deleted
  8. The user · Look again: the Account menu, the usage modal and the plain sign-in page · done: Looks good (2026-11-14 15:12, on the page)
  9. The user · Go for the teardown · done: Go (2026-11-14 15:21, on the page)
  10. agent · Destroy ResearchArchive-web-test and confirm nothing is left · done. just destroy web-test exit 0; no web-test buckets, tables, functions, user pool or /research-archive/web-test parameters left; the BucketDeployment helper's log group deleted by hand (PARK9)

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
