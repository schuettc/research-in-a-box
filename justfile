schema_file := "packages/web/src/schema/archive-contract.schema.json"
config_type_file := "packages/infra/src/generated/archive-config.ts"
config_type_generator := "packages/infra/scripts/generate-config-type.ts"
openapi_file := "packages/web/src/schema/openapi.json"
web_types_dir := "packages/web/src/generated"

# Run every check in both languages, plus the schema drift check
check: check-python check-ts check-schema

# Python: format check, lint, type check, tests
check-python:
    uv run ruff format --check
    uv run ruff check
    uv run mypy packages examples/femc scripts
    uv run pytest

# TypeScript: format check, lint, type check, web build, tests (the infra tests synth the build)
check-ts: lambda-assets
    npx prettier --check .
    npx eslint .
    npm run typecheck --workspaces
    npm run build -w packages/web
    npm test --workspaces

# Start a reindex of the stage's catalog, with the caller's AWS_PROFILE and region
reindex stage:
    #!/usr/bin/env bash
    set -euo pipefail
    fn="$(aws cloudformation describe-stacks --stack-name "ResearchArchive-{{stage}}" \
        --query "Stacks[0].Outputs[?OutputKey=='ReindexFunction'].OutputValue" --output text)"
    aws lambda invoke --invocation-type Event --function-name "$fn" --payload '{}' \
        --cli-binary-format raw-in-base64-out /dev/null >/dev/null
    echo "reindex started on {{stage}}; follow it with just reindex-status {{stage}}"

# Show the status and result of the stage's latest reindex
reindex-status stage:
    #!/usr/bin/env bash
    set -euo pipefail
    fn="$(aws cloudformation describe-stacks --stack-name "ResearchArchive-{{stage}}" \
        --query "Stacks[0].Outputs[?OutputKey=='ReindexFunction'].OutputValue" --output text)"
    # Listing executions can't filter by alias, so list by the function's unqualified ARN.
    arn="$(aws lambda list-durable-executions-by-function --function-name "${fn%:live}" --max-items 1 \
        --query "DurableExecutions[0].DurableExecutionArn" --output text | head -n 1)"
    if [ -z "$arn" ] || [ "$arn" = "None" ]; then
        echo "no reindex has run on {{stage}}"
        exit 1
    fi
    aws lambda get-durable-execution --durable-execution-arn "$arn" \
        --query "{status: Status, result: Result}" --output json

# Invite a person to the stage by email, optionally into a group (contributor, curator or admin)
invite-user stage email group="":
    #!/usr/bin/env bash
    set -euo pipefail
    pool="$(aws cloudformation describe-stack-resources --stack-name "ResearchArchive-{{stage}}" \
        --query "StackResources[?ResourceType=='AWS::Cognito::UserPool'].PhysicalResourceId" --output text)"
    aws cognito-idp admin-create-user --user-pool-id "$pool" --username "{{email}}" \
        --user-attributes Name=email,Value="{{email}}" Name=email_verified,Value=true \
        --desired-delivery-mediums EMAIL >/dev/null
    if [ -n "{{group}}" ]; then
        aws cognito-idp admin-add-user-to-group --user-pool-id "$pool" --username "{{email}}" --group-name "{{group}}"
    fi
    echo "invited {{email}} to {{stage}} {{group}}"

# Subscribe a curator's email to the stage's curators' topic, for messages to their user id or to all
add-curator stage email userId:
    #!/usr/bin/env bash
    set -euo pipefail
    topic="$(aws cloudformation describe-stacks --stack-name "ResearchArchive-{{stage}}" \
        --query "Stacks[0].Outputs[?OutputKey=='CuratorTopic'].OutputValue" --output text)"
    attributes="$(jq -cn --arg user '{{userId}}' \
        '{FilterPolicy: ({audience: [$user, "all"]} | tojson)}')"
    aws sns subscribe --topic-arn "$topic" --protocol email --notification-endpoint '{{email}}' \
        --attributes "$attributes" --query SubscriptionArn --output text >/dev/null
    echo "{{email}} subscribed to the {{stage}} curators' topic; they must confirm from the email"

# Drive the sample package through the ingest pipeline on a deployed non-prod stage, with the
# caller's AWS_PROFILE and region. Set INGEST_E2E_REVIEWER to your curator user id to receive
# the reminder; the reminder run leaves one submission waiting, and the next day's run checks it.
ingest-e2e stage:
    uv run python scripts/ingest_e2e.py {{stage}}

# Install archive-backend, its workspace packages (the contract and cruise) and its locked
# dependencies as arm64 Lambda wheels, without Docker
lambda-assets:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    rm -rf packages/infra/assets/python
    uv export --package archive-backend --no-dev --no-hashes --frozen --no-emit-workspace -o "$tmp/requirements.txt"
    # manylinux_2_28: DuckDB ships no older aarch64 wheel; the python3.13 runtime (AL2023) has glibc 2.34.
    uv pip install --python-platform aarch64-manylinux_2_28 --python-version 3.13 --only-binary :all: --target packages/infra/assets/python -r "$tmp/requirements.txt"
    uv pip install --no-deps --python-version 3.13 --target packages/infra/assets/python packages/contract packages/tool packages/backend

# Fail when the committed JSON Schema, the construct's config type or the OpenAPI spec differs from the code
check-schema:
    #!/usr/bin/env bash
    set -euo pipefail
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    uv run python -m archive_contract.schema "$tmp/schema.json"
    diff -u {{schema_file}} "$tmp/schema.json"
    npx tsx {{config_type_generator}} "$tmp/schema.json" "$tmp/archive-config.ts"
    diff -u {{config_type_file}} "$tmp/archive-config.ts"
    uv run python -m archive_backend.api "$tmp/openapi.json"
    diff -u {{openapi_file}} "$tmp/openapi.json"
    just web-types "$tmp/web"
    diff -ru {{web_types_dir}} "$tmp/web"

# Rewrite the committed JSON Schema and the construct's config type from the contract
schema:
    uv run python -m archive_contract.schema {{schema_file}}
    npx tsx {{config_type_generator}} {{schema_file}} {{config_type_file}}

# Rewrite the committed OpenAPI spec from the read API's routes
openapi:
    uv run python -m archive_backend.api {{openapi_file}}

# Write the web app's API and manifest types from the committed OpenAPI spec and JSON Schema
web-types out=web_types_dir:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p "{{out}}"
    out="$(cd "{{out}}" && pwd)"
    root="$PWD"
    (cd packages/web && npx openapi-typescript "$root/{{openapi_file}}" -o "$out/api.ts" >/dev/null)
    npx json2ts -i {{schema_file}} -o "$out/manifest.ts" --no-format \
        --bannerComment="// Generated from the archive contract's JSON Schema by \`just web-types\`. Do not edit."
    npx prettier --config .prettierrc --write "$out/api.ts" "$out/manifest.ts" >/dev/null

# Format Python and TypeScript in place
fmt:
    uv run ruff format
    uv run ruff check --fix
    npx prettier --write .
