#!/bin/sh
set -eu
if [ ! -r /run/secrets/cloudflare_api_token ]; then
    echo 'The Cloudflare token file must be readable.' >&2
    exit 1
fi
CLOUDFLARE_API_TOKEN=$(cat /run/secrets/cloudflare_api_token)
CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN%"$(printf '\r')"}
if [ -z "$CLOUDFLARE_API_TOKEN" ]; then
    echo 'The Cloudflare token must contain a value.' >&2
    exit 1
fi
export CLOUDFLARE_API_TOKEN
exec "$@"
