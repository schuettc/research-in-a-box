schema_file := "packages/web/src/schema/archive-contract.schema.json"

# Run every check in both languages, plus the schema drift check
check: check-python check-ts check-schema

# Python: format check, lint, type check, tests
check-python:
    uv run ruff format --check
    uv run ruff check
    uv run mypy packages
    uv run pytest

# TypeScript: format check, lint, type check, tests, web build
check-ts:
    npx prettier --check .
    npx eslint .
    npm run typecheck --workspaces
    npm test --workspaces
    npm run build -w packages/web

# Fail when the committed JSON Schema differs from the contract
check-schema:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp)"
    trap 'rm -f "$tmp"' EXIT
    uv run python -m archive_contract.schema "$tmp"
    diff -u {{schema_file}} "$tmp"

# Rewrite the committed JSON Schema from the contract
schema:
    uv run python -m archive_contract.schema {{schema_file}}

# Format Python and TypeScript in place
fmt:
    uv run ruff format
    uv run ruff check --fix
    npx prettier --write .
