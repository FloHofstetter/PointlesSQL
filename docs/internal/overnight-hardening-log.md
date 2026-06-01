# Overnight Hardening Marathon — run log

Autonomous hardening run started 2026-06-02. Lands as **Hardening Cluster (Phase 189+)**
on top of ROADMAP head Phase 188. One local commit per phase, full `pytest` green gate,
**no push** — left for Florian's morning review.

Baseline: `4131 passed, 14 skipped, 10 deselected` (243s).

Adaptation (recorded up front): the Explore scoping heuristic over-counted "untested"
services — e.g. `dp_canvas` is already saturated (~95 tests). So **Group A is run
coverage-guided**: each test phase does a real gap analysis (`pytest --cov` on the target
module) and fills genuine gaps rather than duplicating existing tests; saturated modules
are skipped in favour of genuinely low-coverage ones.

---

## Phase log

### Phase 0 — Re-baseline + commit canvas WIP
- Baseline suite green at 4131 passed / 14 skipped / 10 deselected.
- Reviewed canvas run-dock WIP: coherent, already documented in ROADMAP + CHANGELOG;
  pyproject bump clean rc252→rc254. Staged only tracked files (left scratch `.jpg`s untracked).
- Committed as Phase 0. Tree clean apart from scratch artifacts.

Generated a full `--cov` map up front (`/tmp/pql-cov.json`) and drive Group A from it.
ROADMAP/CHANGELOG churn is batched into a single Hardening-Cluster node at the closing
phase (rather than 20+ per-phase edits); this log is the per-phase record in the meantime.

### Phase 1 — pure-logic gap tests (suite 4131→4170, +39)
- `tests/test_output_rendering.py` (+27): `services/output_rendering.py` was 0% / zero test
  refs. Covers the full mime-bundle priority order (markdown>html>svg>png>jpeg>json>plain),
  the widget placeholder + model_id truncation, stream stdout/stderr, error traceback vs
  ename/evalue fallback, list-payload coercion, HTML-escaping, and the unknown-type fallbacks.
- `tests/test_aws_sigv4.py` (+12): `services/aws_sigv4.py` was 22% / zero test refs. Verifies
  the signature against an independent in-test re-derivation of the SigV4 algorithm (genuine
  cross-check), the empty-body SHA-256 external known-answer, determinism for a fixed clock,
  signature sensitivity to body/region, extra-header signing, and canonical-URI encoding.
- Committed.
