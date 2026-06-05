#!/usr/bin/env bash
# PR-incremental mutation gate.
#
# Runs mutmut only on the pql/ + services/ modules a change actually
# touches, and fails if any of them introduces a surviving mutant that
# is not on the known-equivalent allowlist. This keeps the gate's
# wall-clock bounded (one stats pass + only the changed modules' mutants)
# while still catching "added logic, forgot the test that pins it" at the
# exact spot it is introduced.
#
# The full sweep is the nightly job (.github/workflows/mutation-nightly.yml);
# this is the cheap per-PR predecessor, the same shape as the pyright /
# file-size budget gates.
#
# Env:
#   MUTATION_BASE_REF   git ref to diff against (default: origin/main).
#                       CI sets it to the PR base; locally it defaults to
#                       origin/main.
#
# Not wired into pre-commit on purpose — even a scoped run is minutes,
# far too slow for a commit hook.

set -euo pipefail

BASE_REF="${MUTATION_BASE_REF:-origin/main}"
ALLOWLIST="scripts/mutation/equivalent.txt"
MUTMUT=(uv run --with mutmut==3.5.0 python scripts/mutation/run_mutmut.py)

# 1. Changed (added/modified, not deleted) .py files under the two
#    mutated packages, relative to the merge base with BASE_REF.
mapfile -t changed < <(
    git diff --name-only --diff-filter=d "${BASE_REF}...HEAD" -- \
        'pointlessql/pql/**.py' 'pointlessql/services/**.py' 2>/dev/null |
        grep -E '\.py$' || true
)

if [ "${#changed[@]}" -eq 0 ]; then
    echo "check-mutation-budget: no pointlessql/{pql,services} .py changes vs ${BASE_REF}; nothing to mutate."
    exit 0
fi

# 2. Map each path to a mutmut module glob: drop .py, slashes -> dots.
#    pointlessql/services/foo/bar.py -> pointlessql.services.foo.bar.*
globs=()
for f in "${changed[@]}"; do
    mod="${f%.py}"
    mod="${mod//\//.}"
    globs+=("${mod}.*")
done

echo "check-mutation-budget: mutating ${#globs[@]} changed module(s) vs ${BASE_REF}:"
printf '  - %s\n' "${globs[@]}"

# 3. Scoped run. Drop stale stats so the mutant->test coverage map is
#    rebuilt for the current tree. mutmut exits non-zero when survivors
#    exist; we adjudicate against the allowlist below, so don't let the
#    raw exit abort us here.
rm -f mutants/mutmut-stats.json
"${MUTMUT[@]}" run "${globs[@]}" || true

# 4. Collect surviving mutants (mutmut results prints "<name>: survived").
mapfile -t survivors < <(
    "${MUTMUT[@]}" results 2>/dev/null |
        awk '/: survived$/ { gsub(/^[ \t]+/, ""); sub(/: survived$/, ""); print }'
)

# 5. Drop the known-equivalent allowlist.
declare -A allow=()
if [ -f "$ALLOWLIST" ]; then
    while IFS= read -r line; do
        line="${line%%#*}"
        line="$(printf '%s' "$line" | tr -d '[:space:]')"
        [ -n "$line" ] && allow["$line"]=1
    done <"$ALLOWLIST"
fi

offenders=()
for s in "${survivors[@]}"; do
    [ -n "$s" ] || continue
    if [ -z "${allow[$s]:-}" ]; then
        offenders+=("$s")
    fi
done

# 6. Verdict.
if [ "${#offenders[@]}" -gt 0 ]; then
    echo >&2
    echo "ERROR: ${#offenders[@]} new surviving mutant(s) in changed modules:" >&2
    printf '  %s\n' "${offenders[@]}" >&2
    echo >&2
    echo "Each survivor is a behavioural change your tests did not catch." >&2
    echo "Either add a test that kills it, or — only if it is genuinely" >&2
    echo "equivalent — add it to ${ALLOWLIST} with a reason." >&2
    echo "Inspect one with: ${MUTMUT[*]} show <name>" >&2
    exit 1
fi

echo "OK: no non-equivalent survivors in the ${#globs[@]} changed module(s)."
exit 0
