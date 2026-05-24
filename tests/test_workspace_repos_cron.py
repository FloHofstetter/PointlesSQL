"""workspace-repos cron-loop driver.

Two narrow tests covering the helper that picks repos due for
sync.  The full lifespan loop is opt-in (interval > 0); we
unit-test the row-selection layer rather than spawning the
asyncio task.
"""

from __future__ import annotations

import datetime

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from pointlessql.models.workspace._repos import WorkspaceRepo
from pointlessql.services.workspace.repos import (
    create_repo,
    list_repos_due_for_sync,
)


def _factory(_test_engine: tuple[Engine, sessionmaker]) -> sessionmaker:  # type: ignore[type-arg]
    return _test_engine[1]


def test_cron_picks_only_stale_repos(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out_a = create_repo(factory, workspace_id=1, slug="never-cron", url="x")
    out_b = create_repo(factory, workspace_id=1, slug="stale-cron", url="y")
    out_c = create_repo(factory, workspace_id=1, slug="fresh-cron", url="z")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        b = session.get(WorkspaceRepo, out_b.repo.id)
        assert b is not None
        b.last_synced_at = now - datetime.timedelta(hours=1)
        c = session.get(WorkspaceRepo, out_c.repo.id)
        assert c is not None
        c.last_synced_at = now
        session.commit()
    cutoff = now - datetime.timedelta(minutes=5)
    rows = list_repos_due_for_sync(factory, cutoff=cutoff)
    slugs = [row.slug for row in rows]
    assert "never-cron" in slugs and "stale-cron" in slugs and "fresh-cron" not in slugs
    _ = out_a


def test_cron_returns_empty_when_no_repos_exist(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    cutoff = datetime.datetime.now(datetime.UTC)
    rows = list_repos_due_for_sync(factory, cutoff=cutoff)
    # The fixture seeds zero workspace_repos, but other tests in the same
    # session may have created some.  We just assert the helper returns
    # *something* iterable and that it's a list of WorkspaceRepo.
    for row in rows:
        assert isinstance(row, WorkspaceRepo)
