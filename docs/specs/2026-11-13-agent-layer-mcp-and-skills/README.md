<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Agent layer (Plan 9)

`research-archive-in-a-box/agent-layer-mcp-and-skills` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → **Plans** → Build → Sign off

## Pick up next

- **PARK1 Prepare from a raw folder:** A prepare-dataset skill that turns a raw folder into a package with cruise inventory, profile, tidy and package. Waits on Plan 3's PARK3 and PARK4.
- **PARK2 Audit and backfill:** An audit-and-backfill skill that runs cruise audit over published datasets and proposes metadata fixes. Waits on Plan 7's in-place metadata edits (its PARK6).
- **PARK3 Rescue data:** A rescue-data skill for values read from scanned documents, including how each value's provenance (the page and region it came from) is recorded. The handoff's open question on provenance is settled with it, once a real scanned dataset arrives.
- **PARK4 GitHub Action:** A GitHub Action that runs cruise diagnose on push and publishes on release. Publishing needs a machine sign-in, since today's sign-in is a person in a browser.
- **PARK5 Remote MCP endpoint:** An MCP endpoint in the archive for clients that can't start a local process, when one is actually used.

## What was asked

> can we start all of the plans as planned so we don't forget them and have a way to track them with their own sessions
> 
> (Saved as planned: mark this plan Planned with diazo_update planned: true and wait for Start planning. Do no research until then. It waits on Plan 3, the quality rules and local tool, and Plan 6, the API and search.)
> 
> Brief: Plan 9 in docs/planning-handoff.md. Starter prompt from the handoff:
> 
> > Read `docs/planning-handoff.md`. Plan the agent layer (Plan 9): an MCP server, a Claude Code plugin and the skills for researchers and curators. Generative work happens only in the user's own Claude. Plan the tools first, then each skill's steps, and take the open questions with me one at a time.

## Decisions

- **DCSN1 Where the MCP server runs.** Where should the MCP server run: on the user's own machine, as a Lambda in the archive, or both? The user chose A: On the user's machine only.
- **DCSN2 Writing approved fixes.** When the person approves a fix Claude drafted, how does it get into datapackage.json? The user chose A: An edit tool that checks against the contract.
- **DCSN3 When the archive is unreachable.** What should the skills do when the archive can't be reached (no network, the archive down, or the sign-in expired)? The user chose A: Say so and keep the local work.
- **AGNT1 Where the code lives.** One folder, packages/agent: a uv workspace package archive-agent (import archive_agent, command archive-mcp) built on the official mcp Python SDK, depending on archive-contract and cruise; beside it skills/, .claude-plugin/plugin.json and .mcp.json, so packages/agent is the plugin. A .claude-plugin/marketplace.json at the repo root lists it. The user kept it.
- **AGNT2 Installing the plugin.** /plugin marketplace add schuettc/research-in-a-box, then install the plugin. Its .mcp.json starts the server with uvx from the git repo's packages/agent, the same way cruise installs today. The user kept it.
- **AGNT3 Choosing the archive.** A connect(url) tool saves the archive's URL to ~/.config/research-in-a-box/archive.json and reads its /auth-config.json. The skills ask for the URL the first time. The user kept it.
- **AGNT4 Tokens in memory.** In the MCP server's memory only. Restarting Claude Code, or an hour passing, means signing in again. The user kept it.
- **AGNT5 Diagnose as a library.** The diagnose tool calls cruise.diagnose in the MCP server's process and returns its findings, score and verdict as JSON. The user kept it.
- **AGNT6 The auth config file.** Plan 8 writes /auth-config.json in its site deployment (region, cognitoDomain, webClientId, cliClientId, no-cache); Plan 9 only reads it, with AuthConfig.from_archive(url) in archive-client. Plan 9's live test waits on that deployment. The user kept it.
- **AGNT7 Three skills.** find-data, submit-dataset and review-submission. Each skill's steps are written in the spec. The user kept it.
- **AGNT8 The tool list.** connect, sign_in, search, get_dataset, download, diagnose, edit_manifest (with DCSN2 A), submit, submissions (your list, the queue, or one with its findings and events), submission_files and decide. Each maps to one built route or to cruise. submission_files reads Plan 7's curator route GET /api/submissions/{id}/files (five-minute links to the current round's held files), which Plan 7 adds after its PLAN1 merges; it answers only while a submission is in-review or publishing (409 otherwise), so the review skill reads files only for submissions in review and reports a 409 as not in review. The user kept it.
- **AGNT9 Shared sign-in module.** A small uv workspace package, packages/client (archive-client, import archive_client), standard library only. archive_client.signin has AuthConfig (region, cognito_domain, cli_client_id), Tokens (access_token, id_token, expires_at; no refresh token) and sign_in(config) -> Tokens, which Plan 10a builds first. Plan 9 adds AuthConfig.from_archive(url) reading /auth-config.json, and its MCP server imports the package. The user kept it.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [The three skills](spec.md#the-three-skills): rests on DCSN2, AGNT7, AGNT8
- [The MCP server and its tools](spec.md#the-mcp-server-and-its-tools): rests on DCSN1, DCSN3, AGNT3, AGNT5, AGNT8
- [Writing approved fixes](spec.md#writing-approved-fixes): rests on DCSN2
- [Sign-in and the archive](spec.md#sign-in-and-the-archive): rests on AGNT3, AGNT4, AGNT6, AGNT9
- [When the archive is unreachable](spec.md#when-the-archive-is-unreachable): rests on DCSN3
- [Where it lives and how it installs](spec.md#where-it-lives-and-how-it-installs): rests on DCSN1, AGNT1, AGNT2
- [Risk and cost](spec.md#risk-and-cost): rests on DCSN1, DCSN2
- [Left out](spec.md#left-out): rests on DCSN1, DCSN3, AGNT4
- [How we'll know it works](spec.md#how-well-know-it-works): rests on DCSN1, DCSN2, DCSN3, AGNT2, AGNT8

## Plans

None yet.

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `mockups/` | the agent and the user | Mockups (HTML) and the agent's pictures; the user's screenshots from before screenshots/. |
| `diagrams/` | diazo | The drawn picture (SVG) of each mermaid diagram in the folder. |

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
