<!-- Written by diazo from decisions.json, spec.md and the plans; diazo rewrites it, so edit those instead. -->

# Repo layout and conventions (Plan 1)

`research-archive-in-a-box/repo-layout-and-conventions` · repo `research-archive-in-a-box`

✓ Start → ✓ Understanding → ✓ Decisions → ✓ Spec → ✓ Plans → **Build · 0 of 6** → Sign off

PLAN1 building · 0 of 6 done

Running: Task 1: Initialise the repo and root files (PLAN1)

## What was asked

> let's review this and start our diazo planning sessions
> 
> (Brief for this session, from docs/planning-handoff.md, Plan 1 starter prompt:) Read `docs/planning-handoff.md`. Plan the repo layout and conventions for the research archive in a box (Plan 1). The stack is decided: Python for the contract, local tool and backend, TypeScript CDK, and a React with Vite web app. Work through the open questions with me one at a time, with options and trade-offs for each. Do not design features.

## Decisions

- **DCSN1 Kit name.** What is the kit called: the repo, the docs title, and the prefix for its contract package and CDK construct? The user chose A: research-archive-in-a-box (descriptive).
- **DCSN2 How cruise is installed.** The tool is `cruise`. Do we publish it to PyPI, or do people install it straight from the repo? The user chose A: Not on PyPI: install from the repo with uv.
- **DCSN3 Standalone app.** Is a Python install enough for the local tool, or do we also ship a standalone app for people without Python? The user chose A: Python packages only (pip, pipx or uv).
- **AGNT1 GitHub Actions for CI.** GitHub Actions. The repo is on GitHub, adopters fork it there, and deploys reach AWS with GitHub OIDC (no stored keys). The user kept it.
- **AGNT2 Folder layout.** `packages/contract`, `packages/tool`, `packages/backend` (Python, uv workspace); `packages/infra` (CDK construct plus default app) and `packages/web` (React and Vite) (npm workspace); `agent/` (plugin, MCP server, skills); `examples/` (the sample package and an example archive config); `docs/`; `.github/workflows/`. Root holds `pyproject.toml`, `package.json`, `justfile`, `LICENSE`. The user kept it.
- **AGNT3 Python tooling.** uv for packages, the lock and the workspace; ruff for lint and format; mypy in strict mode with the Pydantic plugin; pytest. Wheels built with hatchling. requires-python >=3.12 for every package; the backend runs on the newest Lambda Python runtime CDK offers. The user kept it.
- **AGNT4 TypeScript tooling.** npm workspaces, TypeScript strict, ESLint (flat config), Prettier, Vitest for both the web app and the CDK construct tests. The user kept it.
- **AGNT5 One task runner.** A root `justfile`: `just check` runs every lint, type check and test across Python and TypeScript, and CI runs exactly `just check`, path-filtered into Python and TypeScript jobs. The user kept it.
- **AGNT6 Schema drift check.** The schema generated from the contract is committed under `packages/web/`, and `just check` regenerates it and fails when the committed copy differs. The user kept it.
- **AGNT7 Versioning and releases.** One SemVer version for the whole repo, starting at 0.1.0. A `vX.Y.Z` tag makes a GitHub release with generated notes. Nothing is published to PyPI or npm; people install `cruise` from a tag with uv, and adopters deploy from their fork. The user kept it.
- **AGNT9 Contract as its own package.** Yes: `archive-contract` (import `archive_contract`) is its own package in the uv workspace, and `cruise` and the backend depend on it through workspace sources. It isn't published anywhere. The user kept it.
- **AGNT10 Local folder keeps its name.** No. The GitHub repo is `research-in-a-box`, and the local folder stays `research-archive-in-a-box` for now, because both planning folders (this one and Plan 2's) and their running sessions are recorded by that path. The user kept it.
- **PRIN1** FEMC is an example, not the source: nothing in the layout, names or tooling is modelled on FEMC's records.

## Spec

- [Goal](spec.md#goal): rests on the understanding
- [One repo](spec.md#one-repo): rests on AGNT2, DCSN1
- [Folder layout](spec.md#folder-layout): rests on AGNT2
- [Names](spec.md#names): rests on DCSN1, DCSN2
- [Installing cruise](spec.md#installing-cruise): rests on DCSN2, DCSN3, AGNT9
- [Python tooling](spec.md#python-tooling): rests on AGNT3, AGNT9
- [TypeScript tooling](spec.md#typescript-tooling): rests on AGNT4
- [One check command and CI](spec.md#one-check-command-and-ci): rests on AGNT1, AGNT5
- [Schema drift](spec.md#schema-drift): rests on AGNT6
- [Versioning and releases](spec.md#versioning-and-releases): rests on AGNT7, DCSN2
- [Risk and cost](spec.md#risk-and-cost): rests on AGNT1, DCSN1
- [Left out](spec.md#left-out): rests on DCSN2, DCSN3
- [How we'll know it works](spec.md#how-well-know-it-works): rests on AGNT5, AGNT6, DCSN2

## Plans

- [PLAN1](plans/1-empty-skeleton.md) An empty, passing skeleton of research-in-a-box: building · 0 of 6 done
  - TASK1 Task 1: Initialise the repo and root files: building
  - TASK2 Task 2: Python workspace with three empty packages: not started
  - TASK3 Task 3: TypeScript workspace with the empty construct and web app: not started
  - TASK4 Task 4: Schema generator and drift check: not started
  - TASK5 Task 5: justfile, CI and release workflows: not started
  - TASK6 Task 6: Publish to GitHub and confirm CI and the install: waiting on STEP1

## Steps

- STEP1 Go to create the public GitHub repo schuettc/research-in-a-box and push the skeleton: needs the user
  Answers: Go: The agent creates the public repo and pushes main · No go: Something shouldn't be public yet (hands it back)

## Files

| File | Written by | What it is |
|---|---|---|
| `README.md` | diazo | This summary: where it stands, what each file is, every decision and its answer. |
| `record.html` | diazo | The whole record as one page that works offline. |
| `decisions.json` | diazo | The full record, every thread. Names its schema. |
| `spec.md` | the agent, header by diazo | The spec. |
| `plans/` | the agent, header by diazo | One file per plan. |
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
