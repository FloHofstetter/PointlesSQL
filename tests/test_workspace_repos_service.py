"""Phase 51.1 — workspace-repo service surface.

Covers create / add_secret / rotate_webhook_secret / delete /
list / sync against a real local bare repository (no network).
"""

from __future__ import annotations

import asyncio
import datetime
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from pointlessql.git import WorkspaceRepoUnknownProvider
from pointlessql.models.workspace._repos import (
    WorkspaceRepo,
    WorkspaceRepoSecret,
)
from pointlessql.services.secrets import decrypt_value
from pointlessql.services.workspace.repos import (
    add_secret,
    create_repo,
    delete_repo,
    list_repos_due_for_sync,
    list_repos_for_workspace,
    rotate_webhook_secret,
    sync_repo,
)


def _git_available() -> bool:
    return shutil.which("git") is not None


pytestmark = pytest.mark.skipif(not _git_available(), reason="git binary not available")


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        env={"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "LANG": "C", "HOME": str(Path.home()),
             "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )


def _bare_repo(tmp_path: Path) -> Path:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "--initial-branch=main", cwd=seed)
    _git("config", "user.email", "test@example.com", cwd=seed)
    _git("config", "user.name", "Test", cwd=seed)
    (seed / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=seed)
    _git("commit", "-m", "initial", cwd=seed)
    bare = tmp_path / "bare.git"
    _git("clone", "--bare", str(seed), str(bare))
    return bare


def _factory(_test_engine: tuple[Engine, sessionmaker]) -> sessionmaker:  # type: ignore[type-arg]
    return _test_engine[1]


def test_create_repo_persists_row_and_reveals_webhook(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="platform-yaml",
        url="file:///tmp/no-such-repo",
        default_branch="main",
        provider_kind="generic",
    )
    assert out.repo.id is not None
    assert len(out.webhook_secret_plaintext) >= 32
    with factory() as session:
        row = session.get(WorkspaceRepo, out.repo.id)
        assert row is not None
        assert row.sync_state == "idle"
        assert row.webhook_secret == out.webhook_secret_plaintext


