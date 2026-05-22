"""Base for the :class:`PQL` façade — constructor + per-instance helpers.

Holds the three private attributes (``_client``, ``_engine``,
``_current_run_id``) every PQL method touches, plus the two per-call
helpers (``_unreachable_msg``, ``_branch_remap``).  The Phase-111.7
mixin split keeps these centralised so the per-concern mixins
(``_DataOpsMixin``, ``_GovernanceMixin``) can rely on a stable
contract without redeclaring the attrs each time.
"""

from __future__ import annotations

import os

from soyuz_catalog_client import Client

from pointlessql.config import Settings
from pointlessql.pql.engine import Engine


class PQLBase:
    """Constructor + shared private helpers for the :class:`PQL` façade.

    Concrete public methods live on per-concern mixins.  This base
    declares the three private attributes the mixins read
    (``_client``, ``_engine``, ``_current_run_id``) and centralises
    the soyuz-client construction + branch-aware FQN rewriting.

    See :class:`pointlessql.pql.pql.PQL` for the full docstring on
    constructor semantics.

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

    _client: Client
    _engine: Engine
    _current_run_id: str | None

    def __init__(
        self,
        client: Client | None = None,
        settings: Settings | None = None,
        engine: Engine | str | None = None,
        *,
        principal: str | None = None,
        agent_run_id: str | None = None,
    ) -> None:
        # Lookup the factory functions via the facade module so tests
        # that monkeypatch ``pointlessql.pql.pql.make_soyuz_client``
        # (the documented patch target since Phase 36 first split the
        # file) keep working after Phase 111.7 moved the constructor
        # body into ``_pql_base``.  Direct ``from pointlessql.services
        # .soyuz_client import …`` would freeze the binding at import
        # time and bypass the patch.
        from pointlessql.pql import pql as _facade

        resolved = settings or Settings()
        # Agent-run-id resolution mirrors `principal`.  Explicit
        # kwarg wins; otherwise the runtime sets the env var before
        # exec'ing the agent's `.py`.  ``None`` keeps the interactive
        # PQL path agnostic — no operation rows are emitted.
        self._current_run_id = agent_run_id or os.environ.get("POINTLESSQL_AGENT_RUN_ID")
        if client is not None:
            self._client = client
        else:
            effective = principal or os.environ.get("POINTLESSQL_PRINCIPAL")
            # Forward X-Agent-Run-Id outbound on every UC call so
            # soyuz's audit log can attribute the
            # mutation to the owning run.  ``None`` skips the header.
            if effective:
                self._client = _facade.make_principal_client(
                    resolved, effective, agent_run_id=self._current_run_id
                )
            else:
                self._client = _facade.make_soyuz_client(
                    resolved, agent_run_id=self._current_run_id
                )
        if engine is None:
            self._engine = _facade.make_engine(resolved.delta.engine)
        elif isinstance(engine, str):
            self._engine = _facade.make_engine(engine)
        else:
            self._engine = engine
        # Subprocess-spawned agent notebooks bypass the FastAPI
        # lifespan, so ``get_session_factory()`` would raise on the
        # first ``agent_run_operations`` write.  Lazy-init the
        # metadata DB when a run id was resolved and no factory is
        # bound yet.  ``init_db`` is idempotent under repeated
        # invocations on the same URL — alembic upgrade-to-head is a
        # no-op once head is reached.
        if self._current_run_id:
            from pointlessql.db import get_session_factory, init_db

            try:
                get_session_factory()
            except RuntimeError:
                init_db(resolved.db.url)

    def _unreachable_msg(self) -> str:
        """Build a user-friendly message when soyuz-catalog is unreachable."""
        url = self._client._base_url  # pyright: ignore[reportPrivateUsage]
        return f"Cannot reach soyuz-catalog at {url}. Is the server running?"

    def _branch_remap(self, full_name: str) -> str:
        """Rewrite a 3-part FQN into the bound branch's sibling schema.

        Phase 102 records the branch binding metadata; this remap is
        the Phase 102 Wave-D kernel-side bridge.  When
        :func:`pointlessql.pql.context.current_branch` returns ``None``
        (interactive use outside the editor, or no active binding),
        the FQN passes through unchanged.

        Args:
            full_name: Caller-supplied ``catalog.schema.table``.

        Returns:
            ``catalog.<branch_name>.table`` when a binding is active;
            else *full_name* unchanged.  Two-part / one-part names
            pass through too — only true 3-part names get remapped.
        """
        from pointlessql.pql.context import current_branch

        branch = current_branch()
        if not branch:
            return full_name
        parts = full_name.split(".")
        if len(parts) != 3:
            return full_name
        catalog, _schema, table = parts
        return f"{catalog}.{branch}.{table}"
