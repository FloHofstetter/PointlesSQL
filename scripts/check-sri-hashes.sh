#!/usr/bin/env bash
# Subresource-Integrity drift guard.
#
# Re-fetches every CDN asset referenced in frontend/templates/ and confirms
# the live bytes still hash to the ``integrity="sha384-…"`` pinned on the
# tag.  Catches a hash typo, an un-updated version bump, or upstream
# tampering of an immutable CDN URL.
#
# Needs network egress to the CDN, so it is NOT a pre-commit hook — run it
# in CI or by hand:  bash scripts/check-sri-hashes.sh
#
# Exit 0 = every pinned hash matches; non-zero = drift (the offending
# URL + expected/actual hash are printed).

set -euo pipefail

TEMPLATES_DIR="frontend/templates"
fail=0
checked=0

# Extract (url, integrity) pairs: a quoted CDN URL immediately followed by
# its integrity attribute.  One pair per line as "url<TAB>sha384-…".
pairs=$(grep -rhoE \
  '(src|href)="(https://cdn\.[^"]+)" integrity="(sha384-[^"]+)"' \
  "$TEMPLATES_DIR" \
  | sed -E 's#.*"(https://cdn\.[^"]+)" integrity="(sha384-[^"]+)".*#\1\t\2#' \
  | sort -u)

if [ -z "$pairs" ]; then
  echo "no integrity-pinned CDN tags found under $TEMPLATES_DIR" >&2
  exit 1
fi

while IFS=$'\t' read -r url pinned; do
  [ -z "$url" ] && continue
  actual="sha384-$(curl -fsSL --retry 2 "$url" | openssl dgst -sha384 -binary | openssl base64 -A)"
  checked=$((checked + 1))
  if [ "$actual" != "$pinned" ]; then
    echo "DRIFT: $url" >&2
    echo "  pinned: $pinned" >&2
    echo "  actual: $actual" >&2
    fail=1
  fi
done <<< "$pairs"

if [ "$fail" -ne 0 ]; then
  echo "SRI drift detected — update the integrity= attribute(s) above." >&2
  exit 1
fi

echo "OK: all $checked SRI-pinned CDN assets still match their integrity hash."
