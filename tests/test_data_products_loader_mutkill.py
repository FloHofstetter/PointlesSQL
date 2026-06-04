"""Behaviour tests that pin down the data-product yaml loader fan-out.

These exercise :func:`load_contracts_from_paths` and
:func:`load_contracts_for_workspace` — the two batch helpers around
:func:`load_contract`.  They assert the *observable* contract:

* which yaml files are discovered (filename, case-sensitivity, the
  directory ``/`` join);
* that every candidate path is visited (``continue`` not ``break``);
* that ``workspace_id`` and ``now`` flow through to the per-file
  ``load_contract`` call (DB row workspace + ``last_loaded_at``);
* the env-path/repo dedup-by-resolved-path bookkeeping; and
* graceful handling of a settings object that omits the optional
  ``data_products`` / ``workspace_repos`` attributes.

Pure-Python: an in-memory sqlite ``StaticPool`` factory rather than
the app-state fixture, so the tests run without a live server.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.data_products._loader import (
    load_contracts_for_workspace,
    load_contracts_from_paths,
)
from pointlessql.models import Base
from pointlessql.models.catalog._data_products import DataProduct

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.2.0"
  description: Curated orders facts.
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
"""

# A second contract with a *different* catalog/schema so two of them
# produce two distinct cache rows in the same workspace.
OTHER_YAML = VALID_YAML.replace("catalog: main", "catalog: other").replace(
    "schema: sales_gold", "schema: other_gold"
)

