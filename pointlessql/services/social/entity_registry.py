"""Polymorphic entity registry (Phase 77.0).

Single source of truth for what each ``entity_kind`` means in
the social layer.  Every later Phase-77 sub-phase that adds a
new entity kind (tables, models, branches, runs, …) registers
one :class:`EntityKindSpec` here and the rest of the social
plumbing — citation tokens, audit-target builders, URL routers,
tab strips — keys off this registry by `kind` string.

Phase 77.0 only registers the ``dp`` kind so end-user behavior
stays identical.  Tables / models / branches / etc. land in
their respective sub-phases.

Capability flags (``supports_*``) drive the per-entity tab
strip on the frontend.  A kind with ``supports_reviews=False``
hides the Reviews tab; ``supports_issues=False`` hides Issues;
``supports_readme=False`` hides README.  Defaults match the
DP-social Phase-76 shape so dropping the registry for a new
kind always *adds* capabilities, never accidentally removes
them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class EntityKindSpec:
    """Capability + addressing shape for one ``entity_kind``.

    Attributes:
        key: The discriminator string stored on
            :class:`SocialTarget.entity_kind`.  Must match one of
            :data:`pointlessql.models.social.ENTITY_KINDS`.
        label: Human-readable name for the entity class.  Used
            in audit-log target prefixes (post-77.0 generic form)
            and admin UIs.
        url_for: Callable that maps ``entity_ref`` to the
            canonical frontend route — e.g. for ``kind='dp'``,
            ``"main.sales" -> "/data-products/main/sales"``.
        audit_target_prefix: The string emitted as the
            ``audit_log.target`` column's leading prefix.  For
            ``kind='dp'`` this is the legacy ``data_product:``
            (locked decision #9 of the Phase-77 plan).  For every
            other kind it defaults to ``{key}:``.
        supports_reviews: ``True`` if the kind exposes a Reviews
            tab (star ratings).  Tables / branches / runs default
            to ``False``.
        supports_endorsements: ``True`` if the kind exposes
            steward endorsements.  Most kinds default to ``True``.
        supports_readme: ``True`` if the kind has a long-form
            polymorphic README (rendered alongside any
            short-form catalog comment).
        supports_issues: ``True`` if the kind can have GitHub-
            style tracked issues opened against it.
        supports_stars: ``True`` if the kind can be bookmarked
            via the lightweight Stars primitive.
        tab_keys: Ordered tuple of tab-key strings that the
            ``socialTabs`` Alpine factory renders for this kind.
            Driven by the ``supports_*`` flags but pinned here
            so the front-end has a stable contract.
    """

    key: str
    label: str
    url_for: Callable[[str], str]
    audit_target_prefix: str
    supports_reviews: bool = True
    supports_endorsements: bool = True
    supports_readme: bool = True
    supports_issues: bool = True
    supports_stars: bool = True
    tab_keys: tuple[str, ...] = field(
        default=(
            "discussion",
            "reviews",
            "endorsements",
            "followers",
            "readme",
            "issues",
        )
    )


def _dp_url(entity_ref: str) -> str:
    """Map ``cat.sch`` to the data-product detail URL."""
    parts = entity_ref.split(".", 1)
    if len(parts) != 2:
        return "/data-products"
    return f"/data-products/{parts[0]}/{parts[1]}"


def _table_url(entity_ref: str) -> str:
    """Map ``cat.sch.tbl`` to the UC table detail URL.

    Phase 77.1 — tables live under the UC catalog browser at
    ``/catalogs/{cat}/schemas/{sch}/tables/{tbl}``.  Federated
    tables share the same route so the social tabs work across
    every UC backend.  Returns a safe fallback when the ref is
    malformed so audit-log rendering never crashes.
    """
    parts = entity_ref.split(".", 2)
    if len(parts) != 3:
        return "/catalogs"
    return f"/catalogs/{parts[0]}/schemas/{parts[1]}/tables/{parts[2]}"


def _branch_url(entity_ref: str) -> str:
    """Map a branch FQN to the branch detail URL.

    Phase 77.3 — branches are referenced by their full schema
    FQN (e.g. ``catalog.schema__branch_xxx``).  The detail page
    lives at ``/branches/{fqn}`` so the registry's URL builder
    can drop straight into the existing route.
    """
    return f"/branches/{entity_ref}"


def _model_url(entity_ref: str) -> str:
    """Map a registered-model full_name to its detail URL.

    Phase 77.2 — registered models (UC ML registry) are addressed
    by their three-part ``catalog.schema.name`` full_name.  The
    MLflow-backed detail page lives at ``/models/{full_name}`` so
    the registry's URL builder mirrors the live HTML route and
    falls back to the models index on malformed refs.
    """
    parts = entity_ref.split(".", 2)
    if len(parts) != 3 or not all(parts):
        return "/models"
    return f"/models/{entity_ref}"


def _run_url(entity_ref: str) -> str:
    """Map an agent-run UUID to its detail URL.

    Phase 77.4 — agent runs are addressed by the
    ``agent_runs.id`` UUID stored as a 36-char string.  The detail
    page lives at ``/runs/{run_id}``.  Falls back to the runs
    index on malformed refs so audit-log rendering never crashes.
    """
    if len(entity_ref) != 36 or entity_ref.count("-") != 4:
        return "/runs"
    return f"/runs/{entity_ref}"


def _issue_url(entity_ref: str) -> str:
    """Map a numeric issue id to its detail URL.

    Phase 77.7 — issues are referenced by their integer primary key
    serialised as a base-10 string.  The detail page lives at
    ``/issues/{id}``.  Falls back to the issues index on malformed
    refs so audit-log rendering never crashes.
    """
    if not entity_ref.isdigit():
        return "/issues"
    return f"/issues/{entity_ref}"


def _schema_url(entity_ref: str) -> str:
    """Map ``cat.sch`` to the UC schema detail URL.

    Phase 77.5 — schemas live under the UC catalog browser at
    ``/catalogs/{cat}/schemas/{sch}``.  Falls back to the catalogs
    index on malformed refs so audit-log rendering never crashes.
    """
    parts = entity_ref.split(".", 1)
    if len(parts) != 2 or not all(parts):
        return "/catalogs"
    return f"/catalogs/{parts[0]}/schemas/{parts[1]}"


def _catalog_url(entity_ref: str) -> str:
    """Map a catalog name to its detail URL.

    Phase 77.5 — catalogs live at ``/catalogs/{name}`` in the UC
    browser.  Falls back to the catalogs index when the ref is
    empty so audit-log rendering never crashes.
    """
    if not entity_ref:
        return "/catalogs"
    return f"/catalogs/{entity_ref}"


def _notebook_url(entity_ref: str) -> str:
    """Map a notebook UUID to its UUID-routed editor URL.

    Phase 77.6 — notebooks are addressed by the 36-char UUID stored
    on ``notebooks.id``.  The UUID-routed alias
    ``/notebooks/uuid/{uuid}`` redirects to the path-based editor
    URL after looking up ``file_path`` from the metadata row.
    Falls back to the notebooks index on malformed refs.
    """
    if len(entity_ref) != 36 or entity_ref.count("-") != 4:
        return "/notebooks"
    return f"/notebooks/uuid/{entity_ref}"


def _saved_query_url(entity_ref: str) -> str:
    """Map a saved-query slug to its audit-tab URL.

    Phase 77.6 — saved queries live at ``/audit/queries/{slug}``.
    Falls back to the queries index on empty refs.
    """
    if not entity_ref:
        return "/audit/queries"
    return f"/audit/queries/{entity_ref}"


def _agent_memory_url(entity_ref: str) -> str:
    """Map an agent_id to its memory page URL.

    Phase 90 — agent memory pages live at ``/memory/{agent_id}``.
    Falls back to the agents index on empty refs so audit-log
    rendering never crashes.
    """
    if not entity_ref:
        return "/agents"
    return f"/memory/{entity_ref}"


def _workspace_url(entity_ref: str) -> str:
    """Map a workspace slug to its landing page URL.

    Phase 77.10 — workspace landing pages live at
    ``/workspaces/{slug}``.  Falls back to the workspaces index
    on empty refs.
    """
    if not entity_ref:
        return "/workspaces"
    return f"/workspaces/{entity_ref}"


_REGISTRY: dict[str, EntityKindSpec] = {
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


def register(spec: EntityKindSpec) -> None:
    """Register a new entity-kind spec.

    Args:
        spec: The kind specification to add.

    Raises:
        ValueError: If a spec with the same ``key`` is already
            registered.  Re-registration is rejected so a sloppy
            import order can't silently shadow another sub-phase's
            wiring.
    """
    if spec.key in _REGISTRY:
        msg = f"entity_kind {spec.key!r} already registered"
        raise ValueError(msg)
    _REGISTRY[spec.key] = spec


def get(kind: str) -> EntityKindSpec:
    """Look up the spec for *kind*.

    Args:
        kind: The discriminator string.

    Returns:
        The registered spec.

    Raises:
        KeyError: If no spec is registered for *kind*.  The
            error message names the kind so callers can
            distinguish "unregistered" from "misspelled".
    """
    spec = _REGISTRY.get(kind)
    if spec is None:
        msg = f"entity_kind {kind!r} is not registered"
        raise KeyError(msg)
    return spec


def all_kinds() -> tuple[str, ...]:
    """Return every registered kind key in registration order."""
    return tuple(_REGISTRY.keys())


def url_for(kind: str, entity_ref: str) -> str:
    """Build the frontend URL for ``(kind, entity_ref)``.

    Args:
        kind: The discriminator string.
        entity_ref: The entity reference string.

    Returns:
        The route under which the entity's detail page lives.
        Falls back to ``/`` if the kind is unregistered — the
        caller is expected to validate first; this fallback only
        protects against partially-migrated audit-log rows.
    """
    try:
        spec = get(kind)
    except KeyError:
        return "/"
    return spec.url_for(entity_ref)


def audit_target(kind: str, entity_ref: str, suffix: str | None = None) -> str:
    """Build the ``audit_log.target`` column value for an entity.

    Args:
        kind: The discriminator string.
        entity_ref: The entity reference string.
        suffix: Optional trailing fragment (e.g.
            ``tab-discussion-comment-42``) appended after a
            ``#`` separator.

    Returns:
        A string of the form ``{prefix}:{ref}`` or
        ``{prefix}:{ref}#{suffix}``.  Prefix is the kind-specific
        registry entry (``data_product`` for kind='dp' per locked
        decision #9, ``{kind}`` for every other kind).
    """
    try:
        prefix = get(kind).audit_target_prefix
    except KeyError:
        prefix = kind
    base = f"{prefix}:{entity_ref}"
    if suffix:
        return f"{base}#{suffix}"
    return base


__all__: list[str] = [
    "EntityKindSpec",
    "all_kinds",
    "audit_target",
    "get",
    "register",
    "url_for",
]
