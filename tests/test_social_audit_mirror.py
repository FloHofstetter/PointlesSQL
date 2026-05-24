"""generic audit_mirror helper.

Coverage:

* ``mirror_social_to_audit`` writes an ``audit_log`` row whose
  ``target`` column carries the legacy ``data_product:{ref}``
  prefix for ``entity_kind='dp'`` (locked decision #9).
* For every other kind the target uses the generic
  ``{kind}:{ref}`` format.
* The suffix is appended after a ``#`` separator.
* ``detail`` JSON auto-injects ``entity_kind`` + ``entity_ref``
  so downstream consumers can route by kind without re-parsing.
* Caller-supplied detail keys win over the auto-injected ones
  (the helper does not overwrite explicit values).
* Workspace + actor_role are threaded through.
"""

from __future__ import annotations

import json

from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.audit._log import AuditLog
from pointlessql.services.social import mirror_social_to_audit


def _latest_audit(*, action: str) -> AuditLog:
    """Return the most recent audit row for *action*."""
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        ).scalar_one()
        # Eager-load the detail so it survives session close.
        _ = row.detail
        _ = row.target
        return row


def test_mirror_writes_legacy_prefix_for_dp_kind() -> None:
    """kind='dp' rows keep the ``data_product:`` prefix forever."""
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="test@phase77c.example",
        action="phase77c.test.legacy_prefix",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        suffix="tab-discussion-comment-42",
        detail={"comment_id": 42},
        workspace_id=1,
    )
    row = _latest_audit(action="phase77c.test.legacy_prefix")
    assert row.target == (
        "data_product:main.sales_gold#tab-discussion-comment-42"
    )


def test_mirror_writes_generic_prefix_for_non_dp_kinds() -> None:
    """kind='table' (and every future kind) uses the generic form."""
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="test@phase77c.example",
        action="phase77c.test.generic_prefix",
        entity_kind="table",
        entity_ref="main.sales_gold.orders",
        suffix="tab-discussion-comment-7",
        workspace_id=1,
    )
    row = _latest_audit(action="phase77c.test.generic_prefix")
    assert row.target == (
        "table:main.sales_gold.orders#tab-discussion-comment-7"
    )


def test_mirror_auto_injects_entity_kind_and_ref_into_detail() -> None:
    """``detail`` carries kind+ref so consumers can route without parsing."""
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="test@phase77c.example",
        action="phase77c.test.detail_injection",
        entity_kind="model",
        entity_ref="cat.sch.gradient_boost",
        detail={"version": 3},
        workspace_id=1,
    )
    row = _latest_audit(action="phase77c.test.detail_injection")
    assert row.detail is not None
    payload = json.loads(row.detail)
    assert payload["entity_kind"] == "model"
    assert payload["entity_ref"] == "cat.sch.gradient_boost"
    assert payload["version"] == 3


def test_mirror_caller_detail_wins_over_auto_injection() -> None:
    """Explicit kind/ref keys in detail are not overwritten.

    The helper uses ``setdefault`` so a caller can override the
    auto-injected fields (e.g. record a *target* entity that
    differs from the social_target row, like cross-DP citation
    rows that name two entities).
    """
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="test@phase77c.example",
        action="phase77c.test.detail_override",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        detail={"entity_kind": "table", "comment_id": 99},
        workspace_id=1,
    )
    row = _latest_audit(action="phase77c.test.detail_override")
    assert row.detail is not None
    payload = json.loads(row.detail)
    assert payload["entity_kind"] == "table"  # caller's value wins
    assert payload["entity_ref"] == "main.sales_gold"
    assert payload["comment_id"] == 99


def test_mirror_threads_workspace_and_actor_role() -> None:
    """Workspace + actor_role land on the row."""
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="bot@phase77c.example",
        action="phase77c.test.role_threading",
        entity_kind="branch",
        entity_ref="main.sales_gold__branch_xyz",
        workspace_id=2,
        actor_role="system",
    )
    row = _latest_audit(action="phase77c.test.role_threading")
    assert row.workspace_id == 2
    assert row.actor_role == "system"


def test_mirror_omits_suffix_cleanly() -> None:
    """No suffix → no trailing ``#`` in target."""
    factory = app.state.session_factory
    mirror_social_to_audit(
        factory,
        user_id=0,
        user_email="test@phase77c.example",
        action="phase77c.test.no_suffix",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
    )
    row = _latest_audit(action="phase77c.test.no_suffix")
    assert row.target == "data_product:main.sales_gold"
    assert "#" not in row.target
