---
diazo: research-archive-in-a-box/web-app-catalog-and-curation
file: PLAN3
status: done
approved: 2026-11-14T12:38:40-06:00
hash: 63bf3048346f1cd5d4045a4196ffff2c8ef46dd10952d91579db83547db86ecc
rests_on: [AGNT11, AGNT12, DCSN2, DCSN3, DCSN4]
record: README.md
---

# PLAN3: A look of our own, the UX review's changes, and themed sign-in with passkeys

## Spec

`spec.md` in this folder, approved for PLAN1's reader's flow, plus the decisions made since PLAN1 was built: DCSN2 (the Reading room look, `mockups/look-a-reading-room.html`), DCSN3 (Cognito's managed login themed from the archive config, with passkeys, call AGNT12), DCSN4 (all ten of the UX review's top changes, `documents/ux-review.md`) and call AGNT11 (one `brand:` block rebrands the app, the sign-in page and the invitation email). This plan changes the screens PLAN1 built; it doesn't add screens. PLAN2's submission, review and policy screens are written after this, in the new look.

## The change

**Brand.** `archive.yaml` gains an optional `brand:` block (name, intro, contact, logo, favicon, primary colour, font stack), validated by a `Brand` model in the contract. Today's look is the default when it's absent.

**The look.** `packages/web` takes the Reading room look: serif headings, a masthead with the logo and name, Browse and About the archive links, a footer, one primary button style, coloured access labels. Everything rests on CSS custom properties set from the brand at build time, so changing the block rebrands it. Every page gets its own title, focus moves to the h1 on navigation, and a skip link leads each page.

**Search** gets decision-ready result entries (an Open or Restricted label first, creators on their own line, a meta line with licence, kinds of file, files, size and updated date), plain-word facet labels, filters that collapse on a phone, facets kept on No results, a submit button, a year range that says when it's incomplete, a pager only when there's more than one page, and an intro and count from the brand.

**The dataset page** is reordered (title and meta line, access banner, description, a summary strip with Download all, files, columns, about; the citation beside on desktop), fits a phone, explains restricted access with one Sign in and the contact, shows who is signed in with Sign out and Add a passkey, draws the spatial coverage as a box on a plain outline, adds Methods, Funding and Related works to About, lists the versions, shows the usage panel beside the Download that was pressed, tidies the column dictionary, and gives error pages a way forward.

**Downloads.** A multi-file resource downloads whole, and a version downloads all at once, as zips the page-writing step writes beside each version. **Every version gets a static page**, so a cited `/datasets/<id>/v<n>` link reads with no API.

**Sign-in.** Cognito's managed login is branded from the same block on the web and CLI clients, choice-based sign-in offers password and passkey, and the invitation email speaks in the archive's name.

**Risk.** Low to moderate. The app still only reads. What a mistake could do: break sign-in for everyone (an auth change in Plan 4's construct), which the walk catches and a revert undoes; or leave a zip that doesn't match its version's files, which the zip step's test and the walk's checksum compare catch, and the reindex rewrites. Checks are unit tests with the API mocked, synth tests for the auth and site changes, backend tests for the zip and page steps, `just check`, and one walk on a test stage with your look at the end.

**Cost.** No new AWS service. Passkeys need Cognito's Essentials plan, which the pool already has (CDK's default for a new pool), so no new charge. Zips add one copy of each version's files in the archive bucket. For you: two Go presses (deploy and teardown) and one look.

## Left out

