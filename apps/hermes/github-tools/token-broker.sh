#!/bin/sh
set -eu

helper=/opt/github-bin/git-credential-github-app
private_key=/var/run/github-app/privateKey
token_dir=/var/run/github-token

require_file() {
  if [ ! -r "$1" ] || [ ! -f "$1" ]; then
    echo "github-token-broker: missing readable file: $1" >&2
    exit 1
  fi
}

require_file "$helper"
require_file "$private_key"

if [ -z "${GITHUB_APP_CLIENT_ID:-}" ] || [ -z "${GITHUB_APP_INSTALLATION_ID:-}" ]; then
  echo "github-token-broker: GitHub App client/installation ID is missing" >&2
  exit 1
fi

mkdir -p "$token_dir"

while :; do
  if output="$(
    printf 'protocol=https\nhost=github.com\n\n' |
      "$helper" \
        --private-key "$private_key" \
        --client-id "$GITHUB_APP_CLIENT_ID" \
        --installation-id "$GITHUB_APP_INSTALLATION_ID" \
        get
  )"; then
    token="$(printf '%s\n' "$output" | sed -n 's/^password=//p')"
    expiry="$(printf '%s\n' "$output" | sed -n 's/^password_expiry_utc=//p')"

    case "$expiry" in
      ''|*[!0-9]*)
        echo "github-token-broker: helper did not return a valid expiry" >&2
        sleep 60
        continue
        ;;
    esac
    if [ -z "$token" ]; then
      echo "github-token-broker: helper returned an empty token" >&2
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
