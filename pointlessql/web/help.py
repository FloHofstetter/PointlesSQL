"""Contextual help-popover registry.

Single source of truth for the copy that powers the small
``bi-info-circle`` icons across the web UI.  Templates call
``help('<slug>')`` via the Jinja global registered in
:mod:`pointlessql.api.main` and render through the
``frontend/templates/_macros/help_icon.html`` macro.

Slug schema is ``<page>.<topic>`` (lowercase-kebab inside each
component); each entry is a :class:`HelpEntry` carrying

* ``title`` — the popover header (≤ 60 chars)
* ``body`` — 1-3 sentences explaining *what* and *why* (≤ 280 chars,
  the popover renders narrow by default)
* ``learn_more`` — optional mkdocs path (``/concepts/agent-runs/``)
  prefixed at render time with the public docs base URL.

Tests in ``tests/test_help_registry.py`` enforce the length
constraints and resolve every slug declared in templates back to
this registry, so a missing or mistyped slug surfaces in CI rather
than as an empty popover at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpEntry:
    """One help-popover entry.

    Attributes:
        title: Popover header.  Kept short (≤ 60 chars) so the
            Bootstrap-rendered title row does not wrap awkwardly.
        body: 1-3 sentences explaining the concept.  Plain text +
            the Bootstrap default sanitizer's allow-list (``<a>``,
            ``<br>``, ``<strong>``, ``<em>``).  Capped at 280 chars
            because the default popover width is ~270 px.
        learn_more: Optional mkdocs path.  Must start with ``/``
            and resolve under ``https://flohofstetter.github.io/
            PointlesSQL`` at render time.  ``None`` means the
            popover renders without a "Learn more →" link.
    """

    title: str
    body: str
    learn_more: str | None = None


HELP: dict[str, HelpEntry] = {
    "runs.what-is-a-run": HelpEntry(
        title="What is an agent run?",
        body=(
            "A supervised pipeline execution triggered by an "
            "external runtime (Hermes, OpenShell, cron). Every "
            "operation, tool call, and write is captured in the "
            "audit trail."
        ),
        learn_more="/concepts/agent-supervision/",
    ),
    "runs.what-is-an-operation": HelpEntry(
        title="What is an operation?",
        body=(
            "Operations are the unit of supervision inside a run: "
            "one autoload, write, merge, query, or rollback per "
            "row. Errors stop the run; warnings (e.g. lineage-emit "
            "hiccups) annotate the row but keep status=ok."
        ),
        learn_more="/concepts/agent-supervision/",
    ),
    "models.what-is-promotion": HelpEntry(
        title="What is model promotion?",
        body=(
            "Promotion moves a model version from challenger to "
            "champion — the version inference APIs serve. Only "
            "READY versions can be promoted, and every promotion "
            "is logged with promoter, reason, and timestamp."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "branches.what-is-a-delta-branch": HelpEntry(
        title="What is a Delta branch?",
        body=(
            "A zero-copy snapshot of one or more Delta tables, "
            "created so an agent run can write in isolation. "
            "Branches are either promoted (changes merged back to "
            "parent) or discarded — never partially applied."
        ),
        learn_more="/concepts/architecture/",
    ),
    "lineage.what-is-lineage": HelpEntry(
        title="What is lineage?",
        body=(
            "The data-provenance graph: which tables, columns, "
            "and rows fed which downstream artefacts. PointlesSQL "
            "captures table-, column-, row-, and value-level "
            "lineage on every PQL write — readable forwards "
            "(impact analysis) and backwards (root-cause)."
        ),
        learn_more="/concepts/lineage/",
    ),
    # context-panel headers.  One slug per rail section
    # whose panel was rebuilt as a navigable list (Runs / Branches
    # / Workspace / Jobs / Alerts / MLflow).  Header copy explains
    # what the panel actually shows so a newcomer doesn't have to
    # click through every row.
    "runs.context-panel": HelpEntry(
        title="Runs panel",
        body=(
            "Lists the 15 most-recent agent runs grouped by "
            "status: Needs approval (top), Running / Queued, "
            "and Recent. Each row links to its run-detail page "
            "with the full operation + lineage trail."
        ),
        learn_more="/concepts/agent-supervision/",
    ),
    "branches.context-panel": HelpEntry(
        title="Branches panel",
        body=(
            "Lists active and recently-promoted Delta-branches "
            "with their copy-on-write strategy. Active rows are "
            "writable; promoted rows merged back to parent; "
            "discarded rows kept for the audit trail."
        ),
        learn_more="/concepts/architecture/",
    ),
    "workspace.context-panel": HelpEntry(
        title="Workspace panel",
        body=(
            "Flat list of every .py / .ipynb notebook the "
            "scheduler can pick up. Click a row to open the "
            "workspace browser at that path; the Schedule "
            "button on each detail view turns it into a job."
        ),
        learn_more=None,
    ),
    "jobs.context-panel": HelpEntry(
        title="Jobs panel",
        body=(
            "Scheduled jobs split into Active (eligible to run on "
            "schedule) and Paused. The badge per active row is "
            "the most-recent run's status — succeeded, failed, "
            "or running."
        ),
        learn_more="/guides/jobs/",
    ),
    "alerts.context-panel": HelpEntry(
        title="Alerts panel",
        body=(
            "Configured alerts split into Enabled (the cron "
            "schedule fires) and Disabled. Each alert is a "
            "saved SQL query plus a threshold; firings are "
            "fanned out to the alert's destinations."
        ),
        learn_more=None,
    ),
    "mlflow.context-panel": HelpEntry(
        title="MLflow panel",
        body=(
            "Most-recent UC-registered models with their latest "
            "version + status. Click a row for the model "
            "detail view; click the footer link for the "
            "embedded MLflow Tracking UI."
        ),
        learn_more="/concepts/architecture/",
    ),
    "workspace.what-is-a-workspace": HelpEntry(
        title="What is a workspace?",
        body=(
            "A governance container for runs, jobs, dashboards "
            "and audit trails. Catalogs stay global — every "
            "workspace can read any UC catalog — but compliance "
            "data is workspace-isolated."
        ),
        learn_more="/concepts/workspaces/",
    ),
    # Catalog tree + table-detail popovers — eight entries that
    # demystify the lineage / time-travel / column-statistics
    # surfaces a newcomer hits the moment they open a table.
    "catalog.what-is-a-catalog": HelpEntry(
        title="What is a catalog?",
        body=(
            "A Unity-Catalog namespace holding schemas and "
            "tables. Catalogs are install-wide: every workspace "
            "can read any catalog subject to UC privileges."
        ),
        learn_more="/concepts/architecture/",
    ),
    "schemas.what-is-a-schema": HelpEntry(
        title="What is a schema?",
        body=(
            "A second-level UC namespace inside a catalog. "
            "Tables, volumes and registered models live under "
            "schemas; permissions and tags propagate down the "
            "catalog → schema → table tree."
        ),
        learn_more="/concepts/architecture/",
    ),
    "tables.external-vs-managed": HelpEntry(
        title="External vs. managed table",
        body=(
            "Managed tables let UC own the storage path and "
            "lifecycle. External tables reference Delta files "
            "outside UC's storage root — drops only remove the "
            "metadata, not the data."
        ),
        learn_more="/concepts/data-layers/",
    ),
    "tables.row-lineage-badge": HelpEntry(
        title="Row-lineage badge",
        body=(
            "Click any <code>_lineage_row_id</code> to walk the "
            "row's lineage backwards through every PQL write "
            "down to the bronze cell that produced it."
        ),
        learn_more="/concepts/lineage/",
    ),
    "tables.column-trace-badge": HelpEntry(
        title="Column-trace badge",
        body=(
            "The <em>lineage</em> badge next to a column links "
            "to its column-level trace: which upstream columns "
            "fed it, through which transforms, on which run."
        ),
        learn_more="/concepts/lineage/",
    ),
    "tables.time-travel-button": HelpEntry(
        title="Time-travel preview",
        body=(
            "Pick any historical Delta version to preview the "
            "table at that point in time. Read-only — use the "
            "Rollback action on a run-detail page to restore."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "tables.comments-vs-properties": HelpEntry(
        title="Comments vs. properties",
        body=(
            "Comments are the UC-managed prose description; "
            "properties are arbitrary key/value metadata. Both "
            "are versioned and audited but only properties are "
            "machine-queryable in bulk."
        ),
        learn_more="/concepts/architecture/",
    ),
    "tables.column-statistics": HelpEntry(
        title="Column statistics",
        body=(
            "On-demand profile of nullability, distinct count, "
            "min/max and top-5 values per column. Cached against "
            "the current Delta version — re-profile after a "
            "write to refresh."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    # Models index + detail popovers — six anchors covering the
    # registry, versions table, inference lineage, MLflow boundary
    # and the compare-versions page.
    "models.what-is-the-registry": HelpEntry(
        title="What is the model registry?",
        body=(
            "PointlesSQL's view of MLflow-registered models as "
            "first-class UC securables. Browse versions, walk "
            "training/inference lineage and promote champions "
            "without leaving the lakehouse UI."
        ),
        learn_more="/concepts/architecture/",
    ),
    "models.versions-table": HelpEntry(
        title="Model versions",
        body=(
            "Every registered version with its MLflow run, "
            "linked agent run, top metrics and a compare action. "
            "Champion is the version production inference APIs "
            "serve; READY-only can be promoted."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "models.linked-hermes-runs": HelpEntry(
        title="Linked Hermes runs",
        body=(
            "Each model version that was trained inside a "
            "PointlesSQL agent run carries a <code>_pql_link</code> "
            "marker pointing back to that run. Click through to "
            "audit training inputs, params and tool calls."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "models.inference-lineage": HelpEntry(
        title="Inference lineage",
        body=(
            "Prediction tables that were written with "
            "<code>source_model_uri</code> set. The model lineage "
            "DAG walks both ways — from training-input tables "
            "(green) to prediction tables (blue dashes)."
        ),
        learn_more="/concepts/lineage/",
    ),
    "models.mlflow-vs-pointlessql": HelpEntry(
        title="MLflow vs. PointlesSQL",
        body=(
            "MLflow runs the training tracking subprocess; "
            "PointlesSQL is the supervision + audit + UC catalog "
            "layer on top. The MLflow tab embeds MLflow's native "
            "UI, started when <code>POINTLESSQL_MLFLOW_ENABLED=1</code>."
        ),
        learn_more="/concepts/architecture/",
    ),
    "models.compare-versions": HelpEntry(
        title="Compare model versions",
        body=(
            "Side-by-side diff of two versions: status, MLflow "
            "source, params and metrics. Use it to confirm the "
            "challenger beats the champion before flipping the "
            "promotion."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    # Branches detail + audit cockpit + home popovers.  The audit
    # cockpit is the biggest rollout target — anomaly cards,
    # severities, FTS syntax, principal heatmap and the
    # cross-workspace lens all currently muted.
    "audit.what-is-an-anomaly": HelpEntry(
        title="What is an anomaly?",
        body=(
            "A run-level metric (writes, queries, cost, latency) "
            "that crossed its 2σ rolling baseline. Each anomaly "
            "becomes an inbox card you can ack, dismiss or "
            "escalate to a supervisor review."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "audit.severity-warn-vs-critical": HelpEntry(
        title="Severity: warn vs. critical",
        body=(
            "Warn = ≥ 2σ over the rolling baseline. Critical = "
            "≥ 4σ or a hard rule violation (rollback, "
            "external-write, supervisor-overridden). Critical "
            "rows page the on-call channel through audit_sinks."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "audit.anomaly-actions": HelpEntry(
        title="Anomaly actions",
        body=(
            "<strong>Ack</strong> closes the card and records "
            "an audit-of-audit row. <strong>Dismiss</strong> "
            "marks it false-positive and feeds the baseline. "
            "<strong>Escalate</strong> raises a supervisor "
            "review."
        ),
        learn_more="/concepts/agent-supervision/",
    ),
    "audit.fts-query-syntax": HelpEntry(
        title="Audit FTS syntax",
        body=(
            "SQLite FTS5: bare words AND together; quote "
            'phrases (<code>"slow merge"</code>); use '
            "<code>OR</code> for either, <code>NOT</code> to "
            "exclude, <code>NEAR(a b, 5)</code> for proximity."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "audit.principal-summary": HelpEntry(
        title="Principal summary",
        body=(
            "Per-principal heatmap of writes / queries / "
            "rollbacks over the time window. Click a row to "
            "drill into that principal's full audit trail."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "audit.cross-workspace-lens": HelpEntry(
        title="Cross-workspace lens",
        body=(
            "Tenant admins can pass <code>?workspace=all</code> "
            "to read across every workspace. The escalation is "
            "logged with read_kind <code>audit_api_cross_"
            "workspace</code> for after-the-fact review."
        ),
        learn_more="/admin/workspace-management/",
    ),
    "audit.read-kind": HelpEntry(
        title="Read kind",
        body=(
            "Every audit-API call records a <code>read_kind</code> "
            "row in <code>query_history</code> so audits-of-audits "
            "are themselves auditable. Cross-workspace reads "
            "carry a distinct kind."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "branches.preview-tab": HelpEntry(
        title="Branch preview",
        body=(
            "Diff the branch against its parent before promoting: "
            "added rows, deleted rows, changed values, schema "
            "drift. Promotion is pointer-swap so the diff is "
            "your last chance to inspect."
        ),
        learn_more="/concepts/architecture/",
    ),
    "branches.promote-vs-discard": HelpEntry(
        title="Promote vs. discard",
        body=(
            "<strong>Promote</strong> swaps the branch pointer "
            "into the parent — atomic, reversible only by "
            "rolling back. <strong>Discard</strong> leaves the "
            "branch state for audit but never merges."
        ),
        learn_more="/concepts/architecture/",
    ),
    "branches.cleanup-loop": HelpEntry(
        title="Branch cleanup loop",
        body=(
            "Opt-in background sweep that deep-copies cloud "
            "branches before discarding their symlinks. Local-FS "
            "branches GC immediately. Disable per-workspace if "
            "you need long-lived sandbox branches."
        ),
        learn_more="/concepts/architecture/",
    ),
    "home.what-is-the-cockpit": HelpEntry(
        title="Audit cockpit",
        body=(
            "The cockpit is the single place to triage runs, "
            "anomalies, alerts and rollbacks. Cards refresh on "
            "a 30-second interval; click any card to drill "
            "into the underlying inbox or run."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "home.anomaly-cards": HelpEntry(
        title="Anomaly cards",
        body=(
            "Live count of unacked warn / critical anomalies. "
            "The badge link goes straight into the audit inbox "
            "filtered to that severity so triage is one click "
            "away."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    # SQL editor + admin + settings popovers.  Three SQL popovers
    # plus seven admin popovers covering the governance surfaces a
    # tenant admin actually has to operate.
    "sql.run-modes": HelpEntry(
        title="SQL run modes",
        body=(
            "<strong>Preview</strong> runs the query through the "
            "EXPLAIN cost gate first. <strong>Execute</strong> "
            "skips the gate (admin-only). <strong>Schedule</strong> "
            "saves the query as a recurring job."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "sql.saved-queries": HelpEntry(
        title="Saved queries",
        body=(
            "Each saved query is owned by a user and versioned: "
            "the SQL text, parameters and run history are kept "
            "for the audit trail. Sharing is workspace-scoped — "
            "promote to a job to make it cron-driven."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "sql.cost-gate": HelpEntry(
        title="Cost gate",
        body=(
            "Before any non-admin query runs PointlesSQL pulls "
            "DuckDB's <code>EXPLAIN (FORMAT JSON)</code> and "
            "blocks plans whose estimated cost exceeds the "
            "per-workspace ceiling."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "admin.external-writes-review": HelpEntry(
        title="External-writes review",
        body=(
            "Delta commits that landed without a matching "
            "PointlesSQL audit row. An admin reviews each one "
            "and either attributes it to a known principal or "
            "flags it as suspicious."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "admin.audit-sinks": HelpEntry(
        title="Audit sinks",
        body=(
            "Outbound destinations for the audit-event stream: "
            "webhook, S3 bucket, AWS CloudTrail. Sinks fan out "
            "every audit-of-audit, anomaly and rollback event "
            "for offline retention."
        ),
        learn_more="/concepts/audit-trail/",
    ),
    "admin.workspace-pins": HelpEntry(
        title="Workspace catalog pins",
        body=(
            "Cosmetic only — pinning a catalog makes the sidebar "
            "tree pre-expand to it on load. No enforcement: "
            "any workspace can read any catalog subject to UC "
            "privileges."
        ),
        learn_more="/admin/workspace-management/",
    ),
    "admin.api-key-scopes": HelpEntry(
        title="API-key scopes",
        body=(
            "<strong>auditor</strong> reads the audit trail; "
            "<strong>supervisor</strong> approves agent runs and "
            "reviews; <strong>admin</strong> mutates workspaces, "
            "pins, sinks and members."
        ),
        learn_more="/concepts/auth/",
    ),
    "admin.system-keys": HelpEntry(
        title="System keys",
        body=(
            "Install-level secrets — PII-hash key, audit-sink "
            "credentials. Workspace-orthogonal: one key per "
            "tenant, rotated via the admin UI. Never returned "
            "in plaintext after creation."
        ),
        learn_more="/concepts/pii-modes/",
    ),
    "admin.rate-limit-tiers": HelpEntry(
        title="Rate-limit tiers",
        body=(
            "Per-key request quotas. Each tier sets a burst "
            "ceiling and a 1-minute sustained rate; breaching "
            "either returns 429 with the next allowed timestamp "
            "in the <code>Retry-After</code> header."
        ),
        learn_more="/concepts/auth/",
    ),
    "admin.agent-reviews": HelpEntry(
        title="Agent reviews",
        body=(
            "Supervisor approval gates for runs flagged by the "
            "audit aggregator. The supervisor gets a transcript "
            "of operations + tool calls and acks, escalates or "
            "rejects."
        ),
        learn_more="/concepts/agent-supervision/",
    ),
}


def get_help(slug: str) -> HelpEntry:
    """Resolve a help slug to its registry entry.

    Unknown slugs propagate :class:`KeyError` from the underlying
    dict lookup — a typo in a template fails loudly in tests and
    dev rather than silently rendering an empty popover.

    Args:
        slug: The slug used in templates, e.g. ``runs.what-is-a-run``.

    Returns:
        The :class:`HelpEntry` registered for ``slug``.
    """
    return HELP[slug]