- Sort by newest, title or relevance on search (S7's sort): `GET /api/search` takes no sort today; a Plan 6 change, as a follow-up.
- BibTeX and RIS citation downloads, and a check that a stored citation's version matches (D11), beyond styling Copied.
- `publishedAt` on the dataset answer (D12): the page takes it from the versions list instead.
- A real map: the spatial box is drawn on a plain outline, no tiles or map library.
- A custom domain for the site or sign-in (an existing follow-up; PARK11 notes passkeys re-register then).
- Fonts on the sign-in page: Cognito can't take one.
- The contributor, curator and admin screens (PLAN2).

## Where

| Path | What changes |
| --- | --- |
| `packages/contract/src/archive_contract/config.py`, its tests, the JSON Schema | The `Brand` model and `ArchiveConfig.brand` |
| `archive.yaml`, `examples/brand/` | A worked brand block for the default archive, with its logo |
| `packages/web/vite.config.ts`, `index.html`, `src/styles.css`, `src/App.tsx`, `src/routes/*`, `src/*.tsx` | The look, the brand at build time, every screen change |
| `packages/infra/src/auth.ts`, `brand.ts` (new), `web.ts`, `research-archive.ts`, their tests | Managed login branding, passkeys, invitation email, the per-version page rewrite |
| `packages/backend/src/archive_backend/pages.py`, `reindex.py`, `ingest.py` (the one call into the page step), their tests | Per-version pages and the zips |
| `docs/planning-handoff.md` | Decision log rows for the brand block, passkeys and the zips |

### Task 8: The brand block

**Does:** Adds a strict `Brand` model to `archive_contract.config` and an optional `brand` field on `ArchiveConfig`: `name` (default the publisher), `intro` (one paragraph, at most 600 characters), `contact` (an email address), `logo` and `favicon` (paths relative to the config file; svg or png for the logo, svg or ico for the favicon; at most 200 KB each; the files must exist), `primaryColor` (`#rrggbb`) and `font` (a CSS font-family stack, optional). Regenerates the JSON Schema and the construct's config type. Adds a brand block to `archive.yaml` for the Invented Research Cooperative, with a small SVG logo under `examples/brand/`, and checks the config still writes under the 4 KB SSM limit.
**Files:** `packages/contract/src/archive_contract/config.py`, `packages/contract/tests/test_config.py`, `packages/web/src/schema/archive-contract.schema.json`, `packages/infra/src/generated/archive-config.ts`, `archive.yaml`, `examples/brand/logo.svg`, `examples/brand/favicon.svg`
**Checks:** `uv run pytest packages/contract`, `uv run mypy packages`, `just check-schema`
**Serves:** DCSN2 (rests on call AGNT11)

- Tests: a valid block loads; a bad colour, a missing logo file, a 300 KB logo, an unknown key and a bad email are each refused with a message naming the field; no brand block gives the defaults.

### Task 9: The Reading room look and the brand at build time

**Does:** Rebuilds `styles.css` on the Reading room mockup (`mockups/look-a-reading-room.html`): custom properties for the brand colour and its derived shades, ink, paper, rules, the heading and body fonts and the radius; serif headings; one primary button style; coloured access labels (green open, amber restricted, grey other levels); section spacing and a ~70ch measure. A Vite plugin reads the brand at build time: writes the `:root` properties after `styles.css`, copies the logo and favicon into `dist/brand/`, sets `<title>` and the favicon link in `index.html`, and defines `__BRAND__` (name, intro, contact, logo URL). One small module derives the hover, active and text-on-colour shades, shared with Task 14. The masthead shows the logo and name with Browse and About the archive; an About page renders the intro and contact; a footer names the publisher. Every route sets `document.title` ("Search · {name}", "{dataset} · {name}", "Not found · {name}") and moves focus to its h1; Clear filters returns focus to the search box. A skip link leads each page.
**Files:** `packages/web/vite.config.ts`, `packages/web/src/brand.ts` (the shade function), `packages/web/index.html`, `packages/web/src/styles.css`, `packages/web/src/App.tsx`, `packages/web/src/routes/About.tsx`, their tests
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`, `npm run build -w packages/web`
**Serves:** DCSN2, DCSN4 (rests on call AGNT11)

- Tests: the build with a second brand (a test config) puts its colour in the CSS and its name in the title; the shade function gives AA contrast for text on the primary colour across a set of colours; each route's title; focus on the h1 after navigation; the skip link reaches main; axe finds nothing on each screen.

### Task 10: Search

**Does:** Result entries take the mockup's form: the access label first ("Open", "Restricted"), the title, creators and coverage years on a muted line, the description cut to three lines, and a meta line with the licence in words, the kinds of file (tables, GIS, documents, images, from the formats), the file count where known, the size and the published date. Facet labels map tokens to words (access levels, licence ids, formats as "Shapefile (.shp)"), keeping the token in the URL. Below 40rem the filters collapse behind "Filters (n active)". On No results the facet groups stay with their values from the archive at 0, the query is echoed, and Clear filters (keeping the query) sits beside Search everything. A submit button searches at once on Enter. The year boxes are text with a numeric keyboard, "From [ ] to [ ]" on one line, and say when a year is incomplete or the range is reversed. The pager shows only past one page, as "Page 1 of n". The home page opens with the brand's intro and "N datasets in the archive". The error line names the contact.
**Files:** `packages/web/src/routes/Search.tsx`, `packages/web/src/routes/Search.test.tsx`, `packages/web/src/labels.ts` and its test, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN4

- Tests: an entry shows the access label before the title and no raw extension; filters collapse at phone width and open with the count; No results keeps the facets; Enter searches at once; a three-digit year shows the hint and sends no filter; one page shows no pager; axe at 1280 and 390.

### Task 11: The dataset page

**Does:** Reorders the page: title, a meta line (creators · published · version · licence), the access banner, the description, a summary strip (files, size, kinds, coverage, with Download all from Task 12), Files, Columns, About; on desktop the citation sits in a right column near the top with Copy inside its box, and Copied shows beside it. Below 40rem: files become cards with a full-width Download, the columns tables scroll sideways inside a framed box, About stacks label over value, long URLs wrap. Restricted and other non-open datasets show a banner saying what the level means, who can sign in (invited accounts), and how to ask for access (the brand's contact), with one Sign in; file rows show a lock and "Sign in above". The header shows "Signed in as {email}" with Sign out and Add a passkey (managed login's passkey registration page) once signed in. Spatial coverage shows its description first, then the bounding box drawn on a plain outline in SVG, with the numbers in small type. About adds Methods, Funding and Related works when the manifest has them. A Versions list (number, published date, link) shows on every version, saying which one the citation points at. The usage panel appears beside the Download that was pressed, is announced, uses the look's form styles, and says its answers were sent anonymously. The column dictionary links a code list to its columns, shows "No code list" muted for undocumented codes, counts a description that repeats the name as none, and folds each table into an open details with its column count. Per-file downloads are one button style at least 32 px tall with the size inside. The error and loading states keep an h1; errors offer Try again, Search the archive, and the current version's link; a missing version links to the current one; a failed sign-in offers Back to the dataset and Try again.
**Files:** `packages/web/src/routes/Dataset.tsx`, `packages/web/src/routes/Dataset.test.tsx`, `packages/web/src/UsagePanel.tsx`, `packages/web/src/Coverage.tsx`, `packages/web/src/App.tsx` (the signed-in header), `packages/web/src/auth.ts` (sign-out and the passkey link), `packages/web/src/routes/Callback.tsx`, `packages/web/src/styles.css`
**Checks:** `npm run typecheck -w packages/web`, `npm test -w packages/web`
**Serves:** DCSN3, DCSN4 (rests on call AGNT12)

- Tests: at 390 the document doesn't scroll sideways (jsdom can't measure, so this is checked in the walk; the unit test checks the card markup); a restricted page shows one Sign in and the contact; signed in, the header names the reader and Sign out clears the token; the versions list marks the cited version; Methods renders; the usage panel sits beside the pressed button and is announced; a repeated-name description shows as none; axe at 1280 and 390.

### Task 12: Download a resource whole, and Download all

**Does:** The page-writing step that publish and the reindex both call gains a zip writer: for each version it writes `package.zip` (every file of the version, with `datapackage.json`, `README.md` and `checksums.sha256`) and, for each multi-file resource, `<resource name>.zip` (its members), beside the version under `<open|restricted>/<id>/<v>/_zips/`, each in one PUT with a full-object SHA-256 like every archived object. It skips a zip that already exists with the same member hashes, so a reindex rewrites only what changed. The zips are listed as file items, so restricted ones go through the existing download route and open ones through `/data`. The page's Download all and each multi-file row's Download point at them, with the member list in a "Files in this set" details. The weekly integrity check covers them because they are written the same way. Waits on the coordinating session's answer on who owns the zip (thread 997); if Plan 6 or 7 takes it, this task shrinks to the page's buttons.
**Files:** `packages/backend/src/archive_backend/pages.py` (or a new `zips.py` beside it), `packages/backend/src/archive_backend/reindex.py`, `packages/backend/src/archive_backend/ingest.py` (its one call), their tests, `packages/infra/src/reindex.ts` (put on `_zips/`), `packages/web/src/routes/Dataset.tsx`
**Checks:** `uv run pytest packages/backend`, `uv run mypy packages`, `npm test -w packages/infra`, `npm test -w packages/web`
**Serves:** DCSN4

- Tests: the version zip holds exactly the version's files and its manifest, and its entries' hashes match `checksums.sha256`; a shapefile set's zip holds its four members; a second run writes nothing new; a restricted zip is a file item the download route accepts.

### Task 13: A static page for every version

**Does:** The page step writes `site/datasets/<id>/v<n>/index.html` for every version from the same template (its own version, citation and file links, and a link to the current version), beside the current page, at publish and in the reindex. The site function sends `/datasets/<id>/v<n>` and `/datasets/<id>/v<n>/` to that file. The template takes the brand's name, logo and colour, so the static page looks like the app before it takes over.
**Files:** `packages/backend/src/archive_backend/pages.py`, `packages/backend/src/archive_backend/reindex.py`, `packages/backend/tests/test_pages.py`, `packages/backend/tests/test_reindex.py`, `packages/infra/src/web.ts`, `packages/infra/test/web.test.ts`
**Checks:** `uv run pytest packages/backend`, `npm test -w packages/infra`, `just check`
**Serves:** DCSN4

- Tests: a reindex over a dataset with two versions writes three pages (current, v1, v2); the site function maps `/datasets/x/v2` to its page and leaves `/datasets/x` as before; the versioned page escapes manifest text as the current one does.

### Task 14: Themed sign-in, passkeys and the invitation email

**Does:** A `brand.ts` in the construct builds managed login's settings document (primary button, link and focus colours with the shared derived shades, form logo on, light mode, header off) and assets (the logo as `FORM_LOGO`, the favicon) from the brand block, and `Auth.addAppClients` passes them to each client's `CfnManagedLoginBranding` instead of Cognito's defaults. The user pool turns on choice-based sign-in with password and passkey as first factors, passkey user verification preferred, the relying party the pool's prefix domain, and both app clients allow `USER_AUTH` alongside the code flow. The invitation email's subject and body use the brand's name and the site's address. Synth fails with a plain message if an asset is over the limit.
**Files:** `packages/infra/src/brand.ts`, `packages/infra/src/auth.ts`, `packages/infra/src/research-archive.ts`, `packages/infra/test/auth.test.ts`, `packages/infra/test/brand.test.ts`
**Checks:** `npm run typecheck -w packages/infra`, `npm test -w packages/infra`, `just check`
**Serves:** DCSN3 (rests on calls AGNT11, AGNT12)

- Tests: each client's branding resource carries the brand colour and the logo asset and no `UseCognitoProvidedValues`; the pool's sign-in policy lists password and passkey; the relying party is the prefix domain; both clients allow `ALLOW_USER_AUTH`; the invitation email names the archive; the same shade function gives the app and the sign-in page the same button colour.

### Task 15: The walk on web-test

**Does:** Opens the PR with Tasks 8 to 14 and enables auto-merge. After it merges and you Go, deploys `ResearchArchive-web-test`, publishes the sample package open and again as restricted, invites a throwaway user, and walks it headless with Playwright at 1280 and 390: every check from PLAN1's walk, plus the new look and a second brand (a rebuild with a test config), no sideways scroll on a phone, page titles and focus, the restricted banner and one Sign in, sign-in on the themed managed login page, adding a passkey with a virtual authenticator and signing in with it, Download all and a shapefile's zip with their contents compared to `checksums.sha256`, a cited `/v1` page with the API cut off, and axe on every screen. Screenshots go in this folder's `screenshots/`. Then your look in your own browser, including signing in with a passkey on your own device. On your second Go, destroys the stage and confirms nothing is left.
**Files:** none changed; the walk's notes and screenshots go in the task's result and the folder
**Checks:** `just check` on main; `cdk deploy` and `just destroy web-test` exit 0
**Serves:** DCSN2, DCSN3, DCSN4

- The walk is a step on this folder's page, with a Go before the deploy and a Go before the teardown.
- On any AWS auth error, stop and report; never copy or export credentials.
