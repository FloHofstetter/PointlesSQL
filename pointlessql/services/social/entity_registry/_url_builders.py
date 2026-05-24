# pyright: reportUnusedFunction=false
"""Per-kind URL builders — map ``entity_ref`` to the canonical frontend route.

One function per registered entity kind.  All are module-private
helpers consumed by :mod:`._registry_data` when it instantiates the
``_REGISTRY`` dict.  Each builder defends against malformed refs by
returning the kind's index page so audit-log row rendering never
crashes on a partially-migrated row.
"""

from __future__ import annotations


def _dp_url(entity_ref: str) -> str:
    """Map ``cat.sch`` to the data-product detail URL."""
    parts = entity_ref.split(".", 1)
    if len(parts) != 2:
        return "/data-products"
    return f"/data-products/{parts[0]}/{parts[1]}"


def _table_url(entity_ref: str) -> str:
    """Map ``cat.sch.tbl`` to the UC table detail URL.

    tables live under the UC catalog browser at
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

    branches are referenced by their full schema
    FQN (e.g. ``catalog.schema__branch_xxx``).  The detail page
    lives at ``/branches/{fqn}`` so the registry's URL builder
    can drop straight into the existing route.
    """
    return f"/branches/{entity_ref}"


def _model_url(entity_ref: str) -> str:
    """Map a registered-model full_name to its detail URL.

    registered models (UC ML registry) are addressed
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

    agent runs are addressed by the
    ``agent_runs.id`` UUID stored as a 36-char string.  The detail
    page lives at ``/runs/{run_id}``.  Falls back to the runs
    index on malformed refs so audit-log rendering never crashes.
    """
    if len(entity_ref) != 36 or entity_ref.count("-") != 4:
        return "/runs"
    return f"/runs/{entity_ref}"


def _issue_url(entity_ref: str) -> str:
    """Map a numeric issue id to its detail URL.

    issues are referenced by their integer primary key
    serialised as a base-10 string.  The detail page lives at
    ``/issues/{id}``.  Falls back to the issues index on malformed
    refs so audit-log rendering never crashes.
    """
    if not entity_ref.isdigit():
        return "/issues"
    return f"/issues/{entity_ref}"


def _schema_url(entity_ref: str) -> str:
    """Map ``cat.sch`` to the UC schema detail URL.

    schemas live under the UC catalog browser at
    ``/catalogs/{cat}/schemas/{sch}``.  Falls back to the catalogs
    index on malformed refs so audit-log rendering never crashes.
    """
    parts = entity_ref.split(".", 1)
    if len(parts) != 2 or not all(parts):
        return "/catalogs"
    return f"/catalogs/{parts[0]}/schemas/{parts[1]}"


def _catalog_url(entity_ref: str) -> str:
    """Map a catalog name to its detail URL.

    catalogs live at ``/catalogs/{name}`` in the UC
    browser.  Falls back to the catalogs index when the ref is
    empty so audit-log rendering never crashes.
    """
    if not entity_ref:
        return "/catalogs"
    return f"/catalogs/{entity_ref}"


def _notebook_url(entity_ref: str) -> str:
    """Map a notebook UUID to its UUID-routed editor URL.

    notebooks are addressed by the 36-char UUID stored
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

    saved queries live at ``/audit/queries/{slug}``.
    Falls back to the queries index on empty refs.
    """
    if not entity_ref:
        return "/audit/queries"
    return f"/audit/queries/{entity_ref}"


def _agent_memory_url(entity_ref: str) -> str:
    """Map an agent_id to its memory page URL.

    agent memory pages live at ``/memory/{agent_id}``.
    Falls back to the agents index on empty refs so audit-log
    rendering never crashes.
    """
    if not entity_ref:
        return "/agents"
    return f"/memory/{entity_ref}"


def _notebook_cell_url(entity_ref: str) -> str:
    """Map a notebook-cell composite ref to its in-editor anchor URL.

    notebook-cell anchors use the composite
    ``"{notebook_uuid}:{cell_uuid}"`` ref shape so a citation can
    deep-link to the cell inside the notebook editor.  Falls back to
    the notebooks index on malformed refs so audit-log rendering
    never crashes.
    """
    if not entity_ref or ":" not in entity_ref:
        return "/notebooks"
    notebook_uuid, _, cell_uuid = entity_ref.partition(":")
    if not notebook_uuid or not cell_uuid:
        return "/notebooks"
    return f"/notebooks/uuid/{notebook_uuid}?cell={cell_uuid}"


def _notebook_revision_url(entity_ref: str) -> str:
    """Map a fact-uuid to the library facts detail URL.

    pinned facts (whole-revision flavour) are
    addressed by their 36-char ``fact_uuid`` so the social anchor
    deep-links into the workspace library at ``/library/facts/{uuid}``.
    Falls back to the library index on malformed refs so audit-log
    rendering never crashes.
    """
    if len(entity_ref) != 36 or entity_ref.count("-") != 4:
        return "/library/facts"
    return f"/library/facts/{entity_ref}"


def _notebook_cell_output_url(entity_ref: str) -> str:
    """Map a cell-output fact uuid to its library detail URL.

    cell-output facts share the library detail page
    with whole-revision facts; the page itself decides whether to
    render the result snapshot.  Same shape as
    :func:`_notebook_revision_url`.
    """
    if len(entity_ref) != 36 or entity_ref.count("-") != 4:
        return "/library/facts"
    return f"/library/facts/{entity_ref}"


def _workspace_url(entity_ref: str) -> str:
    """Map a workspace slug to its landing page URL.

    workspace landing pages live at
    ``/workspaces/{slug}``.  Falls back to the workspaces index
    on empty refs.
    """
    if not entity_ref:
        return "/workspaces"
    return f"/workspaces/{entity_ref}"
