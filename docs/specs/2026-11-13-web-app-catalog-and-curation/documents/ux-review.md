# UX review: the reader's screens (search, dataset page, downloads, sign-in)

Reviewed 2026-11-14 on `origin/main` at `6853570`, worktree `plan8/ux-review`.

## How this was run

- **App:** `packages/web` served by the Vite dev server on :5199. The config was a scratch one outside the repo (`mock/vite.mock.config.ts`) that merges the repo's own `vite.config.ts` and adds middleware answering `/api/search`, `/api/datasets/{id}`, `/versions` and `/versions/{v}`, `/usage`, `/data/...` and `/auth-config.json`.
- **Mock data:** built from `examples/sample-package/datapackage.json` in the shapes of `src/schema/openapi.json`. There are two datasets: the open package, and a copy under a `restricted/` prefix with `archive:access: by-request`. Each has versions 1 and 2. A `state.json` switches the API between slow (4 s) and down (502).
- **Driving it:** Playwright (Chromium) at 1280 and 390 wide (390 at 2x pixel density), in `mock/walk.mjs`, `mock/keys.mjs` and `mock/crop.mjs`.
- **Accessibility check:** axe-core 4.14 injected into each settled screen: 26 runs.
- **Real deploy:** cross-checked against `walk-1…5.png`. Sign-in and the signed-in restricted page come only from those, since there is no Cognito locally.
- **Reference archives:** Zenodo search and the record [zenodo.org/records/3985919](https://zenodo.org/records/3985919); the Dryad record [doi:10.15146/R3D59D](https://datadryad.org/dataset/doi:10.15146/R3D59D). Screenshots are at `ux/ref-zenodo-search.png`, `ux/ref-zenodo-record.png` and `ux/ref-dryad-record.png`. The EDI portal and the data.gov catalogue gave nothing usable to the fetcher, so they aren't cited.
- **Mock artefact, not a finding:** because the mock reuses one manifest for both versions, the v2 citation reads "Version 1" (`ux/22-copied-1280.png`). See D11 for the real risk behind it.

**Overall.** The app is clean, readable at desktop and technically accessible: axe finds nothing on any screen, focus is always visible, and labels and landmarks are right. Every state the spec asks for exists. Its weaknesses are the ones a reader feels:

- On a phone the dataset page doesn't fit, and the download column sits off-screen.
- A multi-file resource (a shapefile) downloads as one useless file.
- Restricted access says nothing about who can get in or how.
- A result card doesn't tell a reader enough to choose between datasets.
- The page title never changes.
- Error states are dead ends.

Severity scale: **Blocks** means a reader can't do what they came for. **Hurts** means they can, with friction or confusion. **Polish** means it looks or reads unfinished.

---

## 1. Whole app (header, titles, navigation)

**A1. Every page's `<title>` is "research-in-a-box". Hurts.**
Every tab, bookmark, history entry and search-engine result reads "research-in-a-box". That is the repo's name, not the publisher's ("Invented Research Cooperative"), and not the dataset's. Screen-reader users hear no page change when a route changes, because the title and the focus both stay put. This fails WCAG 2.4.2 (Page Titled); axe can't see it in a single-page app.
Evidence: `ux/report.json`, where `title` is the same on all 32 screens. `index.html:6`.
*Do:* set `document.title` per route: "Search · {publisher}", "{dataset title} · {publisher}", "Dataset not found · {publisher}". Also set `index.html`'s `<title>` from `__PUBLISHER__` at build.

**A2. After a route change, focus goes to `<body>`. Hurts.**
After opening a result with Enter, or pressing Clear filters, focus lands on `<body>`. A keyboard reader's next Tab goes to the first control on the new page, and a screen-reader user isn't told the page changed. Evidence: `keys.mjs` output, "after opening result: … focus BODY" and "after Clear filters: … focus BODY".
*Do:* on navigation, move focus to the new page's `<h1>` (`tabIndex={-1}`). After Clear filters, move it to the search box.

**A3. The header is one unstyled bold link, with no search box, no "About", no footer and no sign-in state. Hurts.**
On a dataset page the only way back to search is the publisher name. It is black, not underlined, and doesn't look like a link. There's no search box in the header (Zenodo and Dryad both keep one there, see `ref-*.png`). There's no "about this archive" or contact link, which matters for restricted data (see D4), and no footer.
Screenshots: `ux/07-dataset-open-1280.png` and `walk-5-signed-in.png`.
*Do:* give the header a "Search" link or a compact search box on non-search pages, an "About / Contact" link, and a signed-in indicator with Sign out. Add a small footer with the publisher and a contact address.

**A4. No skip link. Polish.**
On search, a keyboard reader tabs through the header link, the search box, nine facet checkboxes and two year boxes, 13 stops in all, before reaching the first result (`keys.mjs` "SEARCH TAB ORDER"). With a real catalogue's formats and projects that becomes dozens.
*Do:* add "Skip to results" on search and "Skip to content" globally.

---

## 2. Search

**S1. A result card doesn't say what the dataset holds or when it was published. Hurts. This is the main findability gap.**
The card shows the title, three lines of description, and a single row of identical grey pills: `open`, `CC-BY-4.0`, `csv`, `shp`, `asc`, `xlsx`, `md`, `png`, `2024-06-01 to ongoing`, `Ada Invented`. A reader can't tell:
- which pill is access, which licence, which format, which person;
- when the dataset was published or last updated;
- how big it is;
- whether it's version 1 or 5.

The access pill, the one fact that decides whether a reader can use the data at all, looks the same as `md`. File-extension pills (`asc`, `md`, `png`) are noise to most readers: `md` is the methods document, not data. In the real deploy the open and restricted copies were told apart only by "(restricted copy)" in the title (`walk-1-search.png`).

Compare Zenodo (`ref-zenodo-search.png`). A coloured access chip with a lock icon, a date-and-version chip and a type chip come first. Then the title, then authors on their own line, the description, and "Uploaded on …".

Screenshots: `ux/02-search-results-1280.png` and `ux/02-search-results-390.png`.

*Do:*
1. Put the access state first as a distinct chip, with an icon and colour and the word in plain English: "Open", or "Restricted: sign-in required".
2. Put creators on their own muted line under the title, not in a pill.
3. Add a meta line: "Published 2026-11-14 · Version 2 · 9 files, 50 kB · 2024–ongoing". `published`, `version` and `bytes` are already in `CatalogRow`, unused.
4. Show the licence once, in words if short ("CC BY 4.0").
5. Drop raw extensions from the card, or show at most "Tables (CSV, Excel), GIS (shapefile, raster), documents".

**S2. On a phone the results start below the fold, under every filter. Hurts.**
At 390 wide the facets stack above the results. "2 datasets" begins around 745 CSS px down, so the first title is barely visible in an 844 px viewport, with only two datasets and six formats. Each new format, licence or project pushes the results further down.
Screenshot: `ux/02-search-results-390.png`.
*Do:* below 40rem, collapse the filters behind a "Filters (n active)" disclosure button above the results, or move them after the results. Keep the result count next to the search box.

**S3. On "No results" the facets vanish. Hurts.**
With `q=glacier` the Access, Licence and Format boxes disappear, leaving only Years (`ux/04-search-none-1280.png`). Only a facet value the reader had already checked stays, shown as "(0)". The reader loses sight of what the archive holds, and "Clear filters" also wipes the query.
*Do:*
1. Keep each facet group visible, with the values it has across the whole archive, greyed at 0, so the reader can see what to widen.
2. Echo the query: "No datasets match 'glacier'".
3. Offer "Clear filters" (keeping the query) and "Search everything" separately.
4. Suggest checking spelling or using fewer words.

**S4. The year filter is two tiny number spinners with no feedback. Hurts.**
`type=number` boxes, 5rem wide, with spinner arrows. A reader who types "24" or "202" sees nothing happen; the filter only applies at exactly four digits, with no message. A From year later than the To year isn't caught. Inside the 14rem sidebar the labels wrap awkwardly against the boxes (`ux/02-search-results-1280.png`).
*Do:*
1. Use `type="text" inputMode="numeric" pattern="\d{4}"` with a visible hint ("e.g. 2019").
2. Show an inline message for an incomplete or reversed range.
3. Lay the boxes out as "From [____] to [____]" on one line, as Zenodo does (`ref-zenodo-search.png`).

**S5. Facet labels are raw tokens. Polish.**
`open`, `by-request` (`restricted` in the deploy), `CC-BY-4.0`, `asc`, `shp`, `md`. Readers don't know `asc` is a raster grid.
*Do:* map the tokens to labels: "Open access", "By request", "CC BY 4.0", "Esri ASCII grid (.asc)", "Shapefile (.shp)", "Markdown (.md)". Keep the token in the URL. Consider grouping formats into kinds, as the dataset page's `archive:kind` already does: table, vector, raster, document.

**S6. Previous and Next show even when there's only one page. Polish.**
With 2 results both buttons render, both disabled (`ux/02-search-results-1280.png`). That's clutter, and it suggests the list is cut short.
*Do:* hide the pager when `total <= PAGE_SIZE`. Otherwise show "Page 1 of 3" with the buttons.

**S7. There's no sort, and the empty search doesn't say what it is. Polish.**
At `/` the page lists every dataset under "Search the archive", with no word on what the archive holds, no total ("12 datasets in the archive"), and no sort (relevance, newest, title). Zenodo has "Sort by" and a result total (`ref-zenodo-search.png`).
*Do:* add a one-line description of the archive under the h1, from config. Phrase the count as "N datasets in the archive" when there's no query. Add "Sort: Newest | Title", plus Relevance when there's a query.

**S8. Loading and error states are fine but bare. Polish.**
"Searching…" (`ux/05-search-loading-1280.png`) is announced politely and leaves the previous results up, which is good. On first load, though, the facets are missing until the answer arrives, so the layout jumps sideways. "Search is unavailable right now." with Try again (`ux/06-search-down-390.png`) is honest, but gives no time to retry and no other route to the data.
*Do:* reserve the sidebar's width while loading. In the error state, add "If this keeps happening, contact {publisher}", linking to the contact from A3.

**S9. There's no search button, and Enter does nothing visible. Polish.**
The box searches 300 ms after typing stops. Pressing Enter keeps the URL as it is (`keys.mjs`: "after Enter url …?q=glacier"), so nothing confirms the search ran. Some readers will look for a button.
*Do:* add a submit button with a magnifier icon and the visible text or accessible name "Search", and make Enter apply the search at once.

---

## 3. Dataset page

**D1. On a phone the page is 628 px wide in a 390 px screen, and Download is off-screen. Blocks a reader.**
At 390 wide the document scrolls sideways (`scrollWidth` 628). The Files table pushes Size and Download past the right edge, and the Columns table hides Description and Codes. The About list's 11rem label column squeezes values into a ~110 px strip; the Rights URL is clipped.
Screenshots: `ux/07-dataset-files-viewport-390.png`, `ux/07-dataset-columns-viewport-390.png`, `ux/07-dataset-open-390.png` (full page) and `ux/09-dataset-restricted-390.png`.
*Do:*
1. Below 40rem, render Files as stacked cards (title, kind, size, then a full-width Download button) instead of a table.
2. Wrap the Columns tables in a horizontal scroller (`overflow-x: auto`, with a visible edge or hint), or stack each column as a card.
3. Stack the About `dt` above its `dd` on narrow screens.
4. Give long URLs `overflow-wrap: anywhere`.

**D2. Downloading a multi-file resource gives one unusable file, and there's no "download all". Blocks a reader** (for GIS data); it hurts otherwise.
The Sites row's main Download fetches only `sites.shp`. A shapefile without its `.shx`, `.dbf` and `.prj` won't open, and the three sidecars are separate Download links squeezed into the File column. Stream depth (`.asc` plus `.prj`) has the same problem. A reader who wants the dataset needs nine clicks, plus one for the linked file. On a restricted dataset that's 14 "Sign in to download" buttons.
Dryad has a prominent "Download full dataset" (`ref-dryad-record.png`). Zenodo offers "Download all" on every record.
Screenshots: `ux/07-dataset-open-1280.png` and `ux/09-dataset-restricted-1280.png`.
*Do:*
1. Give each multi-file resource one "Download (4 files, 697 B)" that delivers all of them: a zip built at publish time, or a sequence of downloads.
2. Move the member list into a `<details>` "Files in this set".
3. Add a primary "Download all (9 files, 50 kB)" for the whole version, including `datapackage.json` and `README.md`, near the top of the page.
This needs a zip per version (or per resource) from the publish step; until that exists, at least label the main row "Download .shp only" and list the set.

**D3. The page leads with prose and a citation; the files are two screens down. Hurts.**
The order (description, pills, citation, About, Files, Columns) follows the README, which suits a printed document but not a reader deciding whether the data fits. At 1280 the Files heading sits ~700 px down. At 390 it is ~2 screens down. Neither page states the dataset's size or file count anywhere above the fold.
Dryad puts "Data files" with "Download full dataset" directly under the title, the citation in a sidebar card, and the abstract below. Zenodo puts the citation, versions and DOI in a right column and the files right after the description (`ref-dryad-record.png`, `ref-zenodo-record.png`).
*Do:* keep a single page with no tabs, as the spec says, but reorder:
1. Title, then a meta line: creators · published · version · licence.
2. An access banner (D4).
3. Description.
4. A summary strip: "9 files · 50 kB · tables, GIS, documents · 2024-06-01 to ongoing · 3 sites" with "Download all".
5. Files.
6. Columns.
7. About.
8. Cite. On wide screens, put Cite in a right-hand column near the top, as Zenodo and Dryad do.

**D4. Restricted access isn't explained. Blocks a reader** without an account; it hurts one with an account.
The page shows a grey `by-request` pill (`restricted` in the deploy) and a "Sign in to download" button on every row. It doesn't say:
- what "restricted" or "by-request" means;
- who can sign in (accounts are invitation-only, per the spec);
- how to ask for access, or whom to contact;
- that metadata and columns stay public while files need an account.

A reader with no account presses Sign in and meets a bare Cognito form with no sign-up and no way back (`walk-4-login.png`): a dead end. "by-request" implies a request path that doesn't exist.
Screenshots: `ux/09-dataset-restricted-1280.png`, `walk-4-login.png` and `walk-5-signed-in.png`.
*Do:*
1. Show a banner under the title: "Restricted: files are available to invited accounts. Sign in, or request access from {contact}." Include one Sign in button.
2. Let the rows say "Sign in above to download" (or show a lock icon) instead of 14 buttons.
3. For `by-request`, show the request route: a mailto, or a form later.
4. Brand Cognito's managed login (logo, archive name, a "Back to {publisher}" link) through managed login branding.
5. Say "invitation only, no sign-up" on the sign-in page, or in the banner before the redirect.

**D5. There's no signed-in state and no sign-out. Hurts.**
After signing in (`walk-5-signed-in.png`) nothing on the page says so: the buttons just read "Download". There's no Sign out, which matters on shared machines. Because tokens live in memory, a reload signs the reader out without a word. When the token expires, the message only appears after the reader presses Download.
*Do:* show "Signed in as {email} · Sign out" in the header (A3). On restricted pages, say "Signed in; you can download these files" in the banner. Note that a reload needs one click to sign in again.

**D6. The usage panel opens out of sight and far from the click. Hurts.**
After a download starts, the panel is inserted below the Files table. At 390 wide its top is 1321 px down in an 844 px viewport, so the reader never sees it (`ux/15-usage-after-click-viewport-390.png`, `crop.mjs` output). Even at desktop it's 13 Tab presses from the link that opened it. Its controls are unstyled native selects of different widths (`ux/15-usage-1280.png`), and "Thank you." replaces it with no sign of what was sent.
*Do:* show it as a small non-modal toast or inline card next to the Download that was pressed, or at the top of the Files section, and announce it ("Download started. Optional: how will you use this data?"). Give the two selects the same width, set off "Send" as the primary button, and make the thanks text "Thanks, your answers were sent anonymously."

**D7. Spatial coverage is four raw numbers. Hurts.**
"west -72.74, south 44.23, east -72.66, north 44.32" means nothing to most readers. They want "where is this?"
*Do:* show a small static map of the bounding box (an OpenStreetMap tile image, or an SVG outline of the region), with the description first: "Three invented sites along two streams (Vermont, USA)". Keep the numbers in small type for people who need them. EDI's portal and data.gov show a map for spatial coverage.

**D8. Methods, funding and related work aren't shown. Hurts.**
The manifest has `archive:methods` ("Hourly loggers with field checks…"), and the About section doesn't render it. The spec's About list omits it too. Methods are the second thing a scientist reads after the description; Dryad gives them their own section (`ref-dryad-record.png`). `archive:funding` and `archive:relatedIdentifiers` aren't rendered either.
*Do:* add Methods (and Funding and Related works, when present) to About. Link the methods document from the Files list there ("Full methods: docs/methods.md").

**D9. The current page offers no version history. Hurts.**
The current page shows only a "Version 2" pill. Nothing lists the versions or links to v1, though `GET /versions` exists. The note on v1 that a newer version exists is good (`ux/08-dataset-v1-top-1280.png`). Zenodo shows a Versions card with dates and a "cite all versions" explanation (`ref-zenodo-record.png`).
*Do:* add a "Versions" list (number, published date, link) to the page, or to its sidebar on wide screens. Say which version the citation points at.

**D10. The column dictionary needs small fixes. Polish.**
- The Codes cell shows the resource name `condition-codes` as plain text. It should link to that resource's columns and its download.
- "undocumented" in Codes reads like a code value. Style it muted, as "No code list", like "No description".
- A description identical to the column name (`depth_cm` → "depth_cm") should count as no description.
- Field names in `code` render at 13 px next to 16 px text, too small and visibly uneven. Use 0.9em.
- Long dictionaries make the page long. Wrap each table's dictionary in an open `<details>` with the column count in its summary.
Screenshot: `ux/07-dataset-open-1280.png` (the Columns section).

**D11. The citation could do more. Polish.**
It's plain text with Copy. "Copied" appears as small text with no style (`ux/22-copied-1280.png`). There's no BibTeX, RIS or DOI. When `archive:citation` is present it's used verbatim, so its "Version 1" can disagree with the archive version in the URL (`…/v2`) if a later version keeps the old citation text. That's a real risk for any curated citation.
*Do:*
1. Style "Copied ✓" next to the button.
2. Offer BibTeX and RIS downloads.
3. Warn in curation, or generate the citation's version, when the stored citation's version doesn't match the published version.

**D12. Badge row on the page. Polish.**
`open`, `CC-BY-4.0`, `Version 2`: the same pill problem as S1. On the current page the Published date only appears when the manifest carries `archive:published`. `DatasetAnswer` has no `publishedAt`, so whether the current page shows a date depends on the publish pipeline. It did in the deploy (`walk-2-page.png`) but not in the mock.
*Do:* replace the pills with a meta line, and make the API return the current version's `publishedAt`.

**D13. The table header says "Download" and the cells say "Download" again. Polish.**
Open rows use underlined links and restricted rows use buttons, so the two kinds of page look different for the same action. Download links are 18 px tall: below the 24 px target size (WCAG 2.5.8) and fiddly on touch.
*Do:* use one button style for every per-file download, at least 32 px tall, with the file size inside: "Download (3.4 kB)". Drop the separate Size column on mobile.

---

## 4. Loading, not found and errors

**E1. "This dataset can't be loaded right now." is a dead end, and it's what a cited link shows. Hurts.**
The heading is just "Dataset", with no Try again, no link to search and no contact (`ux/11-dataset-down-1280.png`). The current page has the static-page fallback, but the versioned URL `/datasets/<id>/v<n>` (the one the citation gives) is rewritten to the bare app shell (`packages/infra/src/web.ts:29-41`). If the API is down, every cited link lands here.
*Do:*
1. Add Try again, "Search the archive", and the dataset id with a link to `/datasets/<id>` (which has the static page).
2. Better still, write a static page per version at publish time, so cited URLs survive an API outage.

**E2. The not-found pages are good. Polish only.**
"Dataset not found" and "Page not found" each name the problem and link to search (`ux/12-dataset-missing-1280.png`, `ux/13-version-missing-1280.png`, `ux/14-page-404-1280.png`). When the dataset exists but the version doesn't (`/v9`), say so and link to the current version, instead of "There's no dataset … version 9".

**E3. Loading the dataset is a bare line with no heading. Polish.**
"Loading the dataset…" with no h1 (`ux/10-dataset-loading-1280.png`). In production the static page covers this, but versioned URLs don't have one.
*Do:* keep an h1 ("Loading dataset…"), or a skeleton of the title, so the layout doesn't jump.

**E4. Sign-in failure. Polish.**
"Sign-in didn't finish. Back to search." loses the dataset the reader was on.
*Do:* store `returnTo` before the redirect, as the app already does, and offer "Back to {dataset}" and "Try signing in again".

---

## 5. Typography, spacing and visual hierarchy

**T1. The page has one visual weight. Hurts at a scan; polish in detail.**
Everything is 16 px system-ui with grey hairlines: the h1, h2s, tables, pills, buttons. Nothing is a primary action. "Download" looks the same as "Copy" and "Previous". Blue links are the only colour. It reads as a well-formatted document, not as a place to get data.
*Do:*
1. Make one primary button style (filled accent) for "Download all" and "Sign in"; keep the grey style for the rest.
2. Give access a colour: green for open, amber for restricted.
3. Give section h2s a top margin of about 2.5rem and a hairline, so the long page breaks into sections.
4. Set the body measure to ~70ch for the description and purpose text.

**T2. Small details. Polish.**
- Facet fieldsets use a 1px border with a legend overlapping it, which looks like default browser styling. Use plain headings and spacing instead.
- The usage panel's selects and textarea have default 1px black borders, unlike the 6px-radius buttons.
- The Copy button sits apart from the citation box, with a gap. Put it inside the box, top right, as Dryad does.

---

## 6. Accessibility summary

- **axe-core:** 0 violations across 26 runs (13 screens × 2 widths; the two loading screens and the thank-you state weren't run): search empty, results, faceted, none and down; dataset current, v1, restricted and down; dataset not found; version not found; 404; and the usage panel open. See `ux/report.json`.
- **Contrast:** the muted text #59636e on white is about 6.0:1 and the accent #0b5cad about 6.6:1, both above AA.
- **Focus:** a 2px accent outline on every focused control. The order is logical, nothing traps focus, and the disabled pager is skipped (`ux/20-keyboard-facet-focus-1280.png`, `ux/21-keyboard-download-focus-1280.png`).
- **Headings and landmarks:** one h1 per screen; h2 for each section and result; h3 for each columns table; `header`, `main`, `search`, `aside` and `nav[aria-label=Pages]` all present. Hidden text makes each Download and Sign in button unique ("Download Logger readings").
- **Gaps axe doesn't catch:** A1 (title), A2 (focus on route change), A4 (skip link), D13 (target size), S4 (silent year input), D6 (the panel appears out of view and isn't announced).

---

## Top ten changes, in order

1. **Fit the dataset page on a phone** (D1): stack Files into cards with full-width Download buttons, scroll or stack the Columns tables, stack the About list.
2. **Download a resource whole, and add "Download all"** (D2): one action per shapefile or raster set, and one for the version (with `datapackage.json` and `README.md`).
3. **Explain restricted access** (D4): a banner saying who can get in, how to request access and whom to contact; one Sign in instead of 14; branded managed login with a way back.
4. **Make result cards decision-ready** (S1): a distinct access chip, creators on their own line, a published · version · size · coverage meta line, licence in words, no raw extensions.
5. **Title every page and move focus on navigation** (A1, A2): "{dataset} · {publisher}", focus to the h1.
6. **Put the files near the top** (D3): a meta line and summary strip with Download all; then Files, Columns, About; citation in a side column on desktop.
7. **Give error pages a way forward, and give cited version URLs a fallback** (E1): Try again plus links; static per-version pages so citations survive an API outage.
8. **Collapse filters on mobile and keep checked facets visible when nothing matches** (S2, S3).
9. **Show the usage panel where the reader is** (D6): next to the pressed Download, announced, styled; and show signed-in state with Sign out (D5).
10. **Give the page a visual hierarchy and fill the content gaps** (T1, D7, D8, D9): one primary button style, coloured access, a small map for spatial coverage, Methods in About, and a versions list.
