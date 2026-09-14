#!/bin/sh
set -eu

private_key=/var/run/github-app/privateKey
token_dir=/var/run/github-token

require_file() {
  if [ ! -r "$1" ] || [ ! -f "$1" ]; then
    echo "github-token-broker: missing readable file: $1" >&2
    exit 1
  fi
}

require_file "$private_key"

is_positive_decimal() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "${#1}" -le 18 ] && [ "$1" -gt 0 ]
}

if ! is_positive_decimal "${GITHUB_APP_ID:-}" || \
  ! is_positive_decimal "${GITHUB_APP_INSTALLATION_ID:-}"; then
  echo "github-token-broker: GitHub App and installation IDs must be positive integers" >&2
  exit 1
fi

b64url() {
  openssl base64 -A | tr '+/' '-_' | tr -d '='
}

create_jwt() {
  now="$(date +%s)"
  header="$(printf '%s' '{"alg":"RS256","typ":"JWT"}' | b64url)"
  payload="$(
    printf '{"iat":%s,"exp":%s,"iss":%s}' \
      "$((now - 60))" "$((now + 540))" "$GITHUB_APP_ID" | b64url
  )"
  signature="$(
    printf '%s.%s' "$header" "$payload" |
      openssl dgst -binary -sha256 -sign "$private_key" | b64url
  )"
  printf '%s.%s.%s\n' "$header" "$payload" "$signature"
}

mint_token() {
  jwt="$(create_jwt)"
  curl -fsS --retry 3 --retry-all-errors \
    --request POST \
    --header 'Accept: application/vnd.github+json' \
    --header "Authorization: Bearer $jwt" \
    --header 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/app/installations/${GITHUB_APP_INSTALLATION_ID}/access_tokens"
}

parse_token_response() {
  python3 -c '
import json
import sys
from datetime import datetime, timezone

try:
    response = json.load(sys.stdin)
    token = response["token"]
    expires_at = response["expires_at"]
    if not isinstance(token, str) or not token or "\n" in token:
        raise ValueError
    expiry = int(datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp())
    if expiry <= int(datetime.now(timezone.utc).timestamp()) + 60:
        raise ValueError
except (KeyError, TypeError, ValueError):
    raise SystemExit("github-token-broker: invalid GitHub token response")

print(token)
print(expiry)
'
}

mkdir -p "$token_dir"

while :; do
  if output="$(mint_token | parse_token_response)"; then
    token="$(printf '%s\n' "$output" | sed -n '1p')"
    expiry="$(printf '%s\n' "$output" | sed -n '2p')"

    case "$expiry" in
      ''|*[!0-9]*)
        echo "github-token-broker: GitHub returned an invalid expiry" >&2
        sleep 60
        continue
        ;;
    esac
    if [ -z "$token" ]; then
        echo "github-token-broker: GitHub returned an empty token" >&2
      sleep 60
      continue
    fi

    token_tmp="$token_dir/.token.$$"
    expiry_tmp="$token_dir/.expires_at.$$"
    umask 022
    printf '%s' "$token" > "$token_tmp"
    printf '%s\n' "$expiry" > "$expiry_tmp"
    chmod 0444 "$token_tmp" "$expiry_tmp"
    mv "$token_tmp" "$token_dir/token"
    mv "$expiry_tmp" "$token_dir/expires_at"

    now="$(date +%s)"
    # Refresh ten minutes before expiry. On failure, retry every minute while
    # the previous token remains available to Hermes.
    delay=$((expiry - now - 600))
    if [ "$delay" -lt 60 ]; then
      delay=60
    fi
    echo "github-token-broker: installation token refreshed; next refresh in ${delay}s"
    sleep "$delay"
  else
    echo "github-token-broker: token refresh failed; retrying in 60s" >&2
    sleep 60
  fi
done
