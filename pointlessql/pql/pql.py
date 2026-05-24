# pyright: reportPrivateUsage=false
"""Sync bridge between Unity Catalog metadata and Delta Lake DataFrames — public façade.

The :class:`PQL` class is the public façade — the bulk of its method
bodies delegates to sibling helper modules (``_read``, ``_write``,
``_merge``, …).  Phase 111.7 split the 1060-LOC class definition into
three per-concern files behind it:

* :mod:`._pql_base`        — :class:`PQLBase` (constructor + the two
  private helpers ``_unreachable_msg`` / ``_branch_remap``).
* :mod:`._pql_data`        — :class:`_DataOpsMixin` (table reads, SQL,
  write_table, merge, update, delete, aggregate, autoload, vector,
  list, widgets).
* :mod:`._pql_governance`  — :class:`_GovernanceMixin` (training-context,
  rollback, the four branch lifecycle methods).

The mixin order matters only for MRO: ``_DataOpsMixin`` first means a
hypothetical name collision between mixins would resolve to the data-
ops side, but there are no overlaps today.  ``PQL`` itself adds no new
methods — it exists purely as the named import surface.

``SQLResult`` is re-exported from this module so existing
``from pointlessql.pql.pql import SQLResult`` callers (notably the
test suite) continue to resolve unchanged.
"""

from __future__ import annotations

from pointlessql.pql._pql_data import _DataOpsMixin
from pointlessql.pql._pql_governance import _GovernanceMixin
from pointlessql.pql._types import SQLResult
from pointlessql.pql.engine import make_engine
from pointlessql.services.soyuz_client import make_principal_client, make_soyuz_client

# Re-exported at module scope so the established test patch targets
# (``pointlessql.pql.pql.make_soyuz_client`` etc.) keep working after
# moved the constructor body to ``_pql_base``.  The base
# resolves these via call-time lookup on this facade module.
__all__ = [
    "PQL",
    "SQLResult",
    "make_engine",
    "make_principal_client",
    "make_soyuz_client",
]


class PQL(_DataOpsMixin, _GovernanceMixin):
    """Sync bridge between Unity Catalog metadata and Delta Lake DataFrames.

    Designed for interactive use in notebooks and scripts.  All methods
    are synchronous — the web UI's async wrapper
    (``pointlessql.services.unitycatalog``) is a separate concern.

    When the ``POINTLESSQL_PRINCIPAL`` environment variable is set
    and no explicit ``client`` is passed, the constructor builds a
    principal-forwarded client via ``make_principal_client()`` so
    every catalog call carries an ``X-Principal`` header.  The
    Papermill executor uses this to make notebook code that
    instantiates ``PQL()`` inherit the job's run-as user without
    any extra wiring — regular interactive use is unaffected.

    The constructor also accepts an explicit ``principal`` argument
    so a Hermes plugin (or any other process spawning PQL
    programmatically) can pass the agent's principal without
    mutating the process env.  Resolution order: explicit ``client``
    wins; otherwise an explicit ``principal`` argument; otherwise
    the ``POINTLESSQL_PRINCIPAL`` env var; otherwise an unforwarded
    client.

    Lazy metadata-DB initialisation: when the agent runtime spawns
    the ``.py`` as a subprocess the FastAPI lifespan never runs, so
    the audit-trail writes from :meth:`autoload` / :meth:`merge` /
    :meth:`write_table` would raise
    ``RuntimeError("Database not initialised — call init_db() first")``.
    If a run id is resolved (explicit ``agent_run_id`` or env) and
    the session factory is unbound, ``__init__`` lazy-calls
    :func:`pointlessql.db.init_db` against ``settings.db.url`` so
    agent-authored notebooks need no DB-init boilerplate.  The
    interactive path stays untouched because it is gated on
    ``self._current_run_id``.

    Args:
        client: An existing ``soyuz_catalog_client.Client`` instance.
            When ``None``, one is built via ``make_soyuz_client()`` (or
            ``make_principal_client()`` if a principal is found).
        settings: Optional ``Settings`` override.  Used for both
            client creation and engine selection when not provided
            explicitly.
        engine: Engine instance, engine name string, or ``None``.
            When ``None``, auto-selects from ``settings.delta.engine``
            (default ``"pandas"``).
        principal: Explicit X-Principal value forwarded on every UC
            call.  Wins over ``POINTLESSQL_PRINCIPAL``.  ``None``
            falls back to the env var.
        agent_run_id: Explicit run UUID; every PQL primitive call
            writes one ``agent_run_operations`` row for forced-audit
            purposes.  Wins over ``POINTLESSQL_AGENT_RUN_ID``;
            ``None`` keeps the interactive path silent.
    """
