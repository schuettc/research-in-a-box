---
diazo: research-archive-in-a-box/agent-layer-mcp-and-skills
file: PLAN1
status: building
approved: 2026-11-14T00:52:45-06:00
hash: 9fed236c26df8e47239a0235556d011d0184a7950faed071823eba0af37dee86
rests_on: [AGNT1, AGNT10, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, AGNT8, AGNT9, DCSN1, DCSN2, DCSN3]
record: README.md
---

# PLAN1: The MCP server, the plugin and three skills

## Spec

`docs/specs/2026-11-13-agent-layer-mcp-and-skills/spec.md`, approved. All of it: the three skills, the eleven tools, `edit_manifest`, sign-in through `archive-client`, plain errors with no queue, and the plugin's layout and install.

## The change

Two new uv workspace packages and a plugin:

- `packages/client` (`archive-client`, import `archive_client`, standard library only): `archive_client.signin` with `AuthConfig`, `Tokens`, `sign_in(config)` and `AuthConfig.from_archive(url)`, as the Decision log row of 2026-11-14 for Plans 9 and 10a says. If Plan 10a has already built `sign_in`, this plan adds only `from_archive`.
- `packages/agent` (`archive-agent`, import `archive_agent`, command `archive-mcp`): a stdio MCP server on the official `mcp` Python SDK (FastMCP), depending on `archive-contract`, `cruise` and `archive-client`. It holds the eleven tools, an HTTP client for the archive that turns every failure into one of the spec's plain errors, and the saved archive URL in `~/.config/research-in-a-box/archive.json`.
- `packages/agent` is also the plugin: `.claude-plugin/plugin.json`, `.mcp.json` (starts `archive-mcp` with `uvx` from the git repo's `packages/agent`) and `skills/find-data/SKILL.md`, `skills/submit-dataset/SKILL.md`, `skills/review-submission/SKILL.md`. A `.claude-plugin/marketplace.json` at the repo root lists it.
- Two small changes to the contract: its readme export makes its citation builder public (`archive_contract.exports.readme.citation`), so `get_dataset` returns the same citation the README shows; and a new `archive_contract.write_checksums(root)` becomes the one checksum writer, used by `edit_manifest` (the FEMC converter and Plan 7's publish move to it when next touched, follow-up PARK6).

Both packages join the root `pyproject.toml`'s workspace members, so `just check-python` covers them (ruff, mypy strict, pytest). No infrastructure and no backend change: every route the tools call is built by Plans 6, 7 and 8.

## Left out

- Everything in the spec's Left out: prepare from a raw folder, audit and backfill, rescue data, the GitHub Action, a remote MCP endpoint, a retry queue, tokens on disk, more than one archive.
- `/auth-config.json` itself (Plan 8 writes it) and `GET /api/submissions/{id}/files` (Plan 7 adds it).
- Tests against a live archive in CI: the walk in Task 7 is the live check.

## Where

- `pyproject.toml` (workspace members)
- `packages/client/` (new)
- `packages/agent/` (new): `src/archive_agent/`, `tests/`, `skills/`, `.claude-plugin/plugin.json`, `.mcp.json`
- `.claude-plugin/marketplace.json` (new)
- `packages/contract/src/archive_contract/exports/readme.py` (citation made public)
- `packages/contract/src/archive_contract/checksums.py` (new, `write_checksums`)
- `docs/planning-handoff.md` (a Decision log row for `write_checksums`)
- `README.md` (an "Use it from Claude Code" section)

### Task 1: The shared sign-in package

**Does:** Creates `packages/client` (`archive-client`) with `archive_client.signin`: `AuthConfig` (`region`, `cognito_domain`, `cli_client_id`), `Tokens` (`access_token`, `id_token`, `expires_at`, no refresh token), `sign_in(config, *, open_browser=webbrowser.open) -> Tokens` and `AuthConfig.from_archive(url)`, which reads `<url>/auth-config.json` (`region`, `cognitoDomain`, `cliClientId`). `sign_in` uses PKCE (S256) with a random `state`, opens `https://<cognito_domain>/oauth2/authorize`, waits on a one-shot listener at `http://localhost:8765/callback` (timeout five minutes), exchanges the code at `/oauth2/token` and drops the refresh token. It raises `SignInError` on a state mismatch, an error callback, a refused exchange or the timeout. If Plan 10a has already built `sign_in` to this shape, this task adds only `from_archive` and its test.
**Files:** `pyproject.toml`, `packages/client/pyproject.toml`, `packages/client/src/archive_client/__init__.py`, `packages/client/src/archive_client/signin.py`, `packages/client/src/archive_client/py.typed`, `packages/client/tests/test_signin.py`
**Checks:** `uv run pytest packages/client`, `just check-python`
**Serves:** none (rests on calls AGNT4, AGNT6, AGNT9)

Tests drive `sign_in` with a fake `open_browser` that calls the local callback itself, and a local HTTP server standing in for the token endpoint: a good round trip, a state mismatch, an `error=` callback. `from_archive` is tested against a local server answering the four fields.

### Task 2: The server, the archive client and its errors

**Does:** Creates `packages/agent` (`archive-agent`, command `archive-mcp`) with the FastMCP server, the saved-archive file, the in-memory tokens, an HTTP client for the archive, and the first two tools. The client sends the access token when signed in and maps every failure to one error with a plain message: unreachable (connection or timeout), signed out or expired (no token, a token past `expires_at`, or a 401), not allowed (403, naming the group the route needs), conflict (409, with the archive's message) and refused (any other 4xx or 5xx, with the archive's message). `connect(url)` checks `<url>/auth-config.json` answers, then saves the URL; `sign_in()` runs `archive_client.sign_in` with `AuthConfig.from_archive` and answers the email and groups from the ID token. Any tool that needs the archive before `connect` answers that the archive isn't set and to call `connect`.
**Files:** `pyproject.toml`, `packages/agent/pyproject.toml`, `packages/agent/src/archive_agent/{__init__,server,archive,state,errors}.py`, `packages/agent/src/archive_agent/py.typed`, `packages/agent/tests/test_archive.py`, `packages/agent/tests/test_connect_sign_in.py`
**Checks:** `uv run pytest packages/agent`, `just check-python`
**Serves:** DCSN1, DCSN3 (rests on calls AGNT1, AGNT3, AGNT4)

The saved file's location comes from `XDG_CONFIG_HOME` when set, else `~/.config`, so tests point it at a temporary folder. HTTP is stubbed with a local server in the tests, one case per error.

### Task 3: Finding and fetching data

**Does:** Adds `search`, `get_dataset` and `download`. `search` passes the spec's filters to `GET /api/search` and answers its rows, total and facets. `get_dataset(id, version?)` answers the dataset, its manifest, its files and a citation from `archive_contract.exports.readme.citation` (made public in this task, its callers unchanged). `download(id, version, paths, to)` fetches open files from `<url>/data/<id>/<version>/<path>` and restricted ones through `GET /api/datasets/{id}/versions/{version}/download?path=`, writes each under `to` (refusing a path that would leave it), checks each file's SHA-256 against the version's file item when it has one, and answers what it wrote.
**Files:** `packages/agent/src/archive_agent/{read,server}.py`, `packages/contract/src/archive_contract/exports/readme.py`, `packages/agent/tests/test_read.py`
**Checks:** `uv run pytest packages/agent packages/contract`, `just check-python`
**Serves:** DCSN3 (rests on call AGNT8)

### Task 4: Diagnose and edit_manifest

**Does:** Adds `diagnose(folder)`, which calls `cruise.diagnose` in process (no profiles by default; the archive's profiles and required fields come later when the archive config is readable by clients) and answers its findings, score and verdict in the JSON shape `cruise diagnose --json` prints, and `edit_manifest(folder, edits)` as the spec describes: the allowed targets (package `title`, `description`, `keywords`, `licenses`, `archive:rightsStatus`, `archive:temporalCoverage`, `archive:spatialCoverage`, `archive:methods`, `contributors`; a column's `title`, `description` and `archive:unit` by resource and column name), every edit applied to the contract's `Manifest` and validated, nothing written if any edit fails, otherwise `datapackage.json` and `README.md` (from `render_readme`) written by temporary file and rename, then `checksums.sha256` rewritten by a new contract function, `archive_contract.write_checksums(root)`: a SHA-256 line for every path the contract's existing `package_files(root)` lists (which already leaves out `_build/`) except `checksums.sha256` itself, in the format `validate` reads (as the FEMC converter's `_write_checksums` does today), written by temporary file and rename. The contract's test helper of the same name is replaced by it, and a Decision log row records it as the one checksum writer.
**Files:** `packages/agent/src/archive_agent/{local,server}.py`, `packages/agent/tests/test_local.py`, `packages/contract/src/archive_contract/{checksums,__init__}.py`, `packages/contract/tests/test_checksums.py`, `packages/contract/tests/test_validate.py`, `docs/planning-handoff.md`
**Checks:** `uv run pytest packages/agent packages/contract`, `just check-python`
**Serves:** DCSN2 (rests on calls AGNT5, AGNT10)

`write_checksums` on an unchanged copy of the sample package reproduces its committed `checksums.sha256` byte for byte.

Tests copy `examples/sample-package` to a temporary folder: a column description and a license applied, `README.md` regenerated, `diagnose` showing no checksum finding afterwards; a list with one invalid edit (a target outside the list, a license with no name or path) leaving all three files byte for byte unchanged.

### Task 5: Submitting and reviewing

**Does:** Adds `submit`, `submissions`, `submission_files` and `decide` against Plan 7's routes, reading their request and answer shapes from `archive_backend.submissions` once Plan 7's PLAN1 is merged. `submit(folder, submission?)` runs `diagnose` and refuses on any error finding; reads `checksums.sha256`, lists those files plus `checksums.sha256` with sizes and SHA-256 values; with no `submission` calls `POST /api/submissions`, else `POST /api/submissions/{id}/uploads`; PUTs each file to its link with the SHA-256 checksum header S3 requires; then `POST /api/submissions/{id}/submit`; and answers the id and status. `submissions(id?, queue?)` reads `GET /api/submissions` (with `status` for the curator queue) or one with `GET /api/submissions/{id}`. `submission_files(id)` reads `GET /api/submissions/{id}/files` and, on 409, answers that the submission isn't in review. `decide(id, decision, note)` posts to `/decision`.
**Files:** `packages/agent/src/archive_agent/{submit,server}.py`, `packages/agent/tests/test_submit.py`
**Checks:** `uv run pytest packages/agent`, `just check-python`
**Serves:** DCSN3 (rests on call AGNT8)

Tests stub the routes and the presigned PUTs locally: `submit` refuses a package with an error finding; a clean package sends exactly the files in `checksums.sha256` plus that file, each with its checksum header; a next round uses `/uploads`; a 409 from `submission_files` gives the not-in-review message.

### Task 6: The plugin and the three skills

**Does:** Writes `skills/find-data/SKILL.md`, `skills/submit-dataset/SKILL.md` and `skills/review-submission/SKILL.md` with the spec's steps, each naming the tools in order and every point where the skill stops for the person's yes, and what to say on each plain error. Adds `.claude-plugin/plugin.json` and `.mcp.json` in `packages/agent`, `.claude-plugin/marketplace.json` at the repo root, and a short "Use it from Claude Code" section in `README.md` with the two install commands.
**Files:** `packages/agent/skills/*/SKILL.md`, `packages/agent/.claude-plugin/plugin.json`, `packages/agent/.mcp.json`, `.claude-plugin/marketplace.json`, `README.md`
**Checks:** `claude plugin validate .`, `uv run archive-mcp --help`, `just check-python`
**Serves:** DCSN1, DCSN2 (rests on calls AGNT2, AGNT7)

### Task 7: One walk on a test stage

**Does:** On a deployed test stage that has Plan 7's build with its curator files route and Plan 8's site deployment, with two invited accounts (contributor and curator), installs the plugin from the branch and walks the spec's last check from Claude Code: connect, sign in, find and fetch a published dataset, download an open file and a restricted one; diagnose a copy of the sample package, approve two drafted fixes, submit it and see it reach review; as a curator read it, see the summary, approve it, and see it at `/datasets/<id>`. Fixes found on the walk become tasks of their own.
**Files:** none expected
**Checks:** the walk, recorded in the task's result
**Serves:** DCSN1, DCSN2, DCSN3
