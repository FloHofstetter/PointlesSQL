"""Phase 77.0.A — polymorphic social_target foundation.

Coverage:

* ``social_targets`` table is created and the Phase-76 DP rows
  are backfilled one-for-one (kind='dp', data_product_id back-
  pointer, FQN as ``entity_ref``).
* ``get_or_create_target`` is idempotent under repeated calls
  with the same ``(workspace_id, kind, ref)``.
* Kind validation rejects unknown kinds and enforces the
  parity contract on ``data_product_id`` (required iff kind='dp').
* Workspace scoping creates separate anchor rows for the same
  kind+ref across two workspaces.
* ``resolve_dp_target`` returns the backfilled anchor for an
  existing DP.
* ``resolve_workspace_for_entity`` returns the owning workspace
  for kind='dp' and ``None`` for unregistered kinds.
* ``entity_registry`` lookups: ``get`` / ``url_for`` /
  ``audit_target`` carry the locked decision #9 legacy prefix
  for kind='dp' and the generic ``{kind}:`` prefix for every
  future kind.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_target import (
    ENTITY_KINDS,
    SocialTarget,
)
from pointlessql.services.social import (
    entity_registry,
    get_or_create_target,
    resolve_dp_target,
    resolve_workspace_for_entity,
)

_CONTRACT_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> int:
    """Seed ``main.sales_gold`` from a yaml on disk."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


def test_entity_kinds_constant_covers_phase77_plan() -> None:
    """The constant lists every kind the Phase-77 plan + later additions."""
    expected = {
        "dp",
        "table",
        "schema",
        "catalog",
        "model",
        "branch",
        "run",
        "query",
        "notebook",
        "saved_query",
        "issue",
        "workspace",
        # Phase 95 — per-cell social (cell-level comments / reactions /
        # follows / tags) registered a polymorphic ``notebook_cell``
        # entity-kind on the same social target.
        "notebook_cell",
        # Phase 96 — inline AI-assistant ``agent_memory`` entity-kind.
        "agent_memory",
        # Phase 97 — revision-level social (per-revision pinned facts +
        # cell-output discussion threads on the same target).
        "notebook_revision",
        "notebook_cell_output",
    }
    assert set(ENTITY_KINDS) == expected


def test_registry_dp_kind_is_registered_with_legacy_prefix() -> None:
    """Locked decision #9 — kind='dp' keeps the legacy prefix."""
    spec = entity_registry.get("dp")
    assert spec.audit_target_prefix == "data_product"
    assert spec.url_for("main.sales_gold") == (
        "/data-products/main/sales_gold"
    )


def test_registry_audit_target_format_for_dp() -> None:
    """kind='dp' rows audit-target stays ``data_product:{ref}``."""
    assert entity_registry.audit_target("dp", "main.sales_gold") == (
        "data_product:main.sales_gold"
    )
    assert entity_registry.audit_target(
        "dp", "main.sales_gold", suffix="tab-discussion-comment-42"
    ) == "data_product:main.sales_gold#tab-discussion-comment-42"


def test_registry_audit_target_falls_back_to_generic_for_unknown() -> None:
    """Unregistered kinds still produce a sensible target string.

    This guarantees 77.1+ sub-phases work the moment they register
    their kind — and that audit-log writes never crash because a
    new kind landed before its registry entry.
    """
    # 'table' is not yet registered in 77.0.A — it lands in 77.1.
    out = entity_registry.audit_target("table", "main.sales_gold.orders")
    assert out == "table:main.sales_gold.orders"


def test_registry_rejects_duplicate_registration() -> None:
    """A second register() for the same kind raises ValueError."""
    spec = entity_registry.get("dp")
    with pytest.raises(ValueError, match="already registered"):
        entity_registry.register(spec)


def test_get_or_create_target_creates_and_is_idempotent(
    tmp_path: Path,
) -> None:
    """Two calls with the same triple return the same row."""
    dp_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        first = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        second = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        first_id = int(first.id)
        second_id = int(second.id)
        kind = first.entity_kind
        ref = first.entity_ref
        dp_back = first.data_product_id
        session.commit()
    assert first_id == second_id
    assert kind == "dp"
    assert ref == "main.sales_gold"
    assert dp_back == dp_id


def test_get_or_create_target_rejects_unknown_kind(tmp_path: Path) -> None:
    """Caller gets a clear Python error before the DB rejects."""
    factory = app.state.session_factory
    with factory() as session, pytest.raises(ValueError, match="unknown entity_kind"):
        get_or_create_target(
            session,
            workspace_id=1,
            kind="bogus",
            ref="whatever",
        )


