#!/bin/sh
set -eu
. /usr/local/lib/keep/token.sh
load_keep_token
# The token goes through stdin. It does not appear in curl's arguments.
response=$(
    printf 'header = "Authorization: Bearer %s"\n' "$KEEP_HTTP_TOKEN" |
        curl --config - --silent --fail --max-time 8 \
            --header 'Content-Type: application/json' \
            --header 'Accept: application/json, text/event-stream' \
            --header 'MCP-Protocol-Version: 2025-11-25' \
            --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
            "http://127.0.0.1:${KEEP_HTTP_HEALTH_PORT:-7340}/mcp"
)
printf '%s' "$response" | grep -q '"tools"'
