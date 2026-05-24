"""YAML loader for ``pointlessql.yaml`` data-product contracts.

The parser is deliberately small — :func:`load_contract` reads a
yaml file, validates the ``data_product:`` block via pydantic, and
(when given a session factory) UPSERTs the result into the
``data_products`` cache table.  Yaml is canonical; the cache is a
read-side accelerator so HTTP and plugin callers don't need
filesystem access to the data team's repo.

Yaml shape::

    data_product:
      name: Sales Orders
      version: "1.2.0"
      description: |
        Curated orders facts joined with customer dim.
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
            - {name: order_total, type: decimal,   nullable: true}
            - {name: ordered_at,  type: timestamp, nullable: false}

The top-level wrapper key (``data_product:``) lets a single yaml
file mix conventions overrides and product declarations as the
project grows; for now only ``data_product`` is consumed.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from pointlessql.data_products._errors import DataProductYamlInvalid
from pointlessql.data_products._schema import DataProductContract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def parse_yaml(yaml_path: Path) -> DataProductContract:
    """Read + validate one ``pointlessql.yaml`` data-product file.

    Args:
        yaml_path: Filesystem path to the yaml.

    Returns:
        Validated :class:`DataProductContract` instance.

    Raises:
        FileNotFoundError: ``yaml_path`` does not exist.
        DataProductYamlInvalid: yaml syntax invalid, top level not a
            mapping, or pydantic validation failed.
    """
    if not yaml_path.exists():
        raise FileNotFoundError(
            f"pointlessql.yaml not found at {yaml_path!s}"
        )

    with yaml_path.open("r", encoding="utf-8") as fh:
        try:
            raw: Any = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise DataProductYamlInvalid(
                f"yaml syntax error in {yaml_path!s}: {exc}"
            ) from exc

    if raw is None:
        raise DataProductYamlInvalid(
            f"yaml file {yaml_path!s} is empty"
        )

    if not isinstance(raw, dict):
        raise DataProductYamlInvalid(
            f"yaml top level must be a mapping, got {type(raw).__name__}"
        )

    raw_dict = cast("dict[str, Any]", raw)
    block: Any = raw_dict.get("data_product")
    if block is None:
        raise DataProductYamlInvalid(
            f"yaml file {yaml_path!s} has no 'data_product:' block"
        )

    if not isinstance(block, dict):
        raise DataProductYamlInvalid(
            "'data_product:' block must be a mapping, "
            f"got {type(block).__name__}"
        )

    block_dict = cast("dict[str, Any]", block)
    try:
        return DataProductContract.model_validate(block_dict)
    except PydanticValidationError as exc:
        raise DataProductYamlInvalid(
            f"contract validation failed for {yaml_path!s}: {exc}"
        ) from exc


def _file_hash(yaml_path: Path) -> str:
    """Return SHA-256 of the yaml file contents."""
    return hashlib.sha256(yaml_path.read_bytes()).hexdigest()


def _resolve_steward_id(session: Session, email: str | None) -> int | None:
    """Look up ``users.id`` for *email*; return ``None`` when missing.

    Steward email is optional in the contract.  Even when provided,
    the FK stays NULL until the human has logged in at least once
    (and therefore has a ``users`` row).  The detail-page UI falls
    back to a mailto link in the NULL case.
    """
    if not email:
        return None
    user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
    return user.id if user is not None else None


def load_contract(
    yaml_path: Path,
    *,
    factory: sessionmaker[Session] | None = None,
    workspace_id: int = 1,
    now: datetime.datetime | None = None,
) -> DataProductContract:
    """Load a data-product yaml + UPSERT the cache row.

    Args:
        yaml_path: Filesystem path to the ``pointlessql.yaml`` file.
        factory: Optional SQLAlchemy session factory.  When given,
            the parsed contract is UPSERTed into the
            ``data_products`` cache table; when ``None`` the file
            is parsed-and-returned without DB side effects (used
            by tests + the CLI ``--validate`` flow).
        workspace_id: Workspace this product belongs to.  Defaults
            to the seeded default workspace (id=1).
        now: Override for the ``last_loaded_at`` timestamp (testing
            hook).  ``None`` uses ``datetime.now(UTC)``.

    Returns:
        The validated :class:`DataProductContract`.

    See :func:`parse_yaml` for the full set of failure modes — they
    propagate from the parse step before any DB write happens, so a
    malformed yaml never leaves a stale cache row behind.
    """
    contract = parse_yaml(yaml_path)
    if factory is None:
        return contract

    contract_hash = _file_hash(yaml_path)
    contract_json = json.dumps(
        contract.model_dump(by_alias=True, mode="json"),
        sort_keys=True,
        default=str,
    )
    timestamp = now or datetime.datetime.now(datetime.UTC)

    with factory() as session:
        steward_id = _resolve_steward_id(session, contract.steward_email)
        existing = session.execute(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == contract.catalog,
                DataProduct.schema_name == contract.schema_name,
            )
        ).scalar_one_or_none()

        # Phase 84.2 — release-stream bookkeeping.  Detect a new
        # release row up front so we can persist it after the DP
        # row is committed (we need DataProduct.id either way).
        # ``release_signal`` is ``None`` when no release should be
        # recorded, else the signed-off email (or empty string).
        from pointlessql.models import DataProductRelease

        release_signal: str | None = None

        if existing is None:
            row = DataProduct(
                workspace_id=workspace_id,
                catalog_name=contract.catalog,
                schema_name=contract.schema_name,
                steward_user_id=steward_id,
                version=contract.version,
                description=contract.description,
                sla_minutes=contract.sla_minutes,
                contract_yaml_hash=contract_hash,
                contract_json=contract_json,
                last_loaded_at=timestamp,
                created_at=timestamp,
            )
            session.add(row)
            release_signal = contract.steward_email or ""
        else:
            if (
                existing.version != contract.version
                or existing.contract_yaml_hash != contract_hash
            ):
                release_signal = contract.steward_email or ""
            existing.steward_user_id = steward_id
            existing.version = contract.version
            existing.description = contract.description
            existing.sla_minutes = contract.sla_minutes
            existing.contract_yaml_hash = contract_hash
            existing.contract_json = contract_json
            existing.last_loaded_at = timestamp
        session.commit()

        if release_signal is not None:
            dp_row = session.execute(
                select(DataProduct).where(
                    DataProduct.workspace_id == workspace_id,
                    DataProduct.catalog_name == contract.catalog,
                    DataProduct.schema_name == contract.schema_name,
                )
            ).scalar_one()
            session.add(
                DataProductRelease(
                    data_product_id=dp_row.id,
                    version=contract.version,
                    contract_yaml_hash=contract_hash,
                    released_at=timestamp,
                    signed_off_by_email=release_signal,
                )
            )
            session.commit()

    return contract


def load_contracts_from_paths(
    paths: list[Path],
    *,
    factory: sessionmaker[Session] | None = None,
    workspace_id: int = 1,
    now: datetime.datetime | None = None,
) -> list[DataProductContract]:
    """Load every ``pointlessql.yaml`` under each search root.

    Walks each path: if it's a file, loads it directly; if it's a
    directory, finds ``pointlessql.yaml`` at the root only (no
    recursive walk — opt-in pinned paths keep the loader's blast
    radius small).

    Args:
        paths: Candidate yaml files or directories containing one.
        factory: See :func:`load_contract`.
        workspace_id: See :func:`load_contract`.
        now: See :func:`load_contract`.

    Returns:
        List of successfully-loaded contracts.  Per-file failures
        are not silently swallowed — the function raises
        :class:`DataProductYamlInvalid` on the first invalid file
        so a typo doesn't mask a half-loaded fleet.
    """
    contracts: list[DataProductContract] = []
    for path in paths:
        target = path if path.is_file() else path / "pointlessql.yaml"
        if not target.exists():
            continue
        contracts.append(
            load_contract(
                target,
                factory=factory,
                workspace_id=workspace_id,
                now=now,
            )
        )
    return contracts


def load_contracts_for_workspace(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    settings: object | None = None,
    now: datetime.datetime | None = None,
) -> list[DataProductContract]:
    """Load every ``pointlessql.yaml`` discovered for *workspace_id*.

    Phase 51.2 — combines two yaml sources:

    1. Env-configured ``settings.data_products.yaml_search_paths``
       (the legacy Phase-50 path).  Treated as workspace-agnostic;
       admins point this at machine-local directories.
    2. Repo-discovered yaml: every successfully-synced
       :class:`WorkspaceRepo` row in *workspace_id* contributes
       matches against
       ``settings.workspace_repos.yaml_search_globs``.

    The two sets are deduplicated by absolute path and sorted in
    ``(env-path-then-repo, alpha)`` order so re-running against an
    unchanged on-disk state always returns the same sequence.
    Idempotent — every yaml is parsed and UPSERTed; unchanged
    files no-op via the SHA-256-hash check inside
    :func:`load_contract`.

    Args:
        factory: SQLAlchemy session factory.  Required (unlike
            :func:`load_contracts_from_paths`) because the repo
            discovery walks ``WorkspaceRepo`` rows.
        workspace_id: Workspace owning the discovered repos.
        settings: Optional :class:`pointlessql.config.Settings`
            override (pure-test inject).  Default builds a fresh
            ``Settings()`` reading the env.
        now: Override for the ``last_loaded_at`` timestamp.

    Returns:
        List of successfully-loaded contracts.

    The function imports :class:`Settings` lazily to keep this
    module's import surface unchanged for the Phase-50 paths that
    don't go through the workspace-scoped helper.
    """
    # Local import to avoid a top-level dependency on settings/git
    # for callers that only use load_contract / load_contracts_from_paths.
    from pointlessql.config import get_settings
    from pointlessql.git import discover_repo_yaml_files

    resolved_settings = settings if settings is not None else get_settings()
    # Cast helps pyright understand the attribute access.
    dp_paths = list(getattr(resolved_settings.data_products, "yaml_search_paths", []))  # type: ignore[union-attr]
    repos_settings = getattr(resolved_settings, "workspace_repos", None)
    base_dir = getattr(repos_settings, "base_dir", None)
    globs = getattr(repos_settings, "yaml_search_globs", ())

    seen: set[Path] = set()
    paths: list[Path] = []
    for raw in dp_paths:
        candidate = Path(raw)
        target = candidate if candidate.is_file() else candidate / "pointlessql.yaml"
        if target.exists() and target not in seen:
            seen.add(target.resolve())
            paths.append(target)
    if base_dir is not None:
        for repo_yaml in discover_repo_yaml_files(
            factory,
            workspace_id=workspace_id,
            base_dir=Path(base_dir),
            globs=tuple(globs),
        ):
            if repo_yaml not in seen:
                seen.add(repo_yaml)
                paths.append(repo_yaml)

    return load_contracts_from_paths(
        paths,
        factory=factory,
        workspace_id=workspace_id,
        now=now,
    )
