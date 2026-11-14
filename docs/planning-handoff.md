# Research archive in a box: planning handoff

Written 2026-11-12. This document starts a set of planning sessions. It is self-contained: a planning agent that reads only this file and the files in this folder has what it needs. No other document is required.

## How to use this document

1. Read "Project in one page", "Decisions already made" and "What we learned from FEMC's data". These apply to every plan.
2. Pick a plan from "The plans". Each one has a brief and a starter prompt.
3. Start a planning session with that brief. Plans in the same wave can run in parallel.
4. When a session settles an open question or changes an interface, record it in "Decision log" at the end of this file so other sessions see it.

### Ground rules for every planning session

- **Decisions listed here are settled.** Do not reopen them unless something in the session shows they cannot work. If so, stop and flag it.
- **Open questions are decided with Court, one at a time.** Present the options, a short trade-off table and a recommendation, then wait. Do not write a proposal into the plan as if it were decided.
- **Nothing is invented about FEMC.** Use only what is in `practice-data/` and in this document. Where a source is silent, say so.
- **Generic first.** Nothing in the core may be specific to FEMC or to ecology. FEMC is one config file plus the ecology profile.
- **FEMC is an example, not the source.** Design the format, the rules and the archive from the standards and from what any research group needs. FEMC's data tests the design afterwards, and migrating FEMC is its own plan once the format and the local tool exist.
- **Each plan ends with something usable on its own.**

## Project in one page

**What it is.** An MIT-licensed, open source kit that lets a small research group clean, package, archive and share its data. The working description is "research archive in a box".

