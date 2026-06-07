"""Coverage ledger — every e2e playbook is accounted for (no silent gaps).

A registry classifies each deterministic playbook under
``docs/e2e-walkthroughs/`` as ``automated`` (replayed by a registered
:mod:`e2e._journeys` journey) or as one of the explicit deferral buckets
(with a reason).  A meta-test globs the playbook directory and fails if a
new ``*.md`` appears without a ledger entry — so a future UI surface cannot
ship a manual-only playbook without a coverage decision.

This is the e2e analogue of the lineage coverage ledger
(``tests/lineage_verify/test_coverage_ledger.py``): a ratchet, not a report.

The module is pure filesystem + dict introspection — it imports neither
Playwright nor the app, so it runs without a live server or browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from e2e._journeys import JOURNEYS, automated_playbooks

pytestmark = pytest.mark.e2e

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLAYBOOK_DIR = _REPO_ROOT / "docs" / "e2e-walkthroughs"

# Status vocabulary.
#   automated                -> replayed by a registered journey (must match)
#   pending                  -> pure-UI, automatable with soyuz DOWN; not yet written
#   curl-api                 -> pure httpx API journey (no browser); not yet written
#   deferred-requires-soyuz  -> needs catalog/lineage/federation data on GET
#   deferred-subprocess      -> needs Jupyter / MLflow / dbt / scheduler subprocess
#   deferred-hermes          -> needs a live LLM / Hermes agent runtime
#   n-a                      -> not a browser journey (MCP server mode, packaging docs)
_VALID_STATUSES = {
    "automated",
    "pending",
    "curl-api",
    "deferred-requires-soyuz",
    "deferred-subprocess",
    "deferred-hermes",
    "n-a",
}

# playbook filename -> (status, note).  Every *.md under docs/e2e-walkthroughs/
# (except README) MUST appear here.  The ratchet meta-test enforces it.
PLAYBOOK_COVERAGE: dict[str, tuple[str, str]] = {
    # --- automated: backed by a registered journey ---------------------------
    "operational.md": ("automated", "healthz + authenticated-home smoke (test_smoke)"),
    "notebook-coedit-multi-tab.md": (
        "automated",
        "multi-tab CRDT convergence (test_notebook_coedit_multi_tab)",
    ),
    # --- pending: pure-UI, automatable with soyuz DOWN -----------------------
    "auth.md": ("pending", "login / logout / session — pure auth surface, our DB"),
    "csrf.md": ("pending", "CSRF token handshake on form POSTs — pure middleware"),
    "oidc.md": ("pending", "SSO button + mock-oidc flow — env-overlay, no soyuz"),
    "error-handling.md": ("pending", "403 / 404 / 500 error envelopes — pure templates"),
    "home.md": ("pending", "home dashboard shell — renders without catalog data"),
    "rate-limit.md": ("pending", "429 after burst — pure middleware, our DB"),
    "mobile.md": ("pending", "375x812 responsive layout — needs a mobile viewport fixture"),
    "config-matrix.md": ("pending", "log-format / tick env-overlay deltas — no soyuz"),
    "admin-console.md": ("pending", "admin console shell + nav — our DB"),
    "admin-audit.md": ("pending", "admin audit-log viewer — our DB audit rows"),
    "admin-policy-modules.md": ("pending", "policy-as-code module registry — our DB"),
    "computational-policy-as-code.md": ("pending", "policy module authoring — our DB"),
    "audit-sinks.md": ("pending", "audit-sink config (webhook/S3/CloudTrail) — our DB"),
    "alerts.md": ("pending", "alert-rule config (HMAC/CloudEvents/Atom) — our DB"),
    "multi-workspace-setup.md": ("pending", "workspace isolation + membership — our DB"),
    "data-product-infrastructure.md": ("pending", "DP infrastructure config form — our DB"),
    "library-facts.md": ("pending", "library / facts reference page — static"),
    "list-polish.md": ("pending", "list-view polish (empty states, sort) — our DB"),
    "ux-overhaul.md": ("pending", "nav / breadcrumb / toast UX shell — static"),
    "social.md": ("pending", "social affordances (reactions, follows) — our DB"),
    "notebook-overview.md": ("pending", "notebook list / overview — our DB, no kernel"),
    "notebook-cell-social.md": ("pending", "cell comments / reactions — our DB, no kernel"),
    "scheduler-dag-editor.md": ("pending", "job DAG canvas editor — our-DB job seed, no soyuz"),
    # --- curl-api: pure httpx API journeys (no browser) ----------------------
    "external-sql-api.md": ("curl-api", "external SQL REST API — httpx, no browser"),
    "git-backed-workspaces.md": ("curl-api", "git-provider workspace API — httpx, no browser"),
    # --- deferred-requires-soyuz: needs catalog data on GET ------------------
    "catalog-browsing.md": ("deferred-requires-soyuz", "catalogs/schemas/tables browse"),
    "inline-editors.md": (
        "deferred-requires-soyuz",
        "inline comment/property edit on catalog rows",
    ),
    "contextual-panels.md": (
        "deferred-requires-soyuz",
        "context help panels keyed to catalog entities",
    ),
    "command-palette.md": ("deferred-requires-soyuz", "palette search resolves catalog entities"),
    "volumes.md": ("deferred-requires-soyuz", "UC Volumes browse"),
    "sql-editor.md": ("deferred-requires-soyuz", "SQL editor against seeded tables"),
    "sql-editor-writes.md": (
        "deferred-requires-soyuz",
        "SQL editor write-path against seeded tables",
    ),
    "explain-rewrite.md": ("deferred-requires-soyuz", "EXPLAIN cost-gate + rewrite on a query"),
    "time-travel.md": ("deferred-requires-soyuz", "Delta time-travel reads"),
    "branches.md": ("deferred-requires-soyuz", "Delta branching control-room"),
    "federation.md": ("deferred-requires-soyuz", "Lakehouse Federation foreign catalog"),
    "foreign-catalog-sync.md": ("deferred-requires-soyuz", "foreign-catalog sync status"),
    "vector-search.md": ("deferred-requires-soyuz", "vector index + search over a table"),
    "models-tab.md": ("deferred-requires-soyuz", "UC MODEL securable tab"),
    "lens-overview.md": ("deferred-requires-soyuz", "Lens overview reads catalog metadata"),
    "data-products.md": ("deferred-requires-soyuz", "data-product list/detail over catalog"),
    "data-product-as-code.md": ("deferred-requires-soyuz", "DP-as-code apply over catalog"),
    "data-product-discovery.md": ("deferred-requires-soyuz", "DP discovery / marketplace"),
    "data-product-lifecycle.md": ("deferred-requires-soyuz", "DP lifecycle transitions"),
    "data-product-event-port.md": ("deferred-requires-soyuz", "DP event-port wiring"),
    "data-product-consumer-voice.md": ("deferred-requires-soyuz", "DP consumer-voice feedback"),
    "data-product-consumption-enforcement.md": (
        "deferred-requires-soyuz",
        "DP consumption enforcement",
    ),
    "data-product-bitemporal-enforcement.md": (
        "deferred-requires-soyuz",
        "DP bitemporal enforcement",
    ),
    "output-port-schema-versioning.md": (
        "deferred-requires-soyuz",
        "output-port schema versioning enforcer",
    ),
    "product-quota-enforcement.md": ("deferred-requires-soyuz", "per-product quota enforcement"),
    "data-mesh.md": ("deferred-requires-soyuz", "data-mesh overview over catalog"),
    "data-domains.md": ("deferred-requires-soyuz", "mesh data-domain registry"),
    "data-governance.md": ("deferred-requires-soyuz", "governance policy surface over catalog"),
    "mesh-cost-dashboard.md": ("deferred-requires-soyuz", "mesh cost dashboard over catalog"),
    "admin-mesh-dashboard.md": ("deferred-requires-soyuz", "admin mesh dashboard over catalog"),
    "admin-entity-discovery.md": ("deferred-requires-soyuz", "admin entity discovery over catalog"),
    "entity-link-discovery.md": ("deferred-requires-soyuz", "entity-link discovery over catalog"),
    "admin-data-product-apply.md": ("deferred-requires-soyuz", "admin DP apply over catalog"),
    "admin-cdf-tail.md": ("deferred-requires-soyuz", "admin CDF tail over a Delta table"),
    "inference-lineage.md": ("deferred-requires-soyuz", "inference lineage over a model+table"),
    "dp-canvas-builder.md": (
        "deferred-requires-soyuz",
        "DP canvas builder needs a seeded canvas product",
    ),
    "dataframe-studio.md": (
        "deferred-requires-soyuz",
        "DataFrame studio canvas over catalog tables",
    ),
    # --- deferred-subprocess: Jupyter / MLflow / dbt / scheduler -------------
    "notebook-editor.md": ("deferred-subprocess", "live kernel (ipykernel) required"),
    "notebook-editor-ui.md": ("deferred-subprocess", "live kernel + editor UI"),
    "notebook-editor-advanced.md": ("deferred-subprocess", "live kernel advanced features"),
    "notebook-full-walkthrough.md": ("deferred-subprocess", "full notebook run via papermill"),
    "notebook-jobs.md": ("deferred-subprocess", "scheduled notebook execution (papermill)"),
    "jobs-dag.md": ("deferred-subprocess", "scheduler tick drives DAG state transitions"),
    "dashboards.md": ("deferred-subprocess", "chart rendering over executed query data"),
    "dbt-pipeline.md": ("deferred-subprocess", "dbt subprocess + docs"),
    "data-product-contract-tests.md": (
        "deferred-subprocess",
        "runs DP contract tests in a subprocess",
    ),
    "rollback.md": ("deferred-subprocess", "rollback runs through the executor/run worker"),
    "run-comparisons.md": ("deferred-subprocess", "compares two executed runs"),
    "audit-cockpit-deep.md": ("deferred-subprocess", "deep cockpit needs streamed forensics data"),
    "model-compare.md": ("deferred-subprocess", "MLflow model comparison"),
    "models-promotion.md": ("deferred-subprocess", "MLflow model promotion run"),
    "agent-ml-registry.md": ("deferred-subprocess", "MLflow registry via agent run"),
    "full-stack-demo.md": ("deferred-subprocess", "grand-tour boots every subsystem"),
    "grand-tour.md": ("deferred-subprocess", "grand-tour boots every subsystem"),
    # --- deferred-hermes: needs a live LLM / Hermes agent runtime ------------
    "hermes-medallion.md": ("deferred-hermes", "Hermes agent builds a medallion pipeline"),
    "agent-memory.md": ("deferred-hermes", "agent analytical-memory loop"),
    "agent-drift-monitor.md": ("deferred-hermes", "agent drift monitoring loop"),
    "agent-review-detail.md": ("deferred-hermes", "audit-reviewer agent persona output"),
    "audit-reviewer-daily.md": ("deferred-hermes", "daily audit-reviewer agent run"),
    "compliance-bot.md": ("deferred-hermes", "compliance agent persona"),
    "incident-responder.md": ("deferred-hermes", "incident-responder agent persona"),
    "notebook-assistant.md": ("deferred-hermes", "in-notebook LLM assistant"),
    "sql-chat.md": ("deferred-hermes", "natural-language SQL chat (LLM)"),
    "reflexive-tools.md": ("deferred-hermes", "reflexive MCP tools driven by an agent"),
    # --- n-a: not a browser journey -----------------------------------------
    "lens-mcp.md": ("n-a", "MCP server stdio/SSE mode — no browser surface"),
    "packaging.md": ("n-a", "packaging / distribution walkthrough — not a UI journey"),
}


def _playbook_files() -> set[str]:
    """Return all playbook filenames under the walkthrough dir (minus README)."""
    return {path.name for path in _PLAYBOOK_DIR.glob("*.md") if path.name.lower() != "readme.md"}


@pytest.mark.e2e
def test_every_playbook_is_classified() -> None:
    """Every playbook ``*.md`` has a coverage-ledger entry (the ratchet)."""
    on_disk = _playbook_files()
    missing = on_disk - set(PLAYBOOK_COVERAGE)
    assert not missing, (
        f"playbook(s) without an e2e coverage-ledger entry: {sorted(missing)}; "
        "register a journey (status 'automated') or classify the playbook in "
        "PLAYBOOK_COVERAGE (pending / curl-api / deferred-* / n-a)"
    )


@pytest.mark.e2e
def test_ledger_has_no_stale_entries() -> None:
    """Every ledger entry maps to a real playbook on disk (stays honest)."""
    on_disk = _playbook_files()
    stale = set(PLAYBOOK_COVERAGE) - on_disk
    assert not stale, f"coverage-ledger entries with no matching playbook file: {sorted(stale)}"


@pytest.mark.e2e
def test_ledger_statuses_are_valid() -> None:
    """Every ledger status is valid and carries a non-empty note."""
    for playbook, (status, note) in PLAYBOOK_COVERAGE.items():
        assert status in _VALID_STATUSES, f"{playbook}: invalid status {status!r}"
        assert note, f"{playbook}: missing coverage note"


@pytest.mark.e2e
def test_automated_playbooks_have_journeys() -> None:
    """Each ``automated`` playbook is backed by ≥1 registered journey."""
    automated = {pb for pb, (status, _) in PLAYBOOK_COVERAGE.items() if status == "automated"}
    backed = automated_playbooks()
    unbacked = automated - backed
    assert not unbacked, (
        f"playbook(s) marked 'automated' with no registered journey: {sorted(unbacked)}; "
        "add a Journey to e2e._journeys.JOURNEYS or downgrade the ledger status"
    )


@pytest.mark.e2e
def test_journeys_point_at_automated_playbooks() -> None:
    """Every registered journey points at a playbook marked ``automated``."""
    for journey in JOURNEYS.values():
        entry = PLAYBOOK_COVERAGE.get(journey.playbook)
        assert entry is not None, (
            f"journey {journey.test_id} replays unknown playbook {journey.playbook!r}"
        )
        status, _ = entry
        assert status == "automated", (
            f"journey {journey.test_id} replays {journey.playbook!r} but its ledger "
            f"status is {status!r}, not 'automated'"
        )
