---
diazo: research-archive-in-a-box/repo-layout-and-conventions
file: PLAN1
status: done
approved: 2026-11-13T00:11:59-06:00
hash: 38b1d89c9594cfeae1d2b21349379b6333922f4fd857267ea5743365a1b07ea0
rests_on: [AGNT1, AGNT10, AGNT2, AGNT3, AGNT4, AGNT5, AGNT6, AGNT7, AGNT9, DCSN1, DCSN2, DCSN3]
record: README.md
---

# PLAN1: An empty, passing skeleton of research-in-a-box

## Spec

`docs/specs/2026-11-12-repo-layout-and-conventions/spec.md`, approved 2026-11-12.

## The change

Turn the project folder into a git repo holding the approved layout: a uv workspace with three empty Python packages (`archive-contract`, `cruise`, backend), an npm workspace with an empty CDK construct and an empty Vite web app, a schema generator with its drift check, one `just check` that runs every check, and the CI and release workflows. Then push it to a new public GitHub repo, `schuettc/research-in-a-box`, and confirm CI passes and `cruise` installs from it.

Each package holds only enough code for its checks to be able to fail: `cruise --version` prints the version, the contract's schema generator writes an empty schema, and the construct synthesises an empty stack.

Risk: low. Everything is new files in a new repo. A mistake is undone by editing or deleting files; the one outward step, creating the public GitHub repo, waits on your Go (STEP1).

## Left out

- Any feature code: the contract models, the tool's commands, Lambdas, resources in the construct and screens in the web app.
- The sample package (Plan 2), deploy workflows and OIDC (Plan 10a).
- Publishing to PyPI or npm.
- Renaming the local folder (call AGNT10).
- Committing other plans' planning folders: each planning session commits its own.

## Where

The project folder `/Users/courtschuett/GitHub/personal/research-archive-in-a-box`, branch `main`. The repo doesn't exist yet, so tasks 1 to 5 commit straight to `main` locally, and task 6 makes the first push.

### Task 1: Initialise the repo and root files

**Does:** Runs `git init -b main`, then adds the root files: `LICENSE` (MIT, 2026, Court Schuett), a short `README.md` (what the kit is, the layout, how to install `cruise` with uv, `just check`), `.gitignore` (keeps `practice-data/`, adds `.venv/`, `node_modules/`, `dist/`, `cdk.out/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`), and `.editorconfig`. The first commit holds these files, `docs/planning-handoff.md` and this planning folder.
**Files:** `LICENSE`, `README.md`, `.gitignore`, `.editorconfig`, `docs/planning-handoff.md`, `docs/specs/2026-11-12-repo-layout-and-conventions/`
**Checks:** `git -C /Users/courtschuett/GitHub/personal/research-archive-in-a-box rev-parse --abbrev-ref HEAD` prints `main`; `git status --porcelain --ignored practice-data` shows it ignored (`!! practice-data/`).
**Serves:** DCSN1 (rests on calls AGNT2, AGNT10)

After the commit, send Plan 2's folder (`8da653f233f9`) a diazo_note saying the repo exists, so its session commits its own folder.

### Task 2: Python workspace with three empty packages

**Does:** Writes the root `pyproject.toml` as the uv workspace root (`members = ["packages/contract", "packages/tool", "packages/backend"]`, dev dependencies ruff, mypy, pytest, pydantic) with the ruff, mypy (strict, `plugins = ["pydantic.mypy"]`) and pytest settings. Adds the three packages, each with its own `pyproject.toml` (hatchling, `requires-python = ">=3.12"`) and `src/<import name>/`, listed below.
**Files:** `pyproject.toml`, `uv.lock`, `packages/contract/`, `packages/tool/`, `packages/backend/`
**Checks:** `uv sync --all-packages`; `uv run ruff format --check`; `uv run ruff check`; `uv run mypy packages`; `uv run pytest`; `uv run cruise --version` prints `cruise 0.1.0`.
**Serves:** DCSN2, DCSN3 (rests on calls AGNT3, AGNT9)

- `packages/contract`: `archive-contract`, import `archive_contract`, depends on pydantic, empty `__init__.py` with `__version__`.
- `packages/tool`: `cruise`, depends on `archive-contract` through `[tool.uv.sources] archive-contract = { workspace = true }`, script `cruise = "cruise.cli:main"`, where `main` handles `--version` with argparse and prints `cruise <version>`. One test: `tests/test_cli.py` runs `main(["--version"])` and checks the output.
- `packages/backend`: `archive-backend`, import `archive_backend`, depends on `archive-contract` through the workspace source, an empty package with no tests yet.

