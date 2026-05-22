# pyright: reportPrivateUsage=false
"""The ``_REGISTRY`` dict — concrete :class:`EntityKindSpec` for every kind."""

from __future__ import annotations

from pointlessql.services.social.entity_registry._spec import EntityKindSpec
from pointlessql.services.social.entity_registry._url_builders import (
    _agent_memory_url,
    _branch_url,
    _catalog_url,
    _dp_url,
    _issue_url,
    _model_url,
    _notebook_cell_output_url,
    _notebook_cell_url,
    _notebook_revision_url,
    _notebook_url,
    _run_url,
    _saved_query_url,
    _schema_url,
    _table_url,
    _workspace_url,
)

REGISTRY: dict[str, EntityKindSpec] = {
    "dp": EntityKindSpec(
        key="dp",
        label="Data Product",
        url_for=_dp_url,
        # Locked decision #9: kind='dp' keeps the legacy
        # ``data_product:`` audit-target prefix forever so
        # existing SIEM / Grafana queries on
        # ``target LIKE 'data_product:%'`` keep working.
        audit_target_prefix="data_product",
        supports_reviews=True,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=True,   # Issues against DPs land in 77.7
        supports_stars=False,   # Stars land in 77.8
        tab_keys=(
            "overview",
            "contract",
            "diff",
            "lineage",
            "compliance",
            "activity",
            "discussion",
            "reviews",
            "readme",
            "issues",
        ),
    ),
    # Phase 77.1 — UC tables get Discussion + Endorsements +
    # Followers + README + (later) Stars tabs.  Reviews stay off
    # for now (locked: star ratings only make sense on curated
    # DPs).  Issues opened against tables land in 77.7.
    "table": EntityKindSpec(
        key="table",
        label="Table",
        url_for=_table_url,
        audit_target_prefix="table",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=True,   # Issues opened against tables (77.7)
        supports_stars=True,    # Stars wire-up lands in 77.8
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "readme",
            "issues",
        ),
    ),
    # Phase 77.3 — branches get Discussion + Endorsements +
    # Followers tabs.  The single endorsement type that matters
    # here is ``branch-approved-for-promotion`` — used by the
    # opt-in promote-gate.  77.7 flips ``supports_issues`` to
    # ``True`` so branch quality concerns get a tracked-work
    # surface; README stays off.
    "branch": EntityKindSpec(
        key="branch",
        label="Branch",
        url_for=_branch_url,
        audit_target_prefix="branch",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=False,
        supports_issues=True,
        supports_stars=False,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "issues",
        ),
    ),
    # Phase 77.4 — agent runs get Discussion + Endorsements +
    # Followers tabs.  Reviews / README hidden: runs are transient
    # execution outcomes, not curated artefacts.  Endorsements
    # reuse the DP set ("verified-by-steward", "production-ready",
    # "under-review", "deprecated") so humans can flag quality
    # signals on individual runs.  Issues stay off until 77.7
    # decides whether agent runs are worth the issue-against-run
    # use-case.  Stars wire-up lands in 77.8.
    "run": EntityKindSpec(
        key="run",
        label="Run",
        url_for=_run_url,
        audit_target_prefix="run",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=False,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
        ),
    ),
    # Phase 77.2 (+ 77.2.1) — registered models get Discussion +
    # Reviews + Endorsements + Followers + README tabs.  Reviews
    # was off in the initial 77.2 landing because the polymorphic
    # upsert idempotency required a kind-agnostic UNIQUE on
    # ``(workspace_id, social_target_id, author_user_id)``;
    # 77.2.1's migration added that UNIQUE so the flag flips
    # ``True`` here.  77.7 flips ``supports_issues`` to ``True`` so
    # tracked-work concerns get a model-scoped surface; full Stars
    # wire-up is 77.8.
    "model": EntityKindSpec(
        key="model",
        label="Model",
        url_for=_model_url,
        audit_target_prefix="model",
        supports_reviews=True,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=True,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "reviews",
            "endorsements",
            "followers",
            "readme",
            "issues",
        ),
    ),
    # Phase 77.7 — issues are themselves polymorphic anchors so the
    # issue gets a Discussion thread + endorsements + followers.
    # ``supports_issues`` stays ``False`` (no recursion into nested
    # issues); README stays off too (the issue body itself is the
    # long-form surface).  Stars flip ``True`` so users can bookmark
    # an issue without needing a Follow.
    "issue": EntityKindSpec(
        key="issue",
        label="Issue",
        url_for=_issue_url,
        audit_target_prefix="issue",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=False,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
        ),
    ),
    # Phase 77.5 — UC schemas get Discussion + Endorsements +
    # Followers + README tabs.  Reviews stay off (star-ratings only
    # make sense on curated DPs).  Issues stay off initially; the
    # registry flips if dogfooding asks for schema-scoped issues.
    # Stars flip ``True`` so the catalog-browser star button works
    # server-side without the localStorage fallback.
    "schema": EntityKindSpec(
        key="schema",
        label="Schema",
        url_for=_schema_url,
        audit_target_prefix="schema",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "readme",
        ),
    ),
    # Phase 77.5 — UC catalogs get the same four social tabs as
    # schemas.  Treated as a curated container of schemas: stewards
    # can endorse them, users can subscribe to their event stream,
    # admins can pin a README.  Stars on, issues off, reviews off
    # (same locked decisions as schemas).
    "catalog": EntityKindSpec(
        key="catalog",
        label="Catalog",
        url_for=_catalog_url,
        audit_target_prefix="catalog",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "readme",
        ),
    ),
    # Phase 77.6 — notebooks get a Discussion + Endorsements +
    # Followers + README side-drawer surface (notebook_editor.html
    # is full-screen by design, so we keep the navigation out of
    # the main view).  Reviews off (notebooks aren't curated
    # artefacts the way DPs / models are); issues off initially.
    # Stars on.
    "notebook": EntityKindSpec(
        key="notebook",
        label="Notebook",
        url_for=_notebook_url,
        audit_target_prefix="notebook",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "readme",
        ),
    ),
    # Phase 77.6 — saved queries get the same four social tabs.
    # ``saved_audit_query_detail.html`` is small enough for an
    # inline tab strip (not a side-drawer).  Reviews off; issues
    # off initially; stars on.
    "saved_query": EntityKindSpec(
        key="saved_query",
        label="Saved query",
        url_for=_saved_query_url,
        audit_target_prefix="saved_query",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=True,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
            "readme",
        ),
    ),
    # Phase 90 — agent_memory anchors hang the polymorphic social
    # surface off an agent identifier (one row per agent, the
    # entity_ref is the AgentRun.agent_id string).  Same tab strip
    # as "run" because a memory page is the agent-wide aggregation
    # of run-scoped activity — humans endorse, follow, and discuss
    # but don't review (memory is transient activity, not a curated
    # artefact).  Stars on so users can bookmark agents they
    # supervise.
    "agent_memory": EntityKindSpec(
        key="agent_memory",
        label="Agent memory",
        url_for=_agent_memory_url,
        audit_target_prefix="agent_memory",
        supports_reviews=False,
        supports_endorsements=True,
        supports_readme=False,
        supports_issues=False,
        supports_stars=True,
        tab_keys=(
            "discussion",
            "endorsements",
            "followers",
        ),
    ),
    # Phase 95 — notebook-cell anchors host the inline cell-thread
    # surface (comments + reactions + followers) for a single cell.
    # entity_ref is the composite ``{notebook_uuid}:{cell_uuid}``; the
    # ``cell_uuid`` half is the stable identity minted by the
    # save-path reconciler in
    # ``pointlessql.services.notebook.cell_reconciliation``.  Reviews
    # off (cells aren't curated artefacts); endorsements / READMEs /
    # issues off (overkill at cell scope — Phase 101 will layer
    # reviewer-per-cell on top of the same anchor).  Stars off (cells
    # are notebook-internal; bookmarks live at notebook level).
    "notebook_cell": EntityKindSpec(
        key="notebook_cell",
        label="Notebook cell",
        url_for=_notebook_cell_url,
        audit_target_prefix="notebook_cell",
        supports_reviews=False,
        supports_endorsements=False,
        supports_readme=False,
        supports_issues=False,
        supports_stars=False,
        tab_keys=(
            "discussion",
            "followers",
        ),
    ),
    # Phase 97 Rest — pinned-fact anchors point at a whole notebook
    # revision (``cell_content_hash IS NULL`` on the fact row).  The
    # entity_ref is the fact's 36-char ``fact_uuid``.  Cells aren't
    # curated artefacts at this scope (we treat the *fact* itself as
    # the curated surface), so reviews / endorsements / readmes /
    # issues / stars are all off — the social affordance is "follow
    # the workspace's library activity" which lives on the workspace
    # entity instead.  Discussion + followers still wire so a fact
    # can collect comments and notify watchers.
    "notebook_revision": EntityKindSpec(
        key="notebook_revision",
        label="Pinned fact",
        url_for=_notebook_revision_url,
        audit_target_prefix="notebook_revision",
        supports_reviews=False,
        supports_endorsements=False,
        supports_readme=False,
        supports_issues=False,
        supports_stars=False,
        tab_keys=(
            "discussion",
            "followers",
        ),
    ),
    # Phase 97 Rest — cell-output facts use the same library detail
    # page as whole-revision facts; the differentiating field is
    # ``cell_content_hash`` on the fact row.  Same capability shape.
    "notebook_cell_output": EntityKindSpec(
        key="notebook_cell_output",
        label="Pinned cell output",
        url_for=_notebook_cell_output_url,
        audit_target_prefix="notebook_cell_output",
        supports_reviews=False,
        supports_endorsements=False,
        supports_readme=False,
        supports_issues=False,
        supports_stars=False,
        tab_keys=(
            "discussion",
            "followers",
        ),
    ),
    # Phase 77.10 — workspaces themselves get a Discussion +
    # README surface plus the landing-page tabs (members /
    # activity).  Endorsements off (workspaces aren't curated
    # artefacts the way tables/models are); issues off; stars
    # off — bookmarking a workspace doesn't make sense.
    "workspace": EntityKindSpec(
        key="workspace",
        label="Workspace",
        url_for=_workspace_url,
        audit_target_prefix="workspace",
        supports_reviews=False,
        supports_endorsements=False,
        supports_readme=True,
        supports_issues=False,
        supports_stars=False,
        tab_keys=(
            "discussion",
            "readme",
            "members",
            "activity",
        ),
    ),
}
