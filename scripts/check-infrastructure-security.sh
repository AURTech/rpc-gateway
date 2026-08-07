#!/bin/sh

set -eu

fail() {
    printf 'infrastructure security contract failed: %s\n' "$1" >&2
    exit 1
}

require_match() {
    pattern=$1
    file=$2
    message=$3
    grep -Eq "$pattern" "$file" || fail "$message"
}

reject_match() {
    pattern=$1
    file=$2
    message=$3
    if grep -Eq "$pattern" "$file"; then
        fail "$message"
    fi
}

if git grep -IlP '\p{Han}' -- . >/dev/null; then
    fail 'tracked text files must use English and contain no Han characters'
fi

ci_workflow='.github/workflows/ci.yml'

require_match '^name: CI$' "$ci_workflow" 'the CI workflow must declare a name'
require_match '^  infra:$' "$ci_workflow" 'CI must define the infrastructure security job'
require_match '^  server:$' "$ci_workflow" 'CI must define the server verification job'
require_match '^  web:$' "$ci_workflow" 'CI must define the web check job'
require_match 'make verify' "$ci_workflow" 'server CI must run static verification'
require_match 'make build' "$ci_workflow" 'server CI must build the package'
require_match 'pnpm lint' "$ci_workflow" 'web CI must lint'
require_match 'pnpm format:check' "$ci_workflow" 'web CI must check formatting'
require_match 'pnpm typecheck' "$ci_workflow" 'web CI must type-check'
require_match 'pnpm build:worker' "$ci_workflow" 'web CI must build the Cloudflare Worker artifact'
reject_match 'make[[:space:]]+(test|ci|cov)|pytest' "$ci_workflow" 'CI must not run backend tests or coverage'
reject_match 'pnpm[[:space:]]+(run[[:space:]]+)?test|vitest|--coverage' "$ci_workflow" 'CI must not run frontend tests or coverage'
reject_match 'pnpm[[:space:]]+deploy:worker' "$ci_workflow" 'CI must not carry the production deployment job'
reject_match 'corepack[[:space:]]+prepare' "$ci_workflow" 'CI must use the integrity-pinned packageManager declaration'
reject_match 'runs-on:[[:space:]]*[a-z0-9-]+-latest' "$ci_workflow" 'CI must pin runner images instead of tracking -latest'

if grep -E '^[[:space:]]*-?[[:space:]]*uses:' "$ci_workflow" | grep -Ev '@[0-9a-f]{40}([[:space:]]|$)' >/dev/null; then
    fail 'every action must be pinned to an immutable commit SHA'
fi

reject_match 'e2e:test|test:e2e|playwright-report|mcr\.microsoft\.com/playwright' "$ci_workflow" 'CI must not expose an E2E job'
reject_match 'test:e2e|test:visual' web/Makefile 'the web Makefile must not expose nonexistent browser tests'
reject_match '"@playwright/test"' web/package.json 'web must not keep the unused Playwright dependency'
require_match '"packageManager": "pnpm@[0-9]+\.[0-9]+\.[0-9]+\+sha512\.' web/package.json 'web pnpm must be versioned and integrity-pinned'

for log_doc in server/.env.example; do
    reject_match 'LOG_PATH="?([.]/|[.][.]/)' "$log_doc" "$log_doc must not recommend a relative LOG_PATH assignment"
done
require_match 'RPC_HTTP_BODY_READ_TIMEOUT_SECONDS=15' server/.env.example 'the server env example must document the HTTP body read timeout'
require_match 'read-only root filesystem' server/.env.example 'the server env example must document the read-only runtime'
require_match 'Leave LOG_PATH unset' server/.env.example 'the server env example must leave container LOG_PATH unset'
require_match 'collect stderr' server/.env.example 'the server env example must document stderr collection'
require_match 'AUTH_SESSION_SECRET must contain at least 32 bytes in production' server/app/core/config.py 'the backend must require a strong production session secret'
require_match 'Endpoint encryption keyring must be configured in production' server/app/core/config.py 'the backend must require a production endpoint keyring'
for endpoint_crypto_file in server/.env.example server/app/cli/endpoint_rekey.py server/app/core/config.py server/app/services/endpoint/crypto.py; do
    reject_match 'allow-weak-legacy-key' "$endpoint_crypto_file" "$endpoint_crypto_file must not expose weak encryption compatibility"
done

for dockerfile in server/Dockerfile; do
    if ! awk '
        /^FROM[[:space:]]+/ {
            image = $2
            if (image ~ /[:\/]/ && image !~ /@sha256:[0-9a-f]{64}$/) {
                exit 1
            }
        }
    ' "$dockerfile"; then
        fail "every base image in $dockerfile must use an immutable SHA-256 manifest digest"
    fi
    reject_match '(^|[^[:alnum:]_-])latest([^[:alnum:]_.-]|$)' "$dockerfile" "$dockerfile must not use latest"
    if grep -Eq '^# syntax=' "$dockerfile"; then
        require_match '^# syntax=.*@sha256:[0-9a-f]{64}$' "$dockerfile" "$dockerfile must pin the Dockerfile frontend by digest"
    fi
