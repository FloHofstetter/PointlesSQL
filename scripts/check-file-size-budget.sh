#!/usr/bin/env bash
# File-size budget for pointlessql/**.py.
#
# The project keeps single source-of-truth modules small: no
# pointlessql/**.py that mixes multiple concerns should exceed 800
# LOC.  This gate prevents new mixed-concerns files from sneaking in:
# any pointlessql/**.py whose line count exceeds 800 fails CI unless
# it appears in the explicit allow-list below.
#
# Files in the allow-list are big-by-design — a public API surface or
# a coherent module/tree where splitting would create false seams.
# When something legitimately new crosses the budget, ADD IT to the
# allow-list with a short comment explaining why — don't bump the
# budget number.
#
# The allow-list is currently empty: the modularization passes split
# every previously-oversized module (api/dependencies.py was the last)
# into focused packages, so no pointlessql/**.py is big-by-design
# over budget today.

set -euo pipefail

BUDGET=800

# Files explicitly allowed above the budget, with the reason. Empty
# today — see the header note above.
ALLOWLIST=()

is_allowed() {
    local path="$1"
    if [ "${#ALLOWLIST[@]}" -eq 0 ]; then
        return 1
    fi
    for allowed in "${ALLOWLIST[@]}"; do
        if [ "$path" = "$allowed" ]; then
            return 0
        fi
    done
    return 1
}

failed=0

while IFS= read -r path; do
    line_count=$(wc -l < "$path")
    if [ "$line_count" -gt "$BUDGET" ]; then
        if is_allowed "$path"; then
            continue
        fi
        echo "ERROR: $path is $line_count LOC (>${BUDGET})" >&2
        echo "  Either split the file (project modularization pattern)" >&2
        echo "  or add it to ALLOWLIST in scripts/check-file-size-budget.sh" >&2
        echo "  with a short comment explaining why it is big-by-design." >&2
        failed=1
    fi
done < <(find pointlessql -name '*.py' -type f)

if [ $failed -eq 0 ]; then
    echo "OK: no pointlessql/**.py exceeds ${BUDGET} LOC outside the allowlist."
fi

exit $failed
