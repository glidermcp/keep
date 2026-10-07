#!/bin/sh
set -eu
# Administrative commands do not need an HTTP token.
case "${1:-}" in
    --version|-V|--help|-h|--generate-token|export|import)
        exec /usr/local/bin/keep "$@" ;;
esac
. /usr/local/lib/keep/token.sh
load_keep_token
exec /usr/local/bin/keep "$@"
