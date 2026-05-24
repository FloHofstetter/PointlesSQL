"""repo-discovered yaml feeds the data-product + conventions loaders.

Each test seeds a real bare repo with a ``pointlessql.yaml``,
syncs the workspace_repo through the service layer (no network),
and verifies that the cached :class:`DataProduct` row materialises
without manual env-path configuration.
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

from pointlessql.conventions import load_conventions_for_workspace
from pointlessql.data_products import load_contracts_for_workspace
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.workspace.repos import (
    build_post_pull_loader_hook,
    create_repo,
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
        env={
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
            "HOME": str(Path.home()),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


_VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Replay fixture for the yaml-loader bridge.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id,    type: long,      nullable: false}
        - {name: customer_id, type: long,      nullable: false}
        - {name: order_total, type: double,    nullable: true}
        - {name: ordered_at,  type: timestamp, nullable: false}
"""


def _seed_bare_repo_with_yaml(tmp_path: Path, yaml_body: str = _VALID_YAML) -> Path:
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "--initial-branch=main", cwd=seed)
    _git("config", "user.email", "test@example.com", cwd=seed)
    _git("config", "user.name", "Test", cwd=seed)
    (seed / "pointlessql.yaml").write_text(yaml_body)
    _git("add", ".", cwd=seed)
    _git("commit", "-m", "seed pointlessql.yaml", cwd=seed)
    bare = tmp_path / "bare.git"
    _git("clone", "--bare", str(seed), str(bare))
    return bare


def _factory(_test_engine: tuple[Engine, sessionmaker]) -> sessionmaker:  # type: ignore[type-arg]
    return _test_engine[1]


def _settings_with_repo_base(tmp_path: Path):  # type: ignore[no-untyped-def]
    from pointlessql.config import Settings, WorkspaceReposSettings

    return Settings(
        workspace_repos=WorkspaceReposSettings(
            base_dir=tmp_path / "repos",
            yaml_search_globs=("pointlessql.yaml", "**/pointlessql.yaml"),
        )
    )


def test_load_contracts_for_workspace_picks_up_synced_repo(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _seed_bare_repo_with_yaml(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="data-team",
        url=f"file://{bare}",
        default_branch="main",
        provider_kind="generic",
    )
    base = tmp_path / "repos"
    asyncio.run(sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual"))

    contracts = load_contracts_for_workspace(
        factory,
        workspace_id=1,
        settings=_settings_with_repo_base(tmp_path),
        now=datetime.datetime.now(datetime.UTC),
    )
    assert len(contracts) == 1
    assert contracts[0].name == "Sales Orders"

    with factory() as session:
        rows = list(session.query(DataProduct))
    assert any(row.catalog_name == "main" and row.schema_name == "sales_gold" for row in rows)


def test_post_pull_hook_wires_loader_count_into_sync_outcome(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _seed_bare_repo_with_yaml(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="hooked-up",
        url=f"file://{bare}",
        default_branch="main",
    )
    base = tmp_path / "repos"
    settings = _settings_with_repo_base(tmp_path)
    hook = build_post_pull_loader_hook(factory, settings=settings)
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
    assert outcome.loaded_data_products == 1
    assert outcome.loaded_conventions == 1


def test_invalid_yaml_does_not_fail_the_sync(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _seed_bare_repo_with_yaml(tmp_path, yaml_body="data_product: not-a-mapping\n")
    out = create_repo(
        factory,
        workspace_id=1,
        slug="bad-yaml",
        url=f"file://{bare}",
        default_branch="main",
    )
    base = tmp_path / "repos"
    settings = _settings_with_repo_base(tmp_path)
    hook = build_post_pull_loader_hook(factory, settings=settings)
    outcome = asyncio.run(
        sync_repo(
            factory,
            repo_id=out.repo.id,
            base_dir=base,
            trigger="manual",
            on_post_pull=hook,
        )
    )
    # Sync itself succeeds; loader error surfaces through SyncOutcome.extra.
    assert outcome.ok is True
    assert "data_products_loader_error" in outcome.extra


def test_resync_unchanged_yaml_is_idempotent(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _seed_bare_repo_with_yaml(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="idem",
        url=f"file://{bare}",
        default_branch="main",
    )
    base = tmp_path / "repos"
    settings = _settings_with_repo_base(tmp_path)
    hook = build_post_pull_loader_hook(factory, settings=settings)

    asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual", on_post_pull=hook)
    )
    with factory() as session:
        before = list(session.query(DataProduct))
    asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual", on_post_pull=hook)
    )
    with factory() as session:
        after = list(session.query(DataProduct))
    assert len(before) == len(after) == 1
    assert before[0].id == after[0].id


def test_repo_deletion_does_not_remove_cached_data_products(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    bare = _seed_bare_repo_with_yaml(tmp_path)
    out = create_repo(
        factory,
        workspace_id=1,
        slug="will-be-deleted",
        url=f"file://{bare}",
        default_branch="main",
    )
    base = tmp_path / "repos"
    settings = _settings_with_repo_base(tmp_path)
    hook = build_post_pull_loader_hook(factory, settings=settings)
    asyncio.run(
        sync_repo(factory, repo_id=out.repo.id, base_dir=base, trigger="manual", on_post_pull=hook)
    )

    from pointlessql.services.workspace.repos import delete_repo

    delete_repo(factory, repo_id=out.repo.id, base_dir=base)

    with factory() as session:
        rows = list(session.query(DataProduct))
    assert any(row.schema_name == "sales_gold" for row in rows), (
        "cache row should survive the repo deletion (mirrors Phase-50 anti-goal)"
    )


def test_load_conventions_for_workspace_with_no_repos_returns_defaults(tmp_path, _test_engine):  # type: ignore[no-untyped-def]
    factory = _factory(_test_engine)
    settings = _settings_with_repo_base(tmp_path)
    config = load_conventions_for_workspace(factory, workspace_id=1, settings=settings)
    # Default config has well-known layer names — sanity-check via attribute.
    assert hasattr(config, "layers")
