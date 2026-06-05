"""Behaviour tests targeting surviving mutants in policy CRUD + resolution.

Pins the observable contract of the product/workspace policy upsert
helpers and the JSON-decode fallback in :func:`_row_values`: the exact
value returned for an undecodable ``linked_policy_module_ids`` string,
the editor/timestamp columns written on an upsert, the value echoed back
from a write, and the workspace scoping of a freshly-inserted row.  Each
test asserts an output a surviving mutant would change.
"""

from __future__ import annotations

import datetime
import json

from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductPolicy,
    Workspace,
    WorkspaceGovernancePolicy,
)
from pointlessql.services.governance import _policy


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    """Insert a minimal DataProduct row; return its id."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_workspace(workspace_id: int, slug: str) -> None:
    """Insert a bare Workspace row so FK targets exist for policy rows."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            Workspace(
                id=workspace_id,
                slug=slug,
                name=slug,
                created_at=now,
            )
        )
        session.commit()


# ---------------------------------------------------------------------------
# _row_values — undecodable linked_policy_module_ids resolves to None
# ---------------------------------------------------------------------------


def test_row_values_invalid_linked_ids_json_resolves_to_none() -> None:
    """A non-JSON ``linked_policy_module_ids`` string decodes to ``None``.

    The except-branch must overwrite the ``linked_policy_module_ids``
    key with ``None`` — not the empty string, and not a differently-cased
    key that would leave the raw string in place.
    """
    dp_id = _seed_dp("main", "lpm_bad")
    written = _policy.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"linked_policy_module_ids": "not-json"},
    )
    # Echoed write value: exactly None (not "" and not the raw "not-json").
    assert written["linked_policy_module_ids"] is None
    assert written["linked_policy_module_ids"] != ""
    assert written["linked_policy_module_ids"] != "not-json"
    # And the same on a fresh read through get_product_policy.
    fetched = _policy.get_product_policy(_factory(), data_product_id=dp_id)
    assert fetched["linked_policy_module_ids"] is None


def test_row_values_valid_linked_ids_json_decodes_to_list() -> None:
    """A JSON-encoded id list round-trips back to a ``list[int]``."""
    dp_id = _seed_dp("main", "lpm_good")
    written = _policy.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"linked_policy_module_ids": json.dumps([3, 5])},
    )
    assert written["linked_policy_module_ids"] == [3, 5]


# ---------------------------------------------------------------------------
# set_product_policy — persisted actor, timestamp, and echoed value
# ---------------------------------------------------------------------------


def test_set_product_policy_persists_editor_and_returns_written_field() -> None:
    dp_id = _seed_dp("main", "spp_actor")
    written = _policy.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"retention_days": 30},
        updated_by_user_id=11,
    )
    # The return mirrors the just-written field — a mutant that returns
    # _row_values(None) would surface all-None instead.
    assert written["retention_days"] == 30
    with _factory()() as session:
        row = session.scalar(
            select(DataProductPolicy).where(DataProductPolicy.data_product_id == dp_id)
        )
        assert row is not None
        # The editor id is stamped from the argument, not nulled out.
        assert row.updated_by_user_id == 11
        assert row.retention_days == 30
        # The insert path stamps a non-null updated_at.
        assert row.updated_at is not None


def test_set_product_policy_null_editor_is_recorded() -> None:
    """Omitting the editor leaves ``updated_by_user_id`` NULL, not stale."""
    dp_id = _seed_dp("main", "spp_null_actor")
    # First write with an editor, then a second write without one must
    # clear it back to NULL (the assignment always runs).
    _policy.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"retention_days": 10},
        updated_by_user_id=42,
    )
    _policy.set_product_policy(
        _factory(),
        data_product_id=dp_id,
        fields={"retention_days": 20},
    )
    with _factory()() as session:
        row = session.scalar(
            select(DataProductPolicy).where(DataProductPolicy.data_product_id == dp_id)
        )
        assert row is not None
        assert row.updated_by_user_id is None
        assert row.retention_days == 20


# ---------------------------------------------------------------------------
# set_workspace_policy — scoping, editor, echoed value, single row
# ---------------------------------------------------------------------------


def test_set_workspace_policy_scopes_row_to_given_workspace() -> None:
    """The inserted row is bound to the requested workspace id.

    A mutant that drops the ``workspace_id`` kwarg falls back to the
    column's server default (1); a mutant that passes ``None`` violates
    the NOT NULL constraint.  Writing for workspace 2 and asserting the
    persisted value is 2 distinguishes both from the original.
    """
    _seed_workspace(2, "ws-two")
    written = _policy.set_workspace_policy(
        _factory(),
        workspace_id=2,
        fields={"retention_days": 90},
        updated_by_user_id=7,
    )
    # The echoed value reflects the written field, not _row_values(None).
    assert written["retention_days"] == 90
    with _factory()() as session:
        rows = list(session.scalars(select(WorkspaceGovernancePolicy)).all())
        # Exactly one row, scoped to workspace 2, with the editor stamped.
        assert len(rows) == 1
        assert rows[0].workspace_id == 2
        assert rows[0].retention_days == 90
        assert rows[0].updated_by_user_id == 7
        assert rows[0].updated_at is not None


def test_set_workspace_policy_default_workspace_distinct_from_other() -> None:
    """Two workspaces get two independently-scoped rows.

    Pins that the workspace id actually threads through: writing for
    workspace 1 and workspace 2 must yield two rows with the matching
    ids, not two rows collapsed onto the server-default workspace.
    """
    _seed_workspace(2, "ws-distinct")
    _policy.set_workspace_policy(_factory(), workspace_id=1, fields={"retention_days": 11})
    _policy.set_workspace_policy(_factory(), workspace_id=2, fields={"retention_days": 22})
    with _factory()() as session:
        rows = {
            r.workspace_id: r.retention_days
            for r in session.scalars(select(WorkspaceGovernancePolicy)).all()
        }
    assert rows == {1: 11, 2: 22}


def test_set_workspace_policy_returns_written_field() -> None:
    """The write echoes the field values, not an all-None placeholder."""
    written = _policy.set_workspace_policy(
        _factory(),
        workspace_id=1,
        fields={"retention_days": 45, "residency_region": "eu-central"},
    )
    assert written["retention_days"] == 45
    assert written["residency_region"] == "eu-central"
