schema_file := "packages/web/src/schema/archive-contract.schema.json"
config_type_file := "packages/infra/src/generated/archive-config.ts"
config_type_generator := "packages/infra/scripts/generate-config-type.ts"

# Run every check in both languages, plus the schema drift check
check: check-python check-ts check-schema

# Python: format check, lint, type check, tests
check-python:
    uv run ruff format --check
    uv run ruff check
    uv run mypy packages
    uv run pytest

# TypeScript: format check, lint, type check, tests, web build
check-ts: lambda-assets
    npx prettier --check .
    npx eslint .
    npm run typecheck --workspaces
    npm test --workspaces
    npm run build -w packages/web

# Install archive-backend and its locked dependencies as arm64 Lambda wheels, without Docker
lambda-assets:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    rm -rf packages/infra/assets/python
    uv export --package archive-backend --no-dev --no-hashes --frozen --no-emit-workspace -o "$tmp/requirements.txt"
    uv pip install --python-platform aarch64-manylinux2014 --python-version 3.13 --only-binary :all: --target packages/infra/assets/python -r "$tmp/requirements.txt"
    uv pip install --no-deps --python-version 3.13 --target packages/infra/assets/python packages/contract packages/backend

# Fail when the committed JSON Schema or the construct's config type differs from the contract
check-schema:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    uv run python -m archive_contract.schema "$tmp/schema.json"
    diff -u {{schema_file}} "$tmp/schema.json"
    npx tsx {{config_type_generator}} "$tmp/schema.json" "$tmp/archive-config.ts"
    diff -u {{config_type_file}} "$tmp/archive-config.ts"

# Rewrite the committed JSON Schema and the construct's config type from the contract
schema:
    uv run python -m archive_contract.schema {{schema_file}}
    npx tsx {{config_type_generator}} {{schema_file}} {{config_type_file}}

# Format Python and TypeScript in place
fmt:
    uv run ruff format
    uv run ruff check --fix
    npx prettier --write .
