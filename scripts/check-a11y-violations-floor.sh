#!/usr/bin/env bash
# Accessibility violations-floor gate.
#
# Runs the axe-core e2e test, which audits key surfaces and fails when the
# aggregate violation counts exceed scripts/wcag_aa_violations_floor.json
# (critical/serious held at 0; moderate/minor ratcheting down). Needs a
# browser, so this runs inside the e2e-browser CI job after
# `playwright install chromium`.
#
# The floor comparison lives in the test; this wrapper just invokes it so it
# can sit alongside the other check-*.sh gates.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

exec uv run pytest -q e2e/test_a11y_violations_floor.py -m e2e