done

require_match '^USER 10001:10001$' server/Dockerfile 'the server runtime image must use UID/GID 10001'
require_match 'COPY --from=builder --chown=10001:10001 /rpc-gateway-api /rpc-gateway-api' server/Dockerfile 'the server application directory must belong to the runtime user'
require_match '"main": "\.open-next/worker\.js"' web/wrangler.jsonc 'the web Worker must use the OpenNext entrypoint'
require_match '"nodejs_compat"' web/wrangler.jsonc 'the web Worker must enable Node.js compatibility'
require_match '"directory": "\.open-next/assets"' web/wrangler.jsonc 'the web Worker must bind OpenNext assets'
reject_match 'CF_ACCESS_CLIENT_SECRET|API_PROXY_TARGET|NEXT_PUBLIC_SITE_URL' web/wrangler.jsonc 'deployment values and secrets must not be committed in Wrangler config'

check_compose_service() {
    compose_file=$1
    service=$2
    expected_user=$3
    if ! awk -v service="$service" -v expected_user="$expected_user" '
        $0 == "  " service ":" { in_service = 1; next }
        in_service && /^  [[:alnum:]_-]+:$/ { in_service = 0 }
        in_service && $0 == "    read_only: true" { read_only = 1 }
        in_service && $0 == "    cap_drop:" { cap_drop = 1 }
        in_service && $0 == "      - ALL" { drop_all = 1 }
        in_service && $0 == "    security_opt:" { security_opt = 1 }
        in_service && $0 == "      - no-new-privileges:true" { no_new_privileges = 1 }
        in_service && $0 == "    user: \"" expected_user "\"" { user = 1 }
        in_service && $0 == "    tmpfs:" { tmpfs = 1 }
        END { exit !(read_only && cap_drop && drop_all && security_opt && no_new_privileges && user && tmpfs) }
    ' "$compose_file"; then
        fail "compose service $service in $compose_file must use a read-only, capability-free, non-root runtime"
    fi
}

check_compose_environment() {
    compose_file=$1
    service=$2
    variable=$3
    expected_value=$4
    if ! awk -v service="$service" -v expected="$variable: $expected_value" '
        $0 == "  " service ":" { in_service = 1; next }
        in_service && /^  [[:alnum:]_-]+:$/ { in_service = 0 }
        in_service && $0 == "      " expected { found = 1 }
        END { exit !found }
    ' "$compose_file"; then
        fail "compose service $service in $compose_file must set $variable=$expected_value"
    fi
}

require_compose_network() {
    compose_file=$1
    service=$2
    network=$3
    if ! awk -v service="$service" -v network="$network" '
        $0 == "  " service ":" { in_service = 1; next }
        in_service && /^  [[:alnum:]_-]+:$/ { in_service = 0 }
        in_service && $0 == "      - " network { found = 1 }
        END { exit !found }
    ' "$compose_file"; then
        fail "compose service $service in $compose_file must join $network"
    fi
}

reject_compose_network() {
    compose_file=$1
    service=$2
    network=$3
    if awk -v service="$service" -v network="$network" '
        $0 == "  " service ":" { in_service = 1; next }
        in_service && /^  [[:alnum:]_-]+:$/ { in_service = 0 }
        in_service && $0 == "      - " network { found = 1 }
        END { exit !found }
    ' "$compose_file"; then
        fail "compose service $service in $compose_file must not join $network"
    fi
}

check_compose_service docker-compose.yml api 10001:10001
check_compose_service docker-compose.yml api-worker 10001:10001
check_compose_service docker-compose.yml api-scheduler 10001:10001
check_compose_environment docker-compose.yml api HOST 0.0.0.0
check_compose_environment docker-compose.yml api APP_ENV '${APP_ENV:-prod}'
check_compose_environment docker-compose.yml api-worker APP_ENV '${APP_ENV:-prod}'
check_compose_environment docker-compose.yml api-scheduler APP_ENV '${APP_ENV:-prod}'
require_match '^  ingress:$' docker-compose.yml 'the root compose must define a dedicated ingress network'
require_match '^    name: rpc-gateway_ingress$' docker-compose.yml 'the ingress network must use the dedicated deployment name'
reject_match 'traefik-network' docker-compose.yml 'the gateway must not join the shared Traefik network'
require_compose_network docker-compose.yml api ingress
require_compose_network docker-compose.yml api internal
for service in api-worker api-scheduler; do
    require_compose_network docker-compose.yml "$service" internal
    reject_compose_network docker-compose.yml "$service" ingress
done

printf 'infrastructure security contract passed\n'