FIXED_NOW = datetime.datetime(2021, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory sqlite factory holding the full ORM schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _write(dir_: Path, content: str = VALID_YAML, name: str = "pointlessql.yaml") -> Path:
    p = dir_ / name
    p.write_text(content, encoding="utf-8")
    return p


def _rows(factory: sessionmaker) -> list[DataProduct]:  # type: ignore[type-arg]
    with factory() as session:
        return list(session.execute(select(DataProduct)).scalars().all())


# --------------------------------------------------------------------------
# load_contracts_from_paths
# --------------------------------------------------------------------------


def test_from_paths_directory_finds_root_yaml(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A directory arg resolves to ``<dir>/pointlessql.yaml`` and loads it.

    Kills the filename-literal and ``/``-join mutations: a wrong
    filename (case change, marker text) or a ``*`` join would either
    raise or find nothing, so the contract list would be empty.
    """
    _write(tmp_path)
    contracts = load_contracts_from_paths([tmp_path], factory=factory)
    assert len(contracts) == 1
    assert contracts[0].catalog == "main"
    assert len(_rows(factory)) == 1


def test_from_paths_directory_without_yaml_is_skipped(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A directory whose ``pointlessql.yaml`` is absent yields nothing.

    The exact lowercase ``pointlessql.yaml`` literal must match: if the
    loader looked for ``POINTLESSQL.YAML`` it would still find nothing
    here, so this pairs with the positive test above to pin the name.
    """
    (tmp_path / "POINTLESSQL.YAML").write_text(VALID_YAML, encoding="utf-8")
    contracts = load_contracts_from_paths([tmp_path], factory=factory)
    assert contracts == []
    assert _rows(factory) == []


def test_from_paths_continues_past_missing_target(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A missing first path does not abort the loop (``continue`` not ``break``)."""
    missing = tmp_path / "ghost"  # directory does not exist -> no yaml
    good_dir = tmp_path / "good"
    good_dir.mkdir()
    _write(good_dir)

    contracts = load_contracts_from_paths([missing, good_dir], factory=factory)
    assert len(contracts) == 1
    assert contracts[0].catalog == "main"
    assert len(_rows(factory)) == 1


def test_from_paths_propagates_workspace_id(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """``workspace_id`` reaches the per-file load and the cache row."""
    _write(tmp_path)
    load_contracts_from_paths([tmp_path], factory=factory, workspace_id=7)
    rows = _rows(factory)
    assert len(rows) == 1
    assert rows[0].workspace_id == 7


def test_from_paths_default_workspace_id_is_one(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """Omitting ``workspace_id`` defaults to 1 (kills the ``=2`` mutation)."""
    _write(tmp_path)
    load_contracts_from_paths([tmp_path], factory=factory)
    rows = _rows(factory)
    assert len(rows) == 1
    assert rows[0].workspace_id == 1


def test_from_paths_propagates_now(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """``now`` reaches the cache row's ``last_loaded_at`` (not wall-clock)."""
    _write(tmp_path)
    load_contracts_from_paths([tmp_path], factory=factory, now=FIXED_NOW)
    rows = _rows(factory)
    assert len(rows) == 1
    stored = rows[0].last_loaded_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=datetime.UTC)
    assert stored == FIXED_NOW


def test_from_paths_file_arg_loaded_directly(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A file path is loaded as-is (the ``is_file()`` branch)."""
    yaml_path = _write(tmp_path)
    contracts = load_contracts_from_paths([yaml_path], factory=factory)
    assert len(contracts) == 1


# --------------------------------------------------------------------------
# load_contracts_for_workspace
# --------------------------------------------------------------------------


def _settings(
    *,
    yaml_search_paths: list[Path] | None = None,
    workspace_repos: object | None = "OMIT",
) -> SimpleNamespace:
    """Build a minimal settings stand-in for the workspace loader.

    ``workspace_repos="OMIT"`` leaves the attribute off entirely so the
    ``getattr(..., None)`` fallback path is exercised.
    """
    dp = SimpleNamespace(yaml_search_paths=list(yaml_search_paths or []))
    ns = SimpleNamespace(data_products=dp)
    if workspace_repos != "OMIT":
        ns.workspace_repos = workspace_repos
    return ns


def test_for_workspace_loads_env_paths(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """Env ``yaml_search_paths`` directories are discovered + loaded."""
    _write(tmp_path)
    settings = _settings(yaml_search_paths=[tmp_path])
    contracts = load_contracts_for_workspace(
        factory, workspace_id=3, settings=settings, now=FIXED_NOW
    )
    assert len(contracts) == 1
    rows = _rows(factory)
    assert len(rows) == 1
    # workspace_id + now flow all the way through to load_contract.
    assert rows[0].workspace_id == 3
    stored = rows[0].last_loaded_at
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=datetime.UTC)
    assert stored == FIXED_NOW


def test_for_workspace_dedups_same_path(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """The same directory listed twice resolves to one discovered yaml.

    Pins the ``and``/dedup bookkeeping: ``target.exists() and target
    not in seen`` plus ``seen.add(target.resolve())``.  A broken
    ``or`` or ``seen.add(None)`` would append the duplicate, yielding
    two contracts (and an idempotent-but-still-double load call).
    """
    _write(tmp_path)
    settings = _settings(yaml_search_paths=[tmp_path, tmp_path])
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert len(contracts) == 1
    assert len(_rows(factory)) == 1


def test_for_workspace_distinct_paths_both_load(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """Two distinct directories each contribute one contract.

    Guards against an over-eager dedup (e.g. ``seen.add(None)`` would
    collapse the second path because ``None in seen`` is already true).
    """
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    _write(d1, VALID_YAML)
    _write(d2, OTHER_YAML)
    settings = _settings(yaml_search_paths=[d1, d2])
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert len(contracts) == 2
    catalogs = {c.catalog for c in contracts}
    assert catalogs == {"main", "other"}
    assert len(_rows(factory)) == 2


def test_for_workspace_missing_yaml_skipped(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A configured dir with the wrong-cased filename finds nothing."""
    (tmp_path / "POINTLESSQL.YAML").write_text(VALID_YAML, encoding="utf-8")
    settings = _settings(yaml_search_paths=[tmp_path])
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert contracts == []
    assert _rows(factory) == []


def test_for_workspace_no_repos_attr_is_graceful(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A settings object lacking ``workspace_repos`` skips repo discovery.

    Kills the ``getattr(resolved_settings, "workspace_repos", None)``
    default-drop mutation: without the ``None`` fallback the attribute
    access raises ``AttributeError`` here.
    """
    _write(tmp_path)
    settings = _settings(yaml_search_paths=[tmp_path], workspace_repos="OMIT")
    assert not hasattr(settings, "workspace_repos")
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert len(contracts) == 1


def test_for_workspace_repos_without_base_dir_is_graceful(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A ``workspace_repos`` object without ``base_dir`` skips discovery.

    Kills the ``getattr(repos_settings, "base_dir", None)`` default
    drop — and, indirectly, the ``globs`` default — by giving a repos
    object that carries neither attribute.  The loader must treat a
    missing ``base_dir`` as "no repo discovery" rather than crash.
    """
    _write(tmp_path)
    settings = _settings(
        yaml_search_paths=[tmp_path],
        workspace_repos=SimpleNamespace(),  # no base_dir, no yaml_search_globs
    )
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert len(contracts) == 1
    assert len(_rows(factory)) == 1


def test_for_workspace_no_data_products_attr_is_graceful(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A ``data_products`` object missing ``yaml_search_paths`` -> empty list.

    Kills the ``getattr(..., "yaml_search_paths", [])`` mutations: a
    ``None`` default would make ``list(None)`` raise, and dropping the
    default entirely would raise ``AttributeError``.  The contract is a
    clean empty result, no crash.
    """
    settings = SimpleNamespace(data_products=SimpleNamespace())  # no yaml_search_paths
    contracts = load_contracts_for_workspace(factory, workspace_id=1, settings=settings)
    assert contracts == []
    assert _rows(factory) == []


def _seed_repo(factory: sessionmaker, *, workspace_id: int, slug: str) -> None:  # type: ignore[type-arg]
    """Insert a workspace + repo row so repo discovery has something to walk."""
    from pointlessql.models import Workspace
    from pointlessql.models.workspace._repos import WorkspaceRepo

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(Workspace(id=workspace_id, slug=f"ws{workspace_id}", name="WS", created_at=now))
        session.add(
            WorkspaceRepo(
                workspace_id=workspace_id,
                slug=slug,
                url="https://example.test/repo.git",
                webhook_secret="x",
                created_at=now,
            )
        )
        session.commit()


def test_for_workspace_discovers_repo_yaml(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A synced repo's ``pointlessql.yaml`` is discovered + loaded.

    Exercises the ``base_dir`` repo-discovery branch end to end and
    pins the repo-loop dedup (``seen.add(repo_yaml)``): a ``None`` add
    would not corrupt this single-match case, but combined with the
    env-path dedup test it keeps the bookkeeping honest.  The clone dir
    layout is ``<base_dir>/<workspace_id>/<slug>/``.
    """
    ws_id = 4
    base_dir = tmp_path / "repos"
    clone_dir = base_dir / str(ws_id) / "myrepo"
    clone_dir.mkdir(parents=True)
    _write(clone_dir, VALID_YAML)
    _seed_repo(factory, workspace_id=ws_id, slug="myrepo")

    settings = _settings(
        yaml_search_paths=[],
        workspace_repos=SimpleNamespace(base_dir=base_dir, yaml_search_globs=("pointlessql.yaml",)),
    )
    contracts = load_contracts_for_workspace(factory, workspace_id=ws_id, settings=settings)
    assert len(contracts) == 1
    assert contracts[0].catalog == "main"
    rows = _rows(factory)
    assert len(rows) == 1
    assert rows[0].workspace_id == ws_id


def test_for_workspace_globs_default_when_repos_present(tmp_path: Path, factory) -> None:  # type: ignore[no-untyped-def]
    """A repos object with ``base_dir`` but no ``yaml_search_globs``.

    Reaches ``tuple(globs)`` in the repo-discovery call.  The
    ``getattr(..., "yaml_search_globs", ())`` default must be an empty
    tuple — a ``None`` default would make ``tuple(None)`` raise, and
    dropping the default would raise ``AttributeError``.  With an empty
    glob set, repo discovery contributes nothing, so only the env path
    loads.
    """
    ws_id = 5
    base_dir = tmp_path / "repos"
    clone_dir = base_dir / str(ws_id) / "myrepo"
    clone_dir.mkdir(parents=True)
    _write(clone_dir, OTHER_YAML)  # would load if globs matched
    _seed_repo(factory, workspace_id=ws_id, slug="myrepo")

    env_dir = tmp_path / "env"
    env_dir.mkdir()
    _write(env_dir, VALID_YAML)

    settings = _settings(
        yaml_search_paths=[env_dir],
        workspace_repos=SimpleNamespace(base_dir=base_dir),  # no yaml_search_globs
    )
    contracts = load_contracts_for_workspace(factory, workspace_id=ws_id, settings=settings)
    # Empty glob -> repo yaml not discovered; only the env path loads.
    assert len(contracts) == 1
    assert contracts[0].catalog == "main"
