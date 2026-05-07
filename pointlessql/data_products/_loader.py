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
from pointlessql.models.data_products import DataProduct

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
        else:
            existing.steward_user_id = steward_id
            existing.version = contract.version
            existing.description = contract.description
            existing.sla_minutes = contract.sla_minutes
            existing.contract_yaml_hash = contract_hash
            existing.contract_json = contract_json
            existing.last_loaded_at = timestamp
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