**Why.** Small research archives do important work, but their data is often hard to find, hard to use, and submitted with missing metadata. The FEMC data archive at the University of Vermont (https://www.uvm.edu/femc/data/index) is the motivating case and the first reference deployment. Court has a contact there. The kit must also stand alone for anyone else.

**The three parts.**

| Part | What it does | Runs where |
| --- | --- | --- |
| Local tool | Inventory, profile, diagnose, tidy, package and audit data | The user's own machine, with no network needed |
| Archive in a box | Receives packages, then stores, catalogs and serves them | The adopter's own AWS account |
| Agent layer | Skills, a plugin and an MCP server that drive both | The user's own Claude |

**The contract between them** is the package: a plain folder that is also a valid Frictionless Data Package.

```
my-dataset/
  datapackage.json   manifest
  data/              tidy tables (CSV first, Parquet later)
  original/          untouched source files
  docs/              methods, protocols, field sheets
  changes.jsonl      every cleaning step, with evidence
  checksums.sha256
  README.md          generated, human-readable
```

**Where things are.**

| Thing | Location |
| --- | --- |
| Repo folder | `/Users/courtschuett/GitHub/personal/research-archive-in-a-box` |
| Practice downloads from FEMC | `practice-data/femc/` (six datasets, see `SOURCES.md` there) |
| First converted package | `practice-data/packages/ozone-bioindicators/` |
| Conversion sketch | `practice-data/packages/_build/build_ozone.py` (one dataset only, not the real tool) |
| This handoff | `docs/planning-handoff.md` |

`practice-data/` is in `.gitignore`. Licenses vary per dataset, so none of it is committed.

**State of the folder.**

- It is not a git repository yet. Plan 1 decides the layout, so `git init` waits for that.
- `practice-data/` exists only on Court's machine. A fresh clone elsewhere will not have it. `practice-data/femc/SOURCES.md` lists where each file came from.
- There is no code yet apart from the one conversion sketch.
- An earlier working document exists as a private web page that a local agent cannot open. It is not needed. Everything in it that still holds is in this file, and where the two differ, this file is correct.

## Decisions already made

### Framing and delivery

- A generic research archive in a box, with FEMC as the first reference.
- MIT license.
- Adopters fork the repo, edit one config file and deploy with the included CI.
- The code is a CDK construct plus a thin default app, so a library release can follow. A one-click template is deferred.
- CI is part of the kit. GitHub Actions is assumed and not yet confirmed.
- A deployment skill ships in the repo, so a fork can be set up and deployed with Claude Code. It covers every optional setting.
- A human-readable findings report for FEMC is a deliverable alongside the code.

### Languages

- Python throughout: contract, local tool, CLI and backend. Adopting teams are likely to be Python-focused.
- CDK in TypeScript.
- Web app in React with Vite, built to a static bundle. It is the only TypeScript application code, and it reads a JSON Schema generated from the Python contract.

### Data and format

- Source of truth: complete packages in S3. Databases, search indexes and web pages are derived and rebuildable by one `reindex` command.
- The package is a valid Frictionless Data Package with our additions.
- CSV first. Parquet must be easy to add later: columns are described by logical type, table reading goes through one interface backed by DuckDB, and `format` on a resource is the only place the file type appears.
- Core plus profiles. Core is small and domain-neutral. Profiles add domain rules, with ecology first. One archive config file per deployment picks profiles and sets required fields, vocabularies, themes, licenses and access levels.
- EML import and export is mandatory. schema.org and DataCite metadata are generated from the manifest. Nobody edits them by hand.
- Validation in two layers. Structure: Pydantic models are the contract and generate the JSON Schema. Quality: our own rules engine, using DuckDB for checks on data tables, produces graded findings with evidence.
- We test compatibility against the Frictionless library and do not depend on it at run time.

### Infrastructure

- As serverless as possible.
- Index: DynamoDB with no relational database. Semantic search uses a DynamoDB vector index, one partition key per archive.
- On publish, the whole catalog is also written as one file, `catalog.json`. Search runs on the server: `GET /api/search` filters it in the API Lambda's memory (changed by Plan 6, see the Decision log).
- Rebuild path: `reindex` writes a DynamoDB JSON file to S3 and loads it with DynamoDB bulk put items.
- Ingest: one Lambda durable function in Python, not Step Functions. Curator review is a callback wait inside it.
- Review is controlled by an admin at run time: when review is required, rules for skipping it, stricter cases, who reviews, reminders. Curators can approve, reject or request changes.
- Accounts: Cognito with email sign-in by default, by invitation only: there is no self-service sign-up, and an admin invites each user with an optional group. ORCID and university single sign-on are optional. Open data needs no account.
- The CLI and plugin sign in through the browser and hold short-lived tokens only.
- Web hosting: a static site on S3 and CloudFront, with pages backed by the API. No server-side rendering.
- Public dataset pages are a hybrid. At publish, the pipeline writes a small HTML file per dataset with the title, description, citation and schema.org metadata. That file loads the web app, which fetches live details from the API.
- Downloads: open data direct from CloudFront at stable URLs. Restricted data goes through an API check that returns a short-lived link. The two live under separate prefixes.
- By-request data starts a small durable function that emails the data owner and waits on a callback.
- AI: no generative AI on the server. Reviewing, auditing and drafting metadata happen in the user's own Claude through the plugin and MCP server. The server's only model use is optional embeddings for semantic search, through Bedrock. With embeddings off, the archive falls back to keyword search.
- Preservation default: versioning plus a scheduled integrity check. Write-once locking is an option in the config. A second-region copy is not offered.
- Operations defaults: API Gateway throttling, a budget alarm, failure alerts and a dashboard in every deploy. WAF is optional.
- DOIs: an optional module using DataCite credentials from the config. Without them the archive runs on stable URLs.

## What we learned from FEMC's data

### From their public pages

- EML 2.1.1 per dataset, with package IDs like `vmc.1379.2933.1`. OGC for spatial data and ITIS for taxonomy.
- Each dataset sits under a parent project. Dataset pages have Overview, Metadata, Data and Documents tabs.
- Tabular data lives in a database and is exported as CSV on request.
- Access states: Unpublished, Downloadable, By Request, Description Only, and Linked, where FEMC holds the record and the data lives elsewhere.
- Browsing is six themes (air, climate change, forest, soil, water, wildlife) plus an All Projects tab and a separate advanced search. No API or bulk export is documented.
- Submission is by requesting an account and following a PDF user guide.
- Downloads are anonymous, with an optional form asking who you are and how you will use the data. FEMC uses this to justify funding.

### From the six practice datasets

| Dataset | What we have | Size |
| --- | --- | --- |
| Ozone Bioindicators | CSV, 165 rows, 17 columns | 17 KB |
| FIA tree-level data | CSV, 162,354 rows | 155 MB |
| IMPROVE fine aerosol | CSV, 971 rows | 1.3 MB |
| Aerial detection survey | Zip: shapefile set plus CSV and XLSX copies | 73 MB |
| Data Rescue Inventory | CSV, 338 rows | 319 KB |
| Camels Hump census data | Metadata only, the data is on GitHub | 3 KB |

- None of the six EML records contains a methods section.
- The Data Rescue Inventory file has 50 columns. Its EML lists 75 attributes, none with a definition, and 25 of them are not in the file.
- Metadata and file disagree in 3 of 5 tables: FIA has 207 columns in the file and 158 in the EML, the aerial survey 41 fields against 27 described, Data Rescue 50 against 75. IMPROVE matches (239).
- The aerial survey zip holds the same data three ways: a polygon shapefile set (47,801 features, USA Contiguous Albers, NAD83), a CSV and an XLSX. Its EML carries 7 code lists, some repeated across columns (DMG_TYPE1 to 3 share one 12-code list).
- Camels Hump's data location appears only inside the free-text citation; its distribution URL points back to FEMC's own page.
- All six EML records use a misspelled tag, `distibution`. The importer must tolerate it.
- Three hosted datasets show the license as "third party determines data license". Two show no license on the overview page.
- Downloaded files carry internal table codes as names, such as `Z0023_ozone.csv`.
- The largest file is 155 MB, which a single Lambda step can handle.

### From converting Ozone Bioindicators by hand

The package passes the Frictionless library's validation, including all 165 rows against the schema. It fails our draft quality check with 11 errors, 21 warnings and 4 notes, all from gaps in the source.

- 7 of 17 columns have no usable description. Four have none, three repeat the column name.
- The species column holds numeric codes with no code list.
- No license, no methods, no geographic coverage, no units.
- Declared coverage is 1997 to 2001, with no rows for 1998.
- Three columns hold the same value in every row.

Format lessons:

- Standard Frictionless properties must be left out when unknown, not set to null. Our extension properties can use null.
- Our additions sit under an `archive:` prefix.
- "Structurally valid" and "good quality" are separate verdicts and both belong in the manifest.
- Keep the type the source declares. Infer one only where the source is silent, and record the inference as a finding.
- People need a legacy role field. FEMC uses "principal investigator" and "content provider".
- A package needs a rights status as well as a license list.
- Legacy identifiers need a home: the EML package ID, the internal table name and the page code all differ.

## References

Several AWS features this design relies on are recent. A planning agent may not know them from memory, so check the linked pages before assuming a feature does not exist or works differently.

| Feature | What we rely on | Where to read |
| --- | --- | --- |
| Lambda durable functions | Workflow written as ordinary code with steps, waits and callbacks. Async executions can run up to one year. Each invocation is still limited to 15 minutes. The Python SDK is synchronous. Always set a timeout on a callback. | https://docs.aws.amazon.com/lambda/latest/dg/durable-basic-concepts.html and https://docs.aws.amazon.com/lambda/latest/dg/durable-execution-sdk.html and https://docs.aws.amazon.com/durable-execution/patterns/best-practices/pause-resume/ |
| DynamoDB vector search | Generally available since 2026-08-05. Vectors are stored on the item and searched with a vector index. We generate the embeddings ourselves. Each search is scoped to one partition key value, and the index updates asynchronously. | https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-dynamodb-vector-search/ |
| DynamoDB bulk put items | Generally available since 2026-11-05. Loads line-delimited DynamoDB JSON or Ion from S3 into an existing table without using table capacity. One operation per table at a time. Global tables are not supported at launch. | https://aws.amazon.com/blogs/database/introducing-bulk-put-items-for-amazon-dynamodb-load-data-from-amazon-s3-into-existing-tables-at-scale/ |
| Frictionless Data Package | The manifest uses the v2 profile. The Ozone package was validated with the `frictionless` Python library, version 5.21.0. | https://datapackage.org/profiles/2.0/datapackage.json |

Details not confirmed against AWS's own documentation, and to verify in the relevant plan: the result limit per vector search, and whether CDK has constructs for bulk put items.

FEMC pages:

- Data archive: https://www.uvm.edu/femc/data/index
- Data policy: https://www.uvm.edu/femc/data/policy
- Project list by theme: https://www.uvm.edu/femc/data/archive/project/themes
- A dataset's EML record is at its dataset URL plus `/eml_xmlview`.

Court's own tools, whose principles the local tool follows (local-first, state on disk, no phoning home, claims backed by evidence): https://subaud.tools

## The plans

Ten plans in three waves. Plans in the same wave can be planned in parallel.

| # | Plan | Wave | Depends on | Produces for others |
| --- | --- | --- | --- | --- |
| 1 | Repo and conventions | 0 | Nothing | Layout, tooling and naming that every plan uses |
| 2 | Package format and contract | 0 | Nothing | Pydantic models, JSON Schema, standard EML import and export, a committed sample package |
| 3 | Quality rules and local tool | 1 | 2 | Findings format, CLI, audit command |
| 4 | Archive infrastructure | 1 | 1, and the manifest shape from 2 | Storage, tables, auth, API shell, CDK construct |
| 5 | FEMC migration and practice corpus | 2 | 2, 3 | FEMC-tolerant EML import, converted packages, audit numbers |
| 6 | API and search | 1 | 2, 4 | OpenAPI spec, catalog file, search endpoints |
| 7 | Ingest, review and access | 2 | 2, 3, 4 | The publish pipeline and review workflow |
| 8 | Web app | 2 | 6, and 7 for submission screens | Catalog, dataset pages, submission, curator queue |
| 9 | Agent layer | 2 | 3, 6 | MCP server, plugin and skills |
| 10a | Deployment and CI | 2 | 4 | Deployment skill, CI workflows |
| 10b | The FEMC report | 3 | 5 | The report |

Plans 1 and 2 should be planned first, in parallel with each other. Plan 2 is the one most other plans wait on, so settle its open questions early. Plans 3, 4 and 6 can then run in parallel. FEMC migration (Plan 5) waits until the format and the local tool exist, and the FEMC report (10b) waits on the migration's audit numbers.

---

### Plan 1: Repo and conventions

**Goal.** A repo layout and toolchain that the other plans can assume.

**In scope.**
- One repo or several, and the folder layout for: Python contract, local tool, backend Lambdas, CDK app, web app, plugin and skills, docs, examples.
- Python packaging and tooling: package manager, lint, format, type check, test runner.
- How the CDK (TypeScript), web app (TypeScript) and Python code share one CI.
- Naming: the kit, the local tool and the Python package. Working ideas are `cruise` (a forest inventory survey) and `accession` for the local tool.
- Versioning and release approach.

**Out of scope.** Any feature design.

**Open questions to settle.**
- One repo or several.
- Names for the kit and the local tool.
- Is pip alone enough for the local tool, or do we also want a standalone app for people without Python?
- Confirm GitHub Actions.

**Done when.** A written layout, tool choices and names exist, and an empty skeleton could be created from them.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the repo layout and conventions for the research archive in a box (Plan 1). The stack is decided: Python for the contract, local tool and backend, TypeScript CDK, and a React with Vite web app. Work through the open questions with me one at a time, with options and trade-offs for each. Do not design features.

---

### Plan 2: Package format and contract

**Goal.** A written package spec and a Python contract package that every other part imports, designed from the standards and from what any research group needs. FEMC's data is one test of the finished format, not its source.

**In scope.**
- The package spec: folder layout, manifest fields, the `archive:` extension properties, versioning and identifiers.
- Pydantic models for the manifest, for profiles and for the archive config file.
- JSON Schema generation for the web app and the docs.
- The profile mechanism, with core and ecology as the first two.
- A project record that groups related packages.
- Resources that are not tables, such as shapefile sets and rasters.
- Linked resources, where the data lives elsewhere.
- Access levels and a rights status alongside the license list.
- Sensitivity flags per column.
- The change log format (`changes.jsonl`) and the findings format, agreed with Plan 3.
- EML import and export for standard EML. Tolerating FEMC's quirks (the misspelled `distibution` tag, attribute lists that disagree with the files) belongs to Plan 5.
- A committed sample package: a small invented dataset with a clear license, covering the shapes the format must hold, seeded with known gaps so tests have predictable findings. Moved here from Plan 1, since it needs the format first.
- schema.org and DataCite export.
- Compatibility tests against the Frictionless library.

**Out of scope.** The quality rules themselves (Plan 3). Storage and API (Plans 4 and 6).

**Inputs.** Frictionless Data Package v2, EML 2.x, DataCite and schema.org Dataset as the standards the format builds on and exports to. The hand-converted Ozone package in `practice-data/packages/ozone-bioindicators/` is one draft to learn from, not the template.

**Open questions to settle.**
- Should a package with no license be storable but not publishable?
- Do we rename columns to a house style, or keep source names and add labels?
- Where do code lists live when a column holds undocumented codes?
- How are versions numbered, and what makes a new version?
- How does a project relate to its packages in storage and in the manifest?

**Done when.** The spec is written, the sample package expresses every shape it covers, the six FEMC practice datasets can each be expressed in it on paper as a test, and the model list and module layout are agreed.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the package format and the Python contract (Plan 2), generic first. Pydantic for structure is decided. Start from what a research dataset package must hold, using Frictionless v2, EML, DataCite and schema.org, and the range of data shapes a small archive receives. Test the result against the FEMC practice datasets afterwards. Then take the open questions one at a time.

---

### Plan 3: Quality rules and local tool

**Goal.** A local-first command line tool that cleans, organizes and packages data, built on a rules engine that produces graded findings with evidence.

**In scope.**
- The rules engine: rule definition, severity, evidence rows, suggested fixes, and how profiles add rules.
- DuckDB as the table reader for CSV now and Parquet later.
- The commands: inventory, profile, diagnose, tidy, package, audit.
- The first rule set: mixed date formats, inconsistent units, species name variants matched against ITIS, swapped or out-of-range coordinates, placeholder values such as -999, spreadsheets with merged headers, descriptions that repeat the column name, constant columns, undocumented codes, coverage gaps.
- Tidy as a proposal with a reviewable change log. Originals are never modified.
- Audit mode: run over many packages and rank them by what needs fixing.
- A completeness score, and what it is made of.
- Behavior with no network.

**Out of scope.** Uploading to an archive (Plan 9 handles the client side, Plan 7 the server side).

**Principles.** Local-first, state on disk, no phoning home, every claim backed by evidence. The checks are deterministic code. An agent is optional and handles judgment calls only.

**Open questions to settle.**
- How the completeness score is calculated and shown.
- Which checks block a package and which only warn. This links to the license question in Plan 2.
- How ITIS lookups work offline.
- How far "inventory" goes in grouping a messy folder into datasets without an agent.

**Done when.** The command set, the rule format and the first rule list are agreed, and the plan shows the rules producing the sample package's known findings. The Ozone findings are a second test.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the quality rules engine and the local tool (Plan 3), generic first. Design the rules from what makes any dataset hard to use, then check them against the sample package from Plan 2 and the hand-made Ozone findings in `practice-data/packages/ozone-bioindicators/datapackage.json` under `archive:quality`. Then plan the commands. Take the open questions with me one at a time.

---

### Plan 4: Archive infrastructure

**Goal.** A CDK construct that stands up the archive's foundations in an adopter's AWS account.

**In scope.**
- The construct and the thin default app, driven by one config file.
- Storage: staging, archive and derived buckets, the open and restricted prefixes, versioning, optional write-once locking, the scheduled integrity check.
- DynamoDB table design for datasets, projects, submissions, review state, users and the download log, including the vector index.
- Cognito, with optional ORCID and university sign-in.
- API Gateway and the Lambda packaging approach for Python, including compiled dependencies such as Pydantic.
- CloudFront for the web app and for open data.
- Operations defaults: throttling, budget alarm, failure alerts, dashboard. Optional WAF.
- The `reindex` path using DynamoDB bulk put items.
- Dev and prod stages.

**Out of scope.** Pipeline logic (Plan 7), API endpoints (Plan 6), deployment skill (Plan 10).

**Open questions to settle.**
- Single-table or multi-table DynamoDB design.
- How the archive config file maps to construct properties.
- How optional modules are switched on without forking the construct.
- Whether the bulk put job is started from CDK, a Lambda or the CLI.

**Done when.** The resource list, table design and construct interface are agreed.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the archive infrastructure as a TypeScript CDK construct (Plan 4). The service choices are decided and listed under "Infrastructure". Do not reopen them. Plan the resources, the DynamoDB design and the construct's interface, and take the open questions with me one at a time.

---

### Plan 5: FEMC migration and practice corpus

**Goal.** A process that migrates FEMC's records into the finished format, proven on the practice datasets, with audit numbers that feed the FEMC report. Planned once the format (Plan 2) and the local tool (Plan 3) exist.

**In scope.**
- The standard EML importer from Plan 2, extended to tolerate what FEMC actually emits: the misspelled `distibution` tag, attribute lists that disagree with the files, data locations held only in citations, titles on the table rather than the dataset.
- Applying it to real FEMC records.
- Converting the remaining five datasets: a large table, a wide table with weak descriptions, a shapefile set, a table with no column definitions, and a linked record.
- Recording what could not be imported and why.
- Growing the corpus to 10 to 20 datasets. Still to add: one by-request dataset, one description-only record, and one with documents or images attached.
- The request to the FEMC contact for a bulk export.
- The FEMC archive config file: the ecology profile, six themes and their access levels.

**Rules for collecting data.**
- Hand-pick and download through the public pages.
- Do not scrape the whole archive without FEMC's agreement.
- Record each dataset's license as it is downloaded.
- Nothing from `practice-data/` is committed.

**Open questions to settle.**
- Which further datasets to add.
- When and how to approach the FEMC contact.

**Done when.** The corpus list is fixed and the conversion order and expected problems are written down.

**Starter prompt.**
> Read `docs/planning-handoff.md` and `practice-data/femc/SOURCES.md`. Plan the conversion of the FEMC practice corpus (Plan 5). One dataset is already converted by hand. Plan the other five in order of what each will teach us, and propose which datasets to add to reach 10 to 20.

---

### Plan 6: API and search

**Goal.** A read API open to all, a write API for signed-in users, and search that works with no relational database.

**In scope.**
- Endpoints for datasets, projects, files, submissions, reviews and admin settings.
- The OpenAPI spec, generated from the Python contract.
- The catalog file written at publish, and server search over it (Plan 6 moved search from the browser to the API).
- Semantic search: what text is embedded, the Bedrock call, the DynamoDB vector query, and the fallback when embeddings are off.
- Access checks and short-lived links for restricted data.
- Download counts and the optional usage form.
- Authentication for the browser, the CLI and the MCP server.

**Out of scope.** Table design (Plan 4). The pipeline (Plan 7). Screens (Plan 8).

**Open questions to settle.**
- Which embedding model.
- The catalog file's format and how large it can grow before a different approach is needed. Document the upgrade path.
- How keyword search and semantic search results are combined.
- The CLI and MCP sign-in flow with Cognito.

**Done when.** The endpoint list, the search design and the catalog file format are agreed.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the API and search (Plan 6). There is no relational database. Search is a catalog file filtered by the API, plus an optional DynamoDB vector index. Plan the endpoints and the search design, and take the open questions with me one at a time.

---

### Plan 7: Ingest, review and access workflows

**Goal.** The publish pipeline as one Lambda durable function in Python, with admin-controlled human review.

**In scope.**
- Pipeline steps: receive, scan, verify checksums, validate structure, run quality rules, derive previews and the spatial extent, review, publish, index, notify.
- The review step as a callback wait, with a timeout, reminders and a stale state.
- The "request changes" loop.
- The review policy an admin controls at run time, and where it is stored.
- The audit log of every decision.
- Publish: copy to the archive bucket, assign the version, write the per-dataset HTML file, generate EML and schema.org, mint a DOI if enabled, update the catalog file.
- The by-request access workflow.
- Extension points: extra check functions listed in the archive config.
- New versions of an existing dataset, and taking a dataset down.

**Out of scope.** The rules themselves (Plan 3). Screens (Plan 8).

**Constraints to respect.**
- Durable functions replay from checkpoints, so anything non-deterministic must sit inside a step.
- Each invocation is still limited to 15 minutes.
- The Python durable execution SDK is synchronous.

**Open questions to settle.**
- Large-file handling. The largest practice file is 155 MB, so this may not be needed at first.
- Malware scanning approach.
- What takedown means when versioning keeps every object.

**Done when.** The pipeline's steps, states and policy model are agreed, and the plan shows a submission moving through approve, reject and request-changes paths.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the ingest pipeline and the review and access workflows (Plan 7). It is one Lambda durable function in Python with a callback wait for curator review. That is decided. Plan the steps, the review policy an admin controls, and the request-changes loop. Take the open questions with me one at a time.

---

### Plan 8: Web app

**Goal.** A static React with Vite app for readers, contributors, curators and admins.

**In scope.**
- Reader screens: faceted search by theme, species, location, date range, license and format, a map view, and dataset pages with a data preview, column dictionary, copyable citation and license badge.
- The data preview using DuckDB in the browser on files served from CloudFront.
- The small pre-rendered HTML file per dataset and how the app takes over from it.
- Contributor screens: guided submission that shows the same findings as the local tool.
- Curator screens: the review queue, a submission's findings and data preview, what changed since the last version, and approve, reject or request changes.
- Admin screens: review policy and other run-time settings.
- Branding and themes from the archive config.
- Accessibility.

**Out of scope.** API design (Plan 6).

**Open questions to settle.**
- How forms are generated from the JSON Schema.
- The map library.
- What the app shows while the API is unreachable.

**Done when.** The screen list, the routes and the main user flows are agreed.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the web app (Plan 8): a static React with Vite app on S3 and CloudFront, backed by the API. Start with the reader's flow from search to dataset page to download, since findability is the main problem we set out to fix. The generated `README.md` in `practice-data/packages/ozone-bioindicators/` shows what a dataset page has to present.

---

### Plan 9: Agent layer

**Goal.** Anyone using Claude Code, or another AI client, can prepare, submit, find and review data without the web app.

**In scope.**
- The MCP server: tools for search, fetch, validate and submit, and how it signs in.
- The Claude Code plugin that bundles the MCP server with skills.
- Skills for researchers and curators: prepare dataset, submit dataset, find and use data, rescue data, review submission, audit and backfill.
- How skills call the local tool, so the checks stay deterministic and the agent handles only judgment.
- A GitHub Action for labs that keep data in a repo: validate on push, publish on release.

**Out of scope.** The deployment skill (Plan 10).

**Principles.** No generative AI runs on the archive's servers. Agents propose, and a person approves. Every route calls the same validator.

**Open questions to settle.**
- Where the MCP server runs: locally, as a Lambda, or both.
- How the "rescue data" skill records provenance for values read from scanned documents.
- What the skills do when the archive is not reachable.

**Done when.** The tool list, the skill list and each skill's steps are agreed.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the agent layer (Plan 9): an MCP server, a Claude Code plugin and the skills for researchers and curators. Generative work happens only in the user's own Claude. Plan the tools first, then each skill's steps, and take the open questions with me one at a time.

---

### Plan 10: Deployment, CI and the FEMC report

Two pieces that share a wave. Split them if that is easier.

#### 10a: Deployment skill and CI

**Goal.** Someone who forks the repo can deploy an archive with Claude Code, and CI keeps it tested and deployed.

**In scope.**
- The deployment skill, shipped in the repo: check prerequisites, ask about the archive and write the config, walk through every optional setting, connect GitHub Actions to the AWS account, deploy, create the first admin, load seed data and run a smoke test.
- Update and teardown.
- Confirmation before any step that costs money or cannot be undone.
- CI workflows: tests for Python, CDK and the web app, security checks, deploy to dev and prod with OIDC.
- Rolling a template change out to existing dataset pages by a rebuild.
- Seed data with a clear license.

**Open questions to settle.**
- Confirm GitHub Actions.
- What the smoke test covers.
- How upstream updates reach a fork.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the deployment skill and CI (Plan 10a). The skill ships in the repo and is for the person running an archive, not for researchers. Plan its steps and the points where it must stop and ask.

#### 10b: The FEMC report

**Goal.** A short, plain-language report that shows FEMC what we found in their own data and what the kit would do about it. It is for archive staff and partners, not engineers.

**Proposed outline.**
1. What the archive does well, stated first and specifically
2. What we looked at: which datasets, when, and how we got them
3. What we found, with real examples from their records
4. Before and after: one or two datasets shown as they are today and as cleaned packages
5. What the kit offers, in terms of their daily work
6. What adopting it would take, including a migration path from existing EML
7. Quick fixes they can make now, with or without us
8. Questions for them

**Principles.**
- Every finding cites a specific record, so they can check it.
- Counts come from the audit tool, not from impressions.
- The tone is collaborative. They have kept this data safe for decades.
- It is honest about limits: we saw only public pages and a sample.

**Open questions to settle.**
- Send a lighter version sooner, or wait for audit numbers from the full corpus.
- Who it is addressed to, and how it reaches them.

**Starter prompt.**
> Read `docs/planning-handoff.md`. Plan the FEMC report (Plan 10b). Sections 1, 2 and 7 can be drafted from what we already know. Plan what each section needs, which findings we can already support with a specific record, and which need the audit tool first.

---

## Open questions across plans

| Question | Owner plan |
| --- | --- |
| One repo or several | 1 |
| Names for the kit and the local tool | 1 |
| pip only, or also a standalone app | 1 |
| Confirm GitHub Actions | 1, 10a |
| A package with no license: storable but not publishable? | 2 |
| Rename columns or keep source names with labels | 2 |
| Where code lists live | 2 |
| How the completeness score works | 3 |
| Single-table or multi-table DynamoDB | 4 |
| When to approach the FEMC contact, and with what | 5, 10b |
| Which embedding model | 6 |
| Large-file handling in ingest | 7 |
| Where the MCP server runs | 9 |
| Confirm DataCite offers a test environment | 7 |

## Decision log

Add a line here whenever a planning session settles something that other plans rely on.

| Date | Plan | Decision |
| --- | --- | --- |
| 2026-11-12 | All | Everything under "Decisions already made" |
| 2026-11-12 | All | FEMC is an example, not the source: the format and rules are designed generically, and FEMC migration (Plan 5) moves after Plans 2 and 3. The FEMC report (10b) follows Plan 5. |
| 2026-11-12 | 1, 2 | The committed sample package moves from Plan 1 to Plan 2, as a generic invented dataset built once the format exists. |
| 2026-11-12 | 2, 5 | Plan 2 covers standard EML import and export. Tolerating FEMC's EML quirks moves to Plan 5. |
| 2026-11-12 | 1 | Plan 1's direction: one repo, a uv workspace (packages/contract, packages/tool, packages/backend) and an npm workspace (packages/infra, packages/web), GitHub Actions, one root justfile. |
| 2026-11-12 | 1 | Settled: the repo is research-in-a-box. The contract wheel is archive-contract (import archive_contract). The local tool's command is cruise. Tooling: Python >=3.12, ruff, mypy strict with the Pydantic plugin, pytest, hatchling. |
| 2026-11-12 | 1 | Nothing is published to PyPI or npm. cruise installs from the git repo with uv (`uv tool install "git+https://github.com/schuettc/research-in-a-box#subdirectory=packages/tool"`), and archive-contract is used through uv workspace sources. No standalone app. |
| 2026-11-13 | 2 | Rights: publishing needs a license or a stated rights status (public-domain, third-party, all-rights-reserved); `undetermined` can be packaged and audited but not published. |
| 2026-11-13 | 2 | Column names are kept from the source; a rename is offered by the local tool and recorded in changes.jsonl, with archive:sourceName on the field. |
| 2026-11-13 | 2 | Code lists are CSV tables under data/codes/, linked from columns by Frictionless foreign key; a coded column with no list is marked archive:codeList "undocumented". |
| 2026-11-13 | 2 | Versions: one stable package id; a file change makes the next integer version, metadata edits apply in place with a history; one DOI per version when DOIs are on. |
| 2026-11-13 | 2 | Projects are their own project.json record; packages point to one with archive:project. |
| 2026-11-13 | 2 | Several files that only work together (a shapefile set) are one resource: path names the main file, archive:files lists every member with size and hash. |
| 2026-11-13 | 2, 3 | The contract defines the Change and Finding models (drafted in Plan 2's spec); Plan 3 confirms or changes them when it starts. |
| 2026-11-13 | 4, 6, 7 | DynamoDB: one catalog table design (datasets, versions, projects, files; keys PK/SK plus GSI1 for a project's datasets), created twice as tables A and B; an SSM parameter `/research-archive/<stage>/catalog-active` names the active one and every Lambda reads it. Operational records get one plain table each: Submissions, Reviews, Settings, UserProfiles, DownloadCounts. All on-demand; point-in-time recovery on the operational tables. |
| 2026-11-13 | 4, 10a | Reindex is a Python durable function in the construct: it empties the inactive catalog table, bulk-loads it from the archive bucket's manifests, then flips the active-catalog parameter. An admin starts it with `just reindex <stage>` and follows it with `just reindex-status <stage>`. It runs while publishing is quiet; catching up publishes during a run is a follow-up for when Plan 7 publishes. |
| 2026-11-13 | 4, 6, 7, 10a | Infrastructure settings are an `infrastructure` section of the Python ArchiveConfig (stages, alert email, monthly budget, optional modules). The construct's TypeScript props type is generated from the contract's JSON Schema under the same CI drift check. A plan that needs a new setting adds it there. |
| 2026-11-13 | 4, 10a | One stage, `prod`, by default; an adopter adds others (such as `dev`) in `infrastructure.stages`, each optionally in its own account and region. One stack per stage, `ResearchArchive-<stage>`. The `prod` stage retains its buckets and tables; other stages tear down cleanly. |
| 2026-11-13 | 4, 6, 7 | The ResearchArchive construct exposes, for later plans to attach to: stagingBucket, archiveBucket, derivedBucket, catalogTables with activeCatalogParameter, submissions, reviews, settings, userProfiles, downloadCounts, userPool, api with its authorizer, distribution, alertTopic, and `pythonFunction(id, props)`, which builds an arm64 Python Lambda from archive-backend the way Plan 4's own are built. |
| 2026-11-13 | 4, 6 | Plan 6 owns the vector index on both catalog tables, the embedding model and its config setting, rolling CloudFront's standard logs (in the derived bucket's `logs/`) up into DownloadCounts, and counting restricted downloads. |
| 2026-11-13 | 4, 7 | Plan 7 owns the DOI config setting and its credentials parameter. |
| 2026-11-13 | 4 | Left out of Plan 4 as follow-ups: ORCID sign-in, university SAML sign-in and a custom domain. Email sign-in on the CloudFront domain is the default. WAF and write-once locking stay as optional modules. |
| 2026-11-13 | 3, 7 | Severity has one meaning: error blocks publishing (structure errors, core fields missing, profile- or config-required fields missing); warning (every column and value rule) and note never block. Plan 7's ingest uses the same rule. |
| 2026-11-13 | 3, 7, 9 | The quality rules live in cruise.rules, which imports without the CLI; the backend and the MCP server run the same rules by depending on cruise as a library. |
| 2026-11-13 | 2, 3 | Rule ids are <group>.<what> (package.*, field.*, values.*, beside structure.*). The ecology profile's three placeholder rules become core rules (field.unit-missing, values.dates-outside-coverage, values.coordinates-out-of-range); ecology.yaml's rules list is emptied. |
| 2026-11-13 | 2, 3 | Finding and Change confirmed as drafted, plus Evidence.count. QualityVerdict gains an unweighted completeness score (0-100) with passed/applicable counts for find, understand and trust. |
| 2026-11-13 | 3, 5 | Plan 3's first plan builds only the rules, cruise diagnose and cruise audit; tidy, package, inventory and profile are planned after diagnose has been used. The hand-made Ozone package uses a draft format and can't be read by the contract, so a real diagnose run on Ozone waits on Plan 5. |
| 2026-11-13 | 4, 6 | The catalog and operational tables are plain dynamodb.Table (AWS::DynamoDB::Table), not TableV2, because TableV2 synthesises a GlobalTable and bulk put items does not support global tables. Plan 6 adds the vector index through the catalog tables' CfnTable (vectorIndexes). |
| 2026-11-13 | 4, 7 | An archived version lives at `<open\|restricted>/<datasetId>/<version>/` with `checksums.sha256` at its root. Every object is written in one PUT with a full-object SHA-256 checksum, which the weekly integrity check compares. Open files are served at `/data/<datasetId>/<version>/<path>` on the CloudFront domain. A metadata edit that rewrites `datapackage.json` or `README.md` in place must rewrite `checksums.sha256` too, or the weekly check alerts. Changing a dataset's access level moves it between `open/` and `restricted/`, so its `/data` URL changes; Plan 7 owns both. |
| 2026-11-13 | 4, 6, 9 | The API lives under `/api/*` on the CloudFront domain. Two Cognito app clients use code with PKCE and no secret: `web` (callback `/auth/callback`) and `cli` (callback `http://localhost:8765/callback`, which Plan 6 may change when it designs the CLI and MCP sign-in). Roles are the Cognito groups `contributor`, `curator` and `admin`. |
| 2026-11-13 | 4, 7 | The site's CloudFront Function sends extensionless paths to `/index.html`; Plan 7 changes it when it writes per-dataset pages. |
| 2026-11-13 | 4, 6, 7 | Catalog items, Plan 4's first cut (Plan 6 may add attributes). Dataset: `PK=DATASET#<id>`, `SK=META`, `id`, `title`, `access` (from `archive:access`, default `open`), `currentVersion` (number, the highest version), `prefix` (`open` or `restricted`, of the current version); with `archive:project` also `project`, `GSI1PK=PROJECT#<project>` and `GSI1SK=DATASET#<id>`. Version: `PK=DATASET#<id>`, `SK=V#<version zero-padded to 6>`, `version` (number), `prefix`, `manifest` (the `datapackage.json` text). File: `PK=DATASET#<id>`, `SK=V#<version padded>#FILE#<path>`, `path`, `name` (the resource name), and `format`, `bytes` (number) and `hash` when present; one item per resource path and per `archive:files` member. |
| 2026-11-13 | 4, 7 | Reindex loads datasets, versions and files from the archive bucket's manifests only. Projects join the catalog once Plan 7 decides where project records live in the archive bucket. |
| 2026-11-13 | 4, 7, 10a | `pythonFunction` takes `durableConfig`. A durable function is invoked through its `live` alias, never unqualified; the reindex's alias ARN is the stack output `ReindexFunction`. `ARCHIVE_CONFIG` points the default CDK app at another config file, so a test stage needs no edit to `archive.yaml`. |
| 2026-11-13 | 4, 6, 7, 10a | Found on Plan 4's test deploy: `StartBulkPutItems` returns the operation ARN inside `BulkOperationDescription`, as `DescribeBulkOperation` does; a bulk operation's ARN is account-scoped (`arn:aws:dynamodb:<region>:<account>:bulk-operation/<id>`), so `DescribeBulkOperation` is granted on that, not under the table; and `ListDurableExecutionsByFunction` refuses an alias, so durable executions are listed by the unqualified function name (invocation still goes through the `live` alias). |
| 2026-11-13 | 5, 10b | The FEMC contact and the bulk-export request move from Plan 5 to Plan 10b. Plan 5 makes no contact and hands 10b only the audit numbers. |
| 2026-11-13 | 5 | FEMC's EML quirks are handled by a FEMC converter in `examples/femc/` (a uv workspace package `femc`, beside FEMC's `archive.yaml`) that rewrites FEMC's records to standard EML and calls the unchanged `from_eml`; `archive_contract` and `cruise` are not changed for FEMC. |
| 2026-11-13 | 5, 10b | The practice corpus is ten datasets: the six in SOURCES.md (Ozone re-converted, since its hand-made package uses a draft format) plus Vegetation Class Raster, Mount Mansfield Quadrat Images, Development Related Projects with Threatened or Endangered Species (by request) and 1991 White clover clones (description only). |
| 2026-11-13 | 6, 7 | Plan 7 owns every endpoint under `/api/submissions` (create and upload links, submit, the queue, one submission's status and events, the curator's decision, and the review-policy setting `GET`/`PUT /api/submissions/policy`); Plan 6 owns every read of the catalog. Plan 7's publish calls Plan 6's catalog-file writer in archive-backend once it exists. |
| 2026-11-13 | 4, 6, 7 | Project records live at `projects/<projectId>/project.json` in the archive bucket. Plan 7's first plan doesn't create them. |
| 2026-11-13 | 4, 6, 7, 10a | The one way a Lambda reads the archive config: the CDK app writes the validated config as JSON to the standard SSM parameter `/research-archive/<stage>/archive-config` at synth (synth fails over 4 KB). |
| 2026-11-13 | 4, 7, 8 | The site's CloudFront Function sends `/datasets/<id>` and `/datasets/<id>/` to `/datasets/<id>/index.html` (the per-dataset page Plan 7 writes in the derived bucket's `site/`), and every other extensionless path to `/index.html`. |
| 2026-11-13 | 4, 7 | Plan 7 changes the staging bucket's lifecycle so only `incoming/` expires after 30 days; a package that passes the checks is held at `held/<submissionId>/` until publish or reject, and findings reports stay at `reports/<submissionId>/<round>.json`. GuardDuty Malware Protection scans `incoming/`. |
| 2026-11-13 | 3, 7 | archive-backend depends on cruise (and so DuckDB); a packaging test keeps the shared unzipped Lambda asset under 250 MB. |
| 2026-11-13 | 6, 7, 8, 9 | Search runs on the server, not in the browser: `GET /api/search` (no sign-in) filters `catalog.json` held in the API Lambda's memory, taking `q`, `access`, `license`, `format`, `project` (each repeatable), `from`, `to`, `bbox` (`west,south,east,north`), `page` and `size` (default 20, at most 100), and answers one page of rows, the total and a count per value of `access`, `license`, `format` and `project`. No DuckDB on the search page. This replaces "The browser uses DuckDB on it" for search; Plan 8 may still use DuckDB-Wasm to preview a dataset's files. PLAN3 adds semantic ranking to the same endpoint. |
| 2026-11-13 | 6, 7, 8 | The catalog file is `catalog.json` in the derived bucket's `site/` (public at `/catalog.json`), written only by `archive_backend.catalog_file.write_catalog_file(table_name, derived_bucket)`, which builds it from the active catalog table. The reindex calls it after the flip; Plan 7's publish calls it after writing the catalog items. One row per published dataset at every access level: `id`, `version`, `title`, `description`, `keywords`, `access`, `licenses` (ids), `rightsStatus`, `project`, `creators`, `formats`, `start`, `end`, `ongoing`, `bbox`, `bytes`, `published`. Search rows carry the same fields. Theme and species join with Plan 2's PARK5 and PARK6. |
| 2026-11-13 | 6, 8, 9 | Read routes, no sign-in: `GET /api/datasets/{id}`, `/api/datasets/{id}/versions`, `/api/datasets/{id}/versions/{version}` (from the active catalog table) and `GET /api/projects/{id}` (from `projects/<id>/project.json` plus GSI1). Restricted files: `GET /api/datasets/{id}/versions/{version}/download?path=` (signed in) returns a five-minute presigned link, only for paths in that version's file items; anyone signed in may read restricted data; by-request answers 403 until Plan 7's grants exist. The OpenAPI spec is generated by Powertools from the one API Lambda, committed, and drift-checked in CI; Plan 8 generates its types from it. |
| 2026-11-13 | 6, 9 | CLI and MCP sign-in: authorization code with PKCE through the `cli` app client, managed login in the browser, callback `http://localhost:8765/callback` (unchanged). The client keeps the one-hour access and ID tokens and discards the refresh token. Plan 9 builds the client. |
| 2026-11-13 | 6, 8 | DownloadCounts holds `open` (daily rollup of CloudFront `GET /data/...` answering 200; 206 range reads and HEAD not counted) and `restricted` (links issued) per dataset and month; the Settings item `downloads-rolled-up-through` marks the last day counted. An optional usage form, `POST /api/datasets/{id}/usage` (no sign-in, no personal data), stores organisation kind, purpose and a short note in Plan 6's UsageResponses table; admins read them at `GET /api/admin/usage?dataset=`. |
| 2026-11-13 | 2, 6, 7 | `archive:published` (Manifest.published, ISO 8601 UTC) is the time a version was published, written only by Plan 7's publish step; the catalog's `publishedAt` and the exports' publication year come from it, so reindex and publish agree. The review policy is `ReviewPolicy` in archive_contract, stored as the Settings item `review-policy`. |
| 2026-11-13 | 4, 6, 7, 8, 9, 10a | Accounts are by invitation only: the user pool has self-service sign-up off, and an admin invites a person by email with `just invite-user <stage> <email> [group]` (Cognito sends a temporary password). Restricted data therefore reaches only people the archive invited, until by-request access exists. |
| 2026-11-14 | 7, 8, 10a | Plan 8 owns the dataset page template (`archive_backend.pages.render_page`); Plan 7's publish writes the pages. The template wraps its readable content in `<div id="app">` and loads the web app with one `<script type="module" src="/app.js">`, a stable loader served no-cache that loads the current hashed bundle, so an app release never rewrites pages. The page stays readable with no JavaScript (title, citation, file links and schema.org JSON-LD stay in the HTML), and manifest text stays escaped. |
| 2026-11-14 | 4, 7, 8, 10a | The reindex rewrites every dataset page: after it flips the active catalog table and writes `catalog.json`, it calls `render_page` then `write_page` for each dataset from the catalog items, as its own step. Web pages are rebuildable by `just reindex`, and a template change reaches every published page that way (Plan 10a's rebuild step after a deploy). |
| 2026-11-14 | 4, 8, 9, 10a | One CDK BucketDeployment, pruning off, writes the web app into the derived bucket's `site/` (`index.html` and `/app.js` no-cache, hashed `assets/` cached a year) and `/auth-config.json` with `Source.jsonData` from the construct's values: `region`, `cognitoDomain`, `webClientId`, `cliClientId`, no-cache. Plan 9 and the web app only read it. Nothing else deploys into `site/`; `catalog.json` and `datasets/` are written by the backend. |
| 2026-11-14 | 9, 10a | Browser sign-in lives in `archive-client` (`packages/client`, import `archive_client`, standard library only): `archive_client.signin` has `AuthConfig` (`region`, `cognito_domain`, `cli_client_id`), `Tokens` (`access_token`, `id_token`, `expires_at`; no refresh token) and `sign_in(config) -> Tokens` (PKCE through the `cli` client, one-shot listener on `localhost:8765`). Whichever of Plans 10a and 9 builds first builds it to this shape; Plan 9 adds `AuthConfig.from_archive(url)`, which reads `/auth-config.json`. cruise and archive_contract gain no network code. |
| 2026-11-14 | 9 | The MCP server runs only on the user's machine (stdio), in `packages/agent` (`archive-agent`, command `archive-mcp`), which is also the Claude Code plugin; the repo root's `.claude-plugin/marketplace.json` lists it. Its review skill reads a submission's files through Plan 7's curator route `GET /api/submissions/{id}/files`. |
| 2026-11-14 | 6, 7, 10a | `just invite-user <stage> <email> [groups]` takes a comma-separated group list; the deployment skill invites the first admin as `admin,curator,contributor`, since creating a submission needs contributor and deciding needs curator. |
| 2026-11-14 | 10a | CI is the only thing that deploys an archive stack: a deploy job on push to `main` deploys the stages in `archive.yaml` order, each in a GitHub environment named for the stage with `AWS_DEPLOY_ROLE_ARN`, and skips a stage with no role. The role comes from a separate `ResearchArchiveDeploy` stack (GitHub OIDC, trust pinned to the fork's environments, may only assume the CDK bootstrap roles). The deployment skill is `.claude/skills/deploy-archive/`; new recipes `just seed`, `just smoke` and `just destroy`. The seed goes through Plan 7's submit and publish and signs in with Plan 9's `archive_client.signin`. |
| 2026-11-14 | 6, 7 | Semantic search is the optional module `infrastructure.modules.embeddings` (`{}` turns it on; `model` is only `amazon.titan-embed-text-v2:0`). `archive_backend.embeddings.with_embedding(item, manifest, bedrock)` is the one way an embedding is set: it returns the DynamoDB-JSON dataset item with `embedding` (a list of 1,024 numbers from the title, description and keywords). The reindex calls it in its write step and Plan 7's publish calls it before its put, never as a later UpdateItem. |
| 2026-11-14 | 5, 7, 9 | `archive_contract.write_checksums(root)` is the one writer of `checksums.sha256`: a `<sha256>  <path>` line for every path `package_files(root)` lists (so not `_build/`) except `checksums.sha256` itself, sorted, written to a temporary name and moved into place. Its text comes from `checksums_text(root, replaced)`, which a writer that builds every file before writing any (Plan 9's `edit_manifest`) uses directly; the contract's tests use `write_checksums`; the FEMC converter's `_write_checksums` and Plan 7's publish move to it when next touched (PARK6). |