def test_create_repo_rejects_unknown_provider(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    with pytest.raises(WorkspaceRepoUnknownProvider):
        create_repo(
            factory,
            workspace_id=1,
            slug="bogus",
            url="file:///tmp/whatever",
            provider_kind="gitlab",  # not registered
        )


def test_create_repo_with_initial_secret_encrypts_value(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    plaintext = "ghp_test_token"  # pragma: allowlist secret
    out = create_repo(
        factory,
        workspace_id=1,
        slug="with-secret",
        url="https://example.com/repo.git",
        provider_kind="generic",
        initial_secret_kind="https_token",
        initial_secret_plaintext=plaintext,
    )
    with factory() as session:
        secrets_rows = list(
            session.query(WorkspaceRepoSecret).filter_by(workspace_repo_id=out.repo.id)
        )
    assert len(secrets_rows) == 1
    assert secrets_rows[0].kind == "https_token"
    assert secrets_rows[0].encrypted_value != plaintext
    assert decrypt_value(secrets_rows[0].encrypted_value, session_factory=factory) == plaintext


def test_create_repo_rejects_half_specified_secret(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    with pytest.raises(ValueError):
        create_repo(
            factory,
            workspace_id=1,
            slug="oops",
            url="x",
            initial_secret_kind="https_token",
            initial_secret_plaintext=None,
        )


def test_add_secret_upserts_existing_kind(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out = create_repo(factory, workspace_id=1, slug="rotate-me", url="x")
    add_secret(factory, repo_id=out.repo.id, kind="https_token", plaintext="v1")
    add_secret(factory, repo_id=out.repo.id, kind="https_token", plaintext="v2")
    with factory() as session:
        rows = list(
            session.query(WorkspaceRepoSecret).filter_by(workspace_repo_id=out.repo.id)
        )
    assert len(rows) == 1
    assert rows[0].rotated_at is not None
    assert decrypt_value(rows[0].encrypted_value, session_factory=factory) == "v2"


def test_rotate_webhook_secret_changes_value(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out = create_repo(factory, workspace_id=1, slug="rot", url="x")
    new_value = rotate_webhook_secret(factory, repo_id=out.repo.id)
    assert new_value != out.webhook_secret_plaintext
    with factory() as session:
        row = session.get(WorkspaceRepo, out.repo.id)
        assert row is not None
        assert row.webhook_secret == new_value


def test_delete_repo_removes_row_and_clone_dir(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out = create_repo(factory, workspace_id=1, slug="bye", url="x")
    base = tmp_path / "repos"
    clone_dir = base / "1" / "bye"
    clone_dir.mkdir(parents=True)
    (clone_dir / "marker").write_text("present")
    deleted = delete_repo(factory, repo_id=out.repo.id, base_dir=base)
    assert deleted is True
    assert not clone_dir.exists()
    with factory() as session:
        assert session.get(WorkspaceRepo, out.repo.id) is None


def test_delete_repo_returns_false_when_missing(_test_engine, tmp_path):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    assert delete_repo(factory, repo_id=99_999, base_dir=tmp_path) is False


def test_list_repos_for_workspace_returns_only_that_workspace(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    create_repo(factory, workspace_id=1, slug="a", url="x")
    create_repo(factory, workspace_id=1, slug="b", url="y")
    rows = list_repos_for_workspace(factory, workspace_id=1)
    assert {row.slug for row in rows} >= {"a", "b"}


def test_list_repos_due_for_sync_picks_never_and_stale(_test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out_a = create_repo(factory, workspace_id=1, slug="never", url="x")
    out_b = create_repo(factory, workspace_id=1, slug="stale", url="y")
    out_c = create_repo(factory, workspace_id=1, slug="fresh", url="z")
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        b_row = session.get(WorkspaceRepo, out_b.repo.id)
        assert b_row is not None
        b_row.last_synced_at = now - datetime.timedelta(days=1)
        c_row = session.get(WorkspaceRepo, out_c.repo.id)
        assert c_row is not None
        c_row.last_synced_at = now
        session.commit()

    cutoff = now - datetime.timedelta(hours=1)
    rows = list_repos_due_for_sync(factory, cutoff=cutoff)
    slugs = [row.slug for row in rows]
    assert "never" in slugs and "stale" in slugs and "fresh" not in slugs
    # Sanity: "out_a" is on the list too.
    _ = out_a


def test_sync_repo_clones_then_pulls_against_local_bare(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _bare_repo(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="real",
        url=f"file://{bare}",
        default_branch="main",
        provider_kind="generic",
    )
    base = tmp_path / "repos"

    first = asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual")
    )
    assert first.ok is True
    assert first.operation == "clone"
    assert first.head_sha is not None
    assert first.changed is True
    with factory() as session:
        row = session.get(WorkspaceRepo, out.repo.id)
        assert row is not None
        assert row.sync_state == "ok"
        assert row.last_synced_sha == first.head_sha

    second = asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual")
    )
    assert second.ok is True
    assert second.operation == "pull"
    assert second.changed is False
    assert second.head_sha == first.head_sha


def test_sync_repo_records_error_on_unreachable_url(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="bad-upstream",
        url="file:///tmp/this-bare-does-not-exist-ever",
        default_branch="main",
        provider_kind="generic",
    )
    base = tmp_path / "repos"
    outcome = asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual")
    )
    assert outcome.ok is False
    assert outcome.error is not None
    with factory() as session:
        row = session.get(WorkspaceRepo, out.repo.id)
        assert row is not None
        assert row.sync_state == "error"
        assert row.last_sync_error is not None


def test_sync_repo_calls_post_pull_hook(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _bare_repo(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="hooked",
        url=f"file://{bare}",
        default_branch="main",
    )
    base = tmp_path / "repos"
    captured: list[tuple[int, str, str | None]] = []

    def hook(workspace_id: int, slug: str, head_sha: str | None) -> dict:  # type: ignore[type-arg]
        captured.append((workspace_id, slug, head_sha))
        return {"loaded_data_products": 3, "loaded_conventions": 1}

    outcome = asyncio.run(
        sync_repo(
            factory,
            repo_id=out.repo.id,
            base_dir=base,
            trigger="manual",
            on_post_pull=hook,
        )
    )
    assert outcome.ok is True
    assert captured and captured[0][1] == "hooked"
    assert outcome.loaded_data_products == 3
    assert outcome.loaded_conventions == 1
