---
diazo: research-archive-in-a-box/agent-layer-mcp-and-skills
file: spec
status: approved
approved: 2026-11-14T00:50:08-06:00
hash: c7d973930e8c72872b75e64b65ebf73398839030fd3d1458d83a6c96ba375b40
rests_on: [DCSN2, AGNT7, AGNT8, DCSN1, DCSN3, AGNT3, AGNT5, AGNT4, AGNT6, AGNT9, AGNT1, AGNT2]
record: README.md
---

# Agent layer: an MCP server, a plugin and three skills

## Goal

Someone using Claude Code can find and use data, submit a dataset, and review a submission without the web app. A Claude Code plugin bundles a local MCP server with three skills: `find-data`, `submit-dataset` and `review-submission`. The checks are the same `cruise` code the archive's ingest runs. Claude drafts and summarises in the user's own session, and nothing is written into a manifest or sent to the archive until the person says yes. It builds on what Plans 1 to 8 built and rebuilds none of it. Preparing a package from a raw folder, audit and backfill, rescue data and the GitHub Action come later.

## The three skills

Each skill is a `SKILL.md` in the plugin. It tells Claude which tools to call in which order, and where it must stop for the person's yes.

**find-data** (anyone, no sign-in for open data).

1. Ask what the person is looking for, then `search` with the words and any filters they give (access, license, format, project, dates, a bounding box).
2. Show the matching datasets as a short list: title, years, license, access.
3. For the one they pick, `get_dataset` and show its description, its columns with their descriptions and units, its license and a citation built from the manifest.
4. On request, `download` the files they name into a folder they name. A restricted file needs `sign_in` first, and the skill says so before opening the browser.

**submit-dataset** (a member of the `contributor` group).

1. Ask for the package folder and `diagnose` it. Show the verdict, the score and the findings grouped by question, errors first.
2. For each finding Claude can help with (a missing description, license, coverage, methods or unit), draft the text from what the folder holds (its docs, its column names and values) and show each draft beside the finding. Never invent a fact the folder doesn't support: where it is silent, ask the person.
3. Apply only the drafts the person approves, with `edit_manifest`, then `diagnose` again and show what changed.
4. Repeat until no errors are left or the person stops. Warnings may remain; the skill lists them and says they don't block publishing.
5. With the person's yes, `sign_in` if needed, then `submit`. Show the submission id and its status.
6. On request later, `submissions` shows the status. When it is `needs-changes`, show the curator's note or the findings, go back to step 2, and `submit` the same submission again for its next round.

**review-submission** (a member of the `curator` group).

