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

# Print the stage names of archive.yaml (or ARCHIVE_CONFIG) as a JSON list, in file order
stages:
    #!/usr/bin/env bash
    set -euo pipefail
    uv run --frozen python - "${ARCHIVE_CONFIG:-archive.yaml}" <<'EOF'
    import json, sys
    from pathlib import Path
    from archive_contract.config import load_config
    config = load_config(Path(sys.argv[1]))
    if config.infrastructure is None:
        sys.exit(f"{sys.argv[1]} needs an infrastructure section")
    print(json.dumps([stage.name for stage in config.infrastructure.stages]))
    EOF

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

# Print a stage's region or account from archive.yaml (or ARCHIVE_CONFIG), empty when it names none
_stage-field stage field:
    #!/usr/bin/env bash
    set -euo pipefail
    uv run --all-packages --frozen python - "${ARCHIVE_CONFIG:-archive.yaml}" "{{stage}}" "{{field}}" <<'EOF'
    import sys
    from pathlib import Path
    from archive_contract.config import load_config
    path, name, field = sys.argv[1:]
    infrastructure = load_config(Path(path)).infrastructure
    stages = {stage.name: stage for stage in infrastructure.stages} if infrastructure else {}
    if name not in stages:
        sys.exit(f"stage {name} is not in {path}")
    print(getattr(stages[name], field) or "")
    EOF

# Invite a person to the stage by email, optionally into groups: a comma-separated list of contributor, curator and admin
invite-user stage email groups="":
    #!/usr/bin/env bash
    set -euo pipefail
    region="$({{just_executable()}} _stage-field "{{stage}}" region)"
    aws() { command aws ${region:+--region "$region"} "$@"; }
    pool="$(aws cloudformation describe-stack-resources --stack-name "ResearchArchive-{{stage}}" \
        --query "StackResources[?ResourceType=='AWS::Cognito::UserPool'].PhysicalResourceId" --output text)"
    aws cognito-idp admin-create-user --user-pool-id "$pool" --username "{{email}}" \
        --user-attributes Name=email,Value="{{email}}" Name=email_verified,Value=true \
        --desired-delivery-mediums EMAIL >/dev/null
    IFS=',' read -ra groups <<< "{{groups}}"
    for group in "${groups[@]}"; do
        group="${group// /}"
        [ -n "$group" ] || continue
        aws cognito-idp admin-add-user-to-group --user-pool-id "$pool" --username "{{email}}" --group-name "$group"
    done
    echo "invited {{email}} to {{stage}} {{groups}}"

# Check the stage's site with no sign-in: site, health, search, the sample dataset's page and a download.
# CI passes the domain from cdk deploy's outputs; with none, it is read from the stack.
smoke stage domain="":
    #!/usr/bin/env bash
    set -euo pipefail
    domain="{{domain}}"
    if [ -z "$domain" ]; then
        region="$({{just_executable()}} _stage-field "{{stage}}" region)"
        domain="$(aws ${region:+--region "$region"} cloudformation describe-stacks \
            --stack-name "ResearchArchive-{{stage}}" \
            --query "Stacks[0].Outputs[?OutputKey=='SiteDomain'].OutputValue" --output text)"
    fi
    if [ -z "$domain" ] || [ "$domain" = "None" ]; then
        echo "ResearchArchive-{{stage}} has no SiteDomain output"
        exit 1
    fi
    python3 scripts/smoke.py "$domain"

# Publish the sample package on the stage as its admin, signed in in the browser, and wait for it
seed stage:
    #!/usr/bin/env bash
    set -euo pipefail
    region="$({{just_executable()}} _stage-field "{{stage}}" region)"
    domain="$(aws ${region:+--region "$region"} cloudformation describe-stacks \
        --stack-name "ResearchArchive-{{stage}}" \
        --query "Stacks[0].Outputs[?OutputKey=='SiteDomain'].OutputValue" --output text)"
    if [ -z "$domain" ] || [ "$domain" = "None" ]; then
        echo "ResearchArchive-{{stage}} has no SiteDomain output"
        exit 1
    fi
    uv run --all-packages --frozen python scripts/seed.py "$domain"

# Delete the stage's stack and the log group CDK's S3 auto-delete helper leaves behind; run from a laptop, never CI
destroy stage:
    #!/usr/bin/env bash
    set -euo pipefail
    region="$({{just_executable()}} _stage-field "{{stage}}" region)"
    account="$({{just_executable()}} _stage-field "{{stage}}" account)"
    aws() { command aws ${region:+--region "$region"} "$@"; }
    if [ -n "$account" ]; then
        caller="$(aws sts get-caller-identity --query Account --output text)"
        if [ "$caller" != "$account" ]; then
            echo "{{stage}} is in account $account, but you are signed in to $caller; nothing destroyed"
            exit 1
        fi
    fi
    # A running ingest execution (a submission waiting for review) blocks deleting the ingest
    # function's version, and cdk destroy then fails after about ten minutes: stop them first.
    ingest="ResearchArchive-{{stage}}-Ingest"
    if executions="$(aws lambda list-durable-executions-by-function --function-name "$ingest" \
        --query "DurableExecutions[].[DurableExecutionArn,Status]" --output text 2>&1)"; then
        stopped=0
        for arn in $(awk '$2 == "RUNNING" { print $1 }' <<< "$executions"); do
            aws lambda stop-durable-execution --durable-execution-arn "$arn" >/dev/null
            stopped=$((stopped + 1))
        done
        echo "stopped $stopped running ingest execution(s)"
    elif ! grep -q "ResourceNotFoundException" <<< "$executions"; then
        echo "could not list $ingest's executions: $executions"
        exit 1
    fi
    (cd packages/infra && npx cdk destroy "ResearchArchive-{{stage}}" --force)
    prefix="/aws/lambda/ResearchArchive-{{stage}}-CustomS3AutoDeleteObjects"
    for group in $(aws logs describe-log-groups --log-group-name-prefix "$prefix" \
        --query "logGroups[].logGroupName" --output text); do
        aws logs delete-log-group --log-group-name "$group"
        echo "deleted log group $group"
    done
    if answer="$(aws cloudformation describe-stacks --stack-name "ResearchArchive-{{stage}}" 2>&1)"; then
        echo "ResearchArchive-{{stage}} still exists"
        exit 1
    fi
    if ! grep -q "does not exist" <<< "$answer"; then
        echo "could not confirm ResearchArchive-{{stage}} is gone: $answer"
        exit 1
    fi
    echo "ResearchArchive-{{stage}} is gone"

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
