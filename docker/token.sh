# This file is sourced by the entrypoint and the health check.
load_keep_token() {
    if [ -n "${KEEP_HTTP_TOKEN_FILE:-}" ] && [ -n "${KEEP_HTTP_TOKEN:-}" ]; then
        echo 'Set KEEP_HTTP_TOKEN_FILE or KEEP_HTTP_TOKEN, but not both.' >&2
        return 1
    fi
    if [ -n "${KEEP_HTTP_TOKEN_FILE:-}" ]; then
        token_file=$KEEP_HTTP_TOKEN_FILE
    elif [ -n "${KEEP_HTTP_TOKEN:-}" ]; then
        token_file=
    else
        token_file=/run/secrets/keep_http_token
    fi
    if [ -n "$token_file" ]; then
        if [ ! -f "$token_file" ] || [ ! -r "$token_file" ]; then
            echo 'The Keep token file must be a readable regular file.' >&2
            return 1
        fi
        bytes=$(wc -c < "$token_file" | tr -d '[:space:]')
        last_bytes=$(tail -c 2 "$token_file" | od -An -tx1 | tr -d ' \n')
        case "$bytes:$last_bytes" in
            64:*) ;;
            65:*0a) ;;
            66:0d0a) ;;
            *)
                echo 'The Keep token file must contain one token, with an optional final LF or CRLF.' >&2
                return 1 ;;
        esac
        # Permit one final LF or CRLF from a text editor.
        KEEP_HTTP_TOKEN=$(cat "$token_file")
        KEEP_HTTP_TOKEN=${KEEP_HTTP_TOKEN%"$(printf '\r')"}
    fi
    if [ "${#KEEP_HTTP_TOKEN}" -ne 64 ]; then
        echo 'The Keep token must contain exactly 64 lowercase hexadecimal characters.' >&2
        return 1
    fi
    case "$KEEP_HTTP_TOKEN" in
        *[!0-9a-f]*)
            echo 'The Keep token must contain exactly 64 lowercase hexadecimal characters.' >&2
            return 1 ;;
    esac
    export KEEP_HTTP_TOKEN
}