1. `sign_in`, then `submissions` with the queue, and show what waits in review, stale ones first.
2. For the one the curator picks, read it with `submissions` (status, findings, events) and `submission_files`, which gives short-lived links to its files, and read its `datapackage.json` and a sample of each table.
3. Summarise it: what the data is, how complete the metadata is, the warnings the rules raised, and the judgment calls no rule can make (a column that looks like a location id with no grid described, a license that doesn't fit the stated source, a description that contradicts the values). Each point cites the field, column or row it rests on.
4. Draft a decision and a note. Show both, and change them as the curator asks.
5. Only with the curator's yes, `decide`.

Rests on: DCSN2, AGNT7, AGNT8

## The MCP server and its tools

One Python MCP server, run on the user's own machine over stdio and started by Claude Code from the plugin. It holds the archive's URL on disk and the sign-in tokens in memory.

| Tool | What it does | Calls |
| --- | --- | --- |
| `connect(url)` | Saves the archive's URL and checks it answers | `GET /auth-config.json` |
| `sign_in()` | Opens the browser to sign in and returns who you are and your groups | Cognito managed login, PKCE |
| `search(...)` | One page of matching datasets with facet counts | `GET /api/search` |
| `get_dataset(id, version?)` | The dataset, its manifest, its files and a citation | `GET /api/datasets/{id}` and its versions |
| `download(id, version, paths, to)` | Writes files to a local folder and checks each against its hash | `/data/...` for open files, the download link route for restricted ones |
| `diagnose(folder)` | Findings, score and verdict as JSON | `cruise.diagnose`, in process |
| `edit_manifest(folder, edits)` | Applies approved edits through the contract (below) | the contract's models |
| `submit(folder, submission?)` | Creates a submission, or the next round of one, uploads every file and submits | `POST /api/submissions`, `/uploads`, `/submit` |
| `submissions(id?, queue?)` | Your submissions, the curator queue, or one submission with its findings and events | `GET /api/submissions` and `/{id}` |
| `submission_files(id)` | Short-lived links to a submission's current files, while it is in review | `GET /api/submissions/{id}/files` (Plan 7) |
| `decide(id, decision, note)` | Approve, reject or request changes | `POST /api/submissions/{id}/decision` |

`submit` runs `diagnose` first and refuses a package with an error finding, since the archive would send it straight back. It sends every file listed in `checksums.sha256` plus `checksums.sha256` itself, each with its size and SHA-256, so the archive's upload links accept it. A `submit` that fails part way leaves its draft in the archive, where Plan 7's lifecycle expires the uploads, and the next `submit` starts a fresh one.

`submission_files` answers only while a submission is in review or publishing; for any other state the archive answers 409, and the tool says the submission isn't in review.

Rests on: DCSN1, DCSN3, AGNT3, AGNT5, AGNT8

## Writing approved fixes

`edit_manifest(folder, edits)` takes a list of edits, each a target and a value. The targets are the metadata the findings ask for: the package's title, description, keywords, licenses, rights status, temporal and spatial coverage, methods and contributors, and a column's title, description and unit (named by resource and column). Resources, paths, column names, types and schemas are not editable through it, so an edit can't change what the data is.

The tool reads `datapackage.json` into the contract's `Manifest`, applies every edit, and validates the result. If any edit fails, it writes nothing and answers which edit failed and why. Otherwise it writes `datapackage.json`, regenerates `README.md` with the contract's readme export, and rewrites those two files' lines in `checksums.sha256`, so the package stays consistent and `diagnose` finds no stale checksum. Each file is written to a temporary name and moved into place.

Rests on: DCSN2

## Sign-in and the archive

The person names their archive once, with `connect`. The URL is saved in `~/.config/research-in-a-box/archive.json`. The skills ask for it the first time a tool needs it.

Sign-in follows the Decision log: authorization code with PKCE through the `cli` client, the browser opened to Cognito's managed login, a one-shot listener on `http://localhost:8765/callback`, and the one-hour access and ID tokens kept in the MCP server's memory, with the refresh token thrown away. Restarting Claude Code or an hour passing means signing in again.

The code lives in a small shared package, `archive-client` (`packages/client`, standard library only): `AuthConfig` (region, Cognito domain, `cli` client id), `Tokens` (access token, ID token, expiry) and `sign_in(config) -> Tokens`. Plan 10a may build `sign_in` first for its seed step; if it hasn't when this plan's build starts, this plan builds it to the same shape. This plan adds `AuthConfig.from_archive(url)`, which reads the archive's public `/auth-config.json` (fields `region`, `cognitoDomain`, `webClientId`, `cliClientId`). Plan 8 writes that file in its site deployment.

Rests on: AGNT3, AGNT4, AGNT6, AGNT9

## When the archive is unreachable

Every tool that calls the archive answers a plain error naming the cause: the archive can't be reached, you're signed out or your sign-in expired, you're not allowed (a 403, naming the group needed), or the archive refused the request (its message). The skill tells the person, keeps everything local (`diagnose` and `edit_manifest` need no network), and says what to run again. Nothing is queued.

Rests on: DCSN3

## Where it lives and how it installs

`packages/agent` is the plugin and the server together: a uv workspace package `archive-agent` (import `archive_agent`, command `archive-mcp`) on the official `mcp` Python SDK, depending on `archive-contract`, `cruise` and `archive-client`; beside it `skills/`, `.claude-plugin/plugin.json` and `.mcp.json`. A `.claude-plugin/marketplace.json` at the repo root lists the plugin. A person installs it with `/plugin marketplace add schuettc/research-in-a-box` and then the plugin; its `.mcp.json` starts the server with `uvx` from the git repo's `packages/agent`, the way `cruise` installs today. Nothing is published to PyPI or npm.

Rests on: DCSN1, AGNT1, AGNT2

## Risk and cost

**Risk.** A mistake in `edit_manifest` could damage a researcher's `datapackage.json`; every edit goes through the contract's models, nothing is written when one fails, and files are replaced whole, so the worst case is an edit the person approved, which they can edit again. A mistake in `submit` could send the wrong files; every submission still passes the archive's own checks and its review policy, so nothing is published unreviewed by this plan. A mistake in `decide` acts with a curator's authority; the skill sends a decision only after the curator's yes. Sign-in holds one-hour tokens in memory only. Checks are sized to this: unit tests for each tool with the archive's HTTP stubbed and for `edit_manifest` on the sample package, and one walk on a deployed test stage.

**Cost.** Your steps: a deployed test stage with Plan 7's build and its curator files route and Plan 8's site deployment, two invited accounts (one `contributor`, one `curator`; yours can be both), installing the plugin, and the walk. New programs: none (uv is already needed for `cruise`). New dependency: the `mcp` Python SDK.

Rests on: DCSN1, DCSN2

## Left out

- Preparing a package from a raw folder, waiting on `cruise` inventory, profile, tidy and package (PARK1).
- Audit and backfill of published datasets, waiting on in-place metadata edits (PARK2).
- Rescue data, and how provenance from scanned documents is recorded (PARK3).
- The GitHub Action, and the machine sign-in its publish step needs (PARK4).
- An MCP endpoint in the archive for clients that can't start a local process (PARK5).
- A queue that retries submissions or decisions later.
- Tokens on disk, and more than one archive per person.

Rests on: DCSN1, DCSN3, AGNT4

## How we'll know it works

- Unit tests pass for every tool, with the archive's HTTP calls stubbed: each tool's request, its answer, and each error cause (unreachable, signed out, 403, 409, a refusal).
- `edit_manifest` on a copy of the sample package applies a column description and a license, regenerates `README.md`, leaves `diagnose` with no checksum finding, and writes nothing when one edit in the list is invalid.
- `submit` refuses a package with an error finding, and otherwise sends exactly the files in `checksums.sha256` plus that file.
- The plugin installs from the repo with `/plugin marketplace add` and the server starts.
- On a deployed test stage, from Claude Code with the plugin: connect, sign in, find and fetch a published dataset, download an open file and a restricted one; diagnose a copy of the sample package, approve two drafted fixes, submit it and see it reach review; as a curator read it, see the summary, and approve it, ending published at `/datasets/<id>`.

Rests on: DCSN1, DCSN2, DCSN3, AGNT2, AGNT8
