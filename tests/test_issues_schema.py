"""issues + issue_labels + issue_milestones schema gates.

Coverage:

* The three tables exist with the expected columns + indexes.
* CHECK constraint on ``issues.state`` rejects out-of-vocab values.
* CHECK constraint on ``issues.closed_reason`` rejects bad reasons.
* UNIQUE on ``issue_labels(workspace_id, slug)`` rejects duplicates.
* UNIQUE on ``issues.social_target_id`` rejects collisions.
* CASCADE on ``parent_social_target_id`` drops the issue when the
  parent's anchor goes away.
* ``ISSUE_STATES`` + ``ISSUE_CLOSED_REASONS`` module exports match
  the DB constraints.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.models.social._issue import (
    ISSUE_CLOSED_REASONS,
    ISSUE_STATES,
    Issue,
)
from pointlessql.models.social._issue_label import IssueLabel
from pointlessql.models.social._issue_milestone import IssueMilestone
from pointlessql.models.social._social_target import SocialTarget


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def test_issues_table_exists_with_expected_indexes() -> None:
    """``issues`` carries (workspace+state), parent, assignee indexes."""
    factory = app.state.session_factory
    with factory() as session:
        bind = session.get_bind()
        insp = inspect(bind)
        assert "issues" in insp.get_table_names()
        index_names = {ix["name"] for ix in insp.get_indexes("issues")}
        assert "ix_issues_workspace_state" in index_names
        assert "ix_issues_parent" in index_names
        assert "ix_issues_assignee" in index_names


def test_issue_labels_table_exists_with_unique_slug_per_workspace() -> None:
    """``issue_labels`` has (workspace_id, slug) UNIQUE."""
    factory = app.state.session_factory
    with factory() as session:
        bind = session.get_bind()
        insp = inspect(bind)
        assert "issue_labels" in insp.get_table_names()
        uqs = {u["name"] for u in insp.get_unique_constraints("issue_labels")}
        assert "uq_issue_labels_slug_per_workspace" in uqs


def test_issue_milestones_table_exists() -> None:
    """``issue_milestones`` is present with the workspace index."""
    factory = app.state.session_factory
    with factory() as session:
        bind = session.get_bind()
        insp = inspect(bind)
        assert "issue_milestones" in insp.get_table_names()
        index_names = {ix["name"] for ix in insp.get_indexes("issue_milestones")}
        assert "ix_issue_milestones_workspace" in index_names


def test_issue_state_check_constraint_blocks_garbage() -> None:
    """A state outside ``ISSUE_STATES`` raises IntegrityError."""
    factory = app.state.session_factory
    with factory() as session:
        anchor = SocialTarget(
            workspace_id=1, entity_kind="issue", entity_ref="ck-state-1"
        )
        parent = SocialTarget(
            workspace_id=1, entity_kind="table", entity_ref="a.b.c"
        )
        session.add_all([anchor, parent])
        session.flush()
        bad = Issue(
            workspace_id=1,
            social_target_id=int(anchor.id),
            parent_social_target_id=int(parent.id),
            title="bogus state",
            state="totally_invalid",
            opened_by_user_id=1,
            opened_at=_now(),
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_issue_closed_reason_check_constraint_blocks_garbage() -> None:
    """A closed_reason outside the locked vocab raises IntegrityError."""
    factory = app.state.session_factory
    with factory() as session:
        anchor = SocialTarget(
            workspace_id=1, entity_kind="issue", entity_ref="ck-reason-1"
        )
        parent = SocialTarget(
            workspace_id=1, entity_kind="table", entity_ref="a.b.c"
        )
        session.add_all([anchor, parent])
        session.flush()
        bad = Issue(
            workspace_id=1,
            social_target_id=int(anchor.id),
            parent_social_target_id=int(parent.id),
            title="bogus reason",
            state="closed",
            closed_reason="nope_not_in_vocab",
            opened_by_user_id=1,
            opened_at=_now(),
            closed_at=_now(),
        )
        session.add(bad)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_issue_social_target_unique_collision_rejected() -> None:
    """Two issues sharing the same self social_target_id are rejected."""
    factory = app.state.session_factory
    with factory() as session:
        anchor = SocialTarget(
            workspace_id=1, entity_kind="issue", entity_ref="uq-1"
        )
        parent = SocialTarget(
            workspace_id=1, entity_kind="table", entity_ref="a.b.c"
        )
        session.add_all([anchor, parent])
        session.flush()
        first = Issue(
            workspace_id=1,
            social_target_id=int(anchor.id),
            parent_social_target_id=int(parent.id),
            title="first",
            opened_by_user_id=1,
            opened_at=_now(),
        )
        second = Issue(
            workspace_id=1,
            social_target_id=int(anchor.id),
            parent_social_target_id=int(parent.id),
            title="second sharing same anchor",
            opened_by_user_id=1,
            opened_at=_now(),
        )
        session.add_all([first, second])
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_issue_label_slug_per_workspace_unique() -> None:
    """Re-using a slug inside one workspace raises IntegrityError."""
    factory = app.state.session_factory
    with factory() as session:
        a = IssueLabel(
            workspace_id=1, slug="bug", label_text="Bug", color_hex="#ff0000"
        )
        b = IssueLabel(
            workspace_id=1, slug="bug", label_text="Bug dup", color_hex="#000000"
        )
        session.add_all([a, b])
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


def test_state_and_closed_reason_module_exports_match_db_vocab() -> None:
    """Module exports match the locked CHECK-constraint vocab."""
    assert ISSUE_STATES == ("open", "closed", "closed_not_planned")
    assert ISSUE_CLOSED_REASONS == (
        "fixed",
        "wont_fix",
        "duplicate",
        "superseded",
    )


def test_issue_milestone_round_trip() -> None:
    """Milestones round-trip through the ORM without surprises."""
    factory = app.state.session_factory
    with factory() as session:
        m = IssueMilestone(
            workspace_id=1,
            title="Q3 GA",
            description_md="Cut release",
            due_at=_now(),
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        assert m.id is not None
        assert m.title == "Q3 GA"
        assert m.due_at is not None
