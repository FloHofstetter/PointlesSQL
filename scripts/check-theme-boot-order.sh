#!/usr/bin/env bash
# Theme-boot ordering guard.
#
# theme_boot.js sets ``data-bs-theme`` on <html> and must execute as a
# classic, render-blocking script BEFORE the first stylesheet <link>
# in every layout — otherwise the first paint flashes the static
# fallback theme.  The guarantee used to live in comments next to
# inline scripts; this makes it mechanical.

set -euo pipefail

LAYOUTS=(
    "frontend/templates/base.html"
    "frontend/templates/base_public.html"
    "frontend/templates/_layouts/auth_chromeless.html"
)

fail=0
for layout in "${LAYOUTS[@]}"; do
    boot_line="$(grep -n "theme_boot\.js" "$layout" | head -1 | cut -d: -f1 || true)"
    css_line="$(grep -n '<link[^>]*rel="stylesheet"' "$layout" | head -1 | cut -d: -f1 || true)"
    if [ -z "$boot_line" ]; then
        echo "ERROR: $layout does not load theme_boot.js" >&2
        fail=1
        continue
    fi
    if [ -n "$css_line" ] && [ "$boot_line" -gt "$css_line" ]; then
        echo "ERROR: $layout loads theme_boot.js (line $boot_line) after the" >&2
        echo "  first stylesheet (line $css_line) — the first paint will flash." >&2
        fail=1
    fi
done

if [ "$fail" -ne 0 ]; then
    exit 1
fi
echo "OK: theme_boot.js precedes the first stylesheet in every layout."