Commits `uv.lock`.

### Task 3: TypeScript workspace with the empty construct and web app

**Does:** Writes the root `package.json` (private, `"workspaces": ["packages/infra", "packages/web"]`), a shared `tsconfig.base.json` (strict), `eslint.config.js` (flat config with typescript-eslint and the React hooks rules for web) and `.prettierrc`, and adds the two packages listed below.
**Files:** `package.json`, `package-lock.json`, `tsconfig.base.json`, `eslint.config.js`, `.prettierrc`, `packages/infra/`, `packages/web/`
**Checks:** `npm ci`; `npx prettier --check .`; `npx eslint .`; `npm run typecheck --workspaces`; `npm test --workspaces`; `npm run build -w packages/web`.
**Serves:** none (rests on calls AGNT2, AGNT4)

- `packages/infra`: aws-cdk-lib and constructs; `src/research-archive.ts` exports an empty `ResearchArchive` construct; `bin/app.ts` is the default app with one stack that uses it and tags the app with `Repo` set to `schuettc/research-in-a-box`; `cdk.json`. One Vitest test synthesises the stack and checks the template has the `Repo` tag.
- `packages/web`: React and Vite in TypeScript, an `App` that renders the kit's title. One Vitest test (jsdom and Testing Library) renders `App` and finds the title.

Commits `package-lock.json`.

### Task 4: Schema generator and drift check

**Does:** Adds `archive_contract.schema` with a `main` that writes the JSON Schema of the contract's root model to a given path. In the skeleton the root model is an empty Pydantic model (`ArchiveContract`), which Plan 2 replaces. Writes `packages/web/src/schema/archive-contract.schema.json` and commits it. A test in `packages/contract/tests/` checks the generator output is valid JSON with a `title`.
**Files:** `packages/contract/src/archive_contract/schema.py`, `packages/contract/tests/test_schema.py`, `packages/web/src/schema/archive-contract.schema.json`
**Checks:** `uv run python -m archive_contract.schema /tmp/schema.json && diff /tmp/schema.json packages/web/src/schema/archive-contract.schema.json`; `uv run pytest packages/contract`.
**Serves:** none (rests on call AGNT6)

### Task 5: justfile, CI and release workflows

**Does:** Writes the root `justfile` with `check` (runs `check-python`, `check-ts` and `check-schema`), `check-python` (ruff format check, ruff check, mypy, pytest), `check-ts` (prettier check, eslint, typecheck, tests, web build), `check-schema` (regenerate to a temp file and `diff` against the committed one), `schema` (rewrite the committed one) and `fmt`. Writes `.github/workflows/ci.yml`: on push and pull request, a Python job (checkout, `astral-sh/setup-uv`, `extractions/setup-just`, `uv sync --all-packages --locked`, `just check-python check-schema`) and a TypeScript job (checkout, `actions/setup-node` with Node 24 and npm cache, setup-just, `npm ci`, `just check-ts`), each action pinned to a full commit SHA. Writes `.github/workflows/release.yml`: on a `v*` tag, `gh release create "$GITHUB_REF_NAME" --generate-notes` with `contents: write`.
**Files:** `justfile`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`
**Checks:** `just check` exits 0 on the clean tree; each of the six breakages makes `just check` exit non-zero, and `git status --porcelain` is empty after reverting them.
**Serves:** none (rests on calls AGNT1, AGNT5, AGNT6, AGNT7)

Then proves each check can fail, without committing the breakage: a ruff lint error, a mypy type error, a failing pytest, a Prettier violation, a failing Vitest test and a stale schema file each make `just check` exit non-zero; each is reverted after.

### Task 6: Publish to GitHub and confirm CI and the install

**Does:** Waits on your Go (STEP1), then creates the public repo with `gh repo create schuettc/research-in-a-box --public --source . --push`. Captures the new CI run's id for the pushed commit (not the latest run) and checks it: both jobs must pass. Then installs `cruise` from GitHub into a throwaway tool directory and runs it.
**Files:** none
**Checks:** `gh run view <id> --json conclusion` reports `success` for the run of the pushed SHA; `UV_TOOL_DIR=<tmp> UV_TOOL_BIN_DIR=<tmp>/bin uv tool install "git+https://github.com/schuettc/research-in-a-box#subdirectory=packages/tool"` exits 0 and `<tmp>/bin/cruise --version` prints `cruise 0.1.0`.
**Serves:** DCSN1, DCSN2 (rests on call AGNT1)