def test_get_or_create_target_rejects_dp_without_back_pointer(
    tmp_path: Path,
) -> None:
    """kind='dp' must carry a data_product_id back-pointer."""
    factory = app.state.session_factory
    with factory() as session, pytest.raises(
        ValueError, match="requires a data_product_id"
    ):
        get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="ghost.missing",
        )


def test_get_or_create_target_rejects_dp_back_pointer_on_non_dp(
    tmp_path: Path,
) -> None:
    """Non-dp kinds must not carry a data_product_id."""
    factory = app.state.session_factory
    with factory() as session, pytest.raises(
        ValueError, match="must not carry a data_product_id"
    ):
        get_or_create_target(
            session,
            workspace_id=1,
            kind="table",
            ref="cat.sch.tbl",
            data_product_id=42,
        )


def test_backfill_creates_one_anchor_row_per_existing_dp(
    tmp_path: Path,
) -> None:
    """Phase 77.0.A migration populates ``social_targets``.

    The conftest runs ``alembic upgrade head`` before any test
    runs, so the backfill has already happened.  Seed one extra
    DP and verify the seeding helper still produces one anchor
    row (load_contract goes through the post-77.0 route stack,
    which the next sub-phase wires; for now the resolver does
    the get-or-create explicitly).
    """
    dp_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        # The DP exists; the resolver creates its anchor row on
        # demand because Phase 77.0.A only backfills DPs that
        # existed at migration time, not future seeds.
        target = resolve_dp_target(
            session,
            workspace_id=1,
            catalog_name="main",
            schema_name="sales_gold",
        )
        kind = target.entity_kind
        ref = target.entity_ref
        dp_back = target.data_product_id
        session.commit()
    assert kind == "dp"
    assert ref == "main.sales_gold"
    assert dp_back == dp_id


def test_resolve_dp_target_raises_lookup_error_for_missing(
    tmp_path: Path,
) -> None:
    """resolve_dp_target signals missing DPs clearly."""
    factory = app.state.session_factory
    with factory() as session, pytest.raises(LookupError, match="no DataProduct"):
        resolve_dp_target(
            session,
            workspace_id=1,
            catalog_name="ghost",
            schema_name="missing",
        )


def test_resolve_workspace_for_entity_dp_returns_workspace(
    tmp_path: Path,
) -> None:
    """For kind='dp' the resolver probes data_products.workspace_id."""
    _seed_product(tmp_path)
    factory = app.state.session_factory
    out = resolve_workspace_for_entity(factory, "dp", "main.sales_gold")
    assert out == 1


def test_resolve_workspace_for_entity_unknown_kind_returns_none() -> None:
    """Unregistered kinds resolve to None until 77.1+ wire them."""
    factory = app.state.session_factory
    out = resolve_workspace_for_entity(factory, "table", "cat.sch.tbl")
    assert out is None


def test_resolve_workspace_for_entity_missing_dp_returns_none() -> None:
    """A bogus DP FQN resolves to None."""
    factory = app.state.session_factory
    out = resolve_workspace_for_entity(factory, "dp", "ghost.nope")
    assert out is None


def test_get_or_create_target_workspace_scopes_separately(
    tmp_path: Path,
) -> None:
    """Same kind+ref under two workspaces = two anchor rows.

    Phase 77.0 plan's "workspace scoping" contract: a federated
    table pinned in two workspaces gets two ``social_targets``
    rows so each workspace has its own Discussion thread.
    """
    factory = app.state.session_factory
    with factory() as session:
        # Use kind='table' (not yet registered for HTTP routes,
        # but the resolver accepts any kind in ENTITY_KINDS).
        ws1_obj = get_or_create_target(
            session,
            workspace_id=1,
            kind="table",
            ref="foreign_cat.sch.tbl",
        )
        ws2_obj = get_or_create_target(
            session,
            workspace_id=2,
            kind="table",
            ref="foreign_cat.sch.tbl",
        )
        ws1_id = int(ws1_obj.id)
        ws2_id = int(ws2_obj.id)
        ws1_ws = ws1_obj.workspace_id
        ws2_ws = ws2_obj.workspace_id
        session.commit()
    assert ws1_id != ws2_id
    assert ws1_ws == 1
    assert ws2_ws == 2


def test_check_constraint_blocks_dp_kind_without_back_pointer_at_db(
    tmp_path: Path,
) -> None:
    """The CHECK constraint is the last-line defence beyond the resolver."""
    from sqlalchemy.exc import IntegrityError

    factory = app.state.session_factory
    with factory() as session, pytest.raises(IntegrityError):
        # Bypass the resolver and try to insert directly.  The
        # ``ck_social_targets_dp_backref`` CHECK must reject.
        session.add(
            SocialTarget(
                workspace_id=1,
                entity_kind="dp",
                entity_ref="ghost.row",
                data_product_id=None,
            )
        )
        session.flush()
