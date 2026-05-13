"""Inline ``pql.contract()`` DSL for agent-authored DPs (Phase 73.2).

Agents call :func:`contract` from inside a notebook to *declare*
a data-product contract for the work they just wrote.
The builder returns a :class:`DraftContract` whose ``.yaml()``
serialises a payload validated against the existing
:class:`pointlessql.data_products._schema.DataProductContract`
pydantic model and whose ``.save()`` writes the yaml under
``settings.data_products.draft_dir`` *and* inserts a
:class:`DataProductYamlDraft` row for the admin to promote.

The DSL stays pure: no DB session is required to *build* a
contract, only to ``save()`` it.  When called outside a
PointlesSQL process (e.g. local notebook), ``save()`` falls
back to writing the file only and skips the DB insert.
"""

from __future__ import annotations

import datetime
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pointlessql.data_products._schema import DataProductContract

DRAFT_SOURCE_KIND = "pql_contract"


@dataclass(frozen=False)
class DraftContract:
    """Builder + persister for an in-notebook contract.

    Returned by :func:`contract`.  Provides three methods:

    * :meth:`yaml` — serialise the validated contract back to
      a yaml string.
    * :meth:`as_dict` — the validated dict payload.
    * :meth:`save` — write the yaml file under
      ``settings.data_products.draft_dir`` and insert a
      :class:`DataProductYamlDraft` row.

    Attributes:
        contract: The validated :class:`DataProductContract`
            this draft wraps.
    """

    contract: DataProductContract

    def as_dict(self) -> dict[str, Any]:
        """Return the contract as a serialisable dict.

        Returns:
            The yaml-shaped dict (uses the ``schema`` alias for
            the ``schema_name`` field).
        """
        return self.contract.model_dump(by_alias=True)

    def yaml(self) -> str:
        """Render the contract as a loader-compatible yaml string.

        The yaml is wrapped in a ``data_product:`` top-level key
        so the existing
        :func:`pointlessql.data_products.load_contract` parser
        accepts it as-is.

        Returns:
            Yaml string round-trippable through the loader.
        """
        return yaml.safe_dump({"data_product": self.as_dict()}, sort_keys=False)

    def save(
        self,
        *,
        session_factory: Any = None,
        draft_dir: Path | None = None,
        workspace_id: int = 1,
        created_by_user_id: int | None = None,
        created_by_agent_run_id: int | None = None,
    ) -> Path:
        """Persist the draft to disk + the DB tracking row.

        When no ``session_factory`` is provided, only the file
        write happens (for notebook-local dry runs).  When the
        ``draft_dir`` is omitted, the helper resolves it via
        ``Settings()`` — convenient for in-process callers.

        Args:
            session_factory: Optional SQLAlchemy session
                factory.  When supplied, a
                :class:`DataProductYamlDraft` row gets
                inserted alongside the file.
            draft_dir: Optional draft root directory override.
                Defaults to ``Settings().data_products.draft_dir``.
            workspace_id: Tenant scope for the DB row.
            created_by_user_id: Author user id for the DB row.
            created_by_agent_run_id: Author agent run id for
                the DB row.

        Returns:
            Absolute path of the written yaml file.
        """
        from pointlessql.models.catalog._data_product_yaml_draft import (
            DataProductYamlDraft,
        )

        target_dir = draft_dir
        if target_dir is None:
            from pointlessql.config import Settings

            target_dir = Settings().data_products.draft_dir
        target_dir = Path(target_dir) / str(workspace_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{self.contract.catalog}__{self.contract.schema_name}.yaml"
        yaml_text = self.yaml()
        yaml_hash = hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
        path.write_text(yaml_text, encoding="utf-8")

        if session_factory is None:
            return path

        from sqlalchemy import select

        with session_factory() as session:
            existing = session.execute(
                select(DataProductYamlDraft).where(
                    DataProductYamlDraft.workspace_id == workspace_id,
                    DataProductYamlDraft.catalog_name == self.contract.catalog,
                    DataProductYamlDraft.schema_name == self.contract.schema_name,
                    DataProductYamlDraft.yaml_hash == yaml_hash,
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    DataProductYamlDraft(
                        workspace_id=workspace_id,
                        catalog_name=self.contract.catalog,
                        schema_name=self.contract.schema_name,
                        draft_path=str(path),
                        source_kind=DRAFT_SOURCE_KIND,
                        created_by_user_id=created_by_user_id,
                        created_by_agent_run_id=created_by_agent_run_id,
                        created_at=datetime.datetime.now(datetime.UTC),
                        yaml_hash=yaml_hash,
                    )
                )
                session.commit()
        return path


def contract(
    catalog: str,
    schema_name: str,
    *,
    tables: list[dict[str, Any]],
    name: str | None = None,
    description: str = "",
    version: str = "0.1.0-draft",
    sla_minutes: int | None = None,
    steward_email: str | None = None,
) -> DraftContract:
    """Build a draft data-product contract from inside a notebook.

    Validates the payload against :class:`DataProductContract`
    before returning the builder.  Callers can chain ``.yaml()``
    or ``.save()`` to persist.

    Args:
        catalog: UC catalog name.
        schema_name: UC schema name.
        tables: List of ``{name, columns: [...],
            primary_key?: [...]}`` dicts; columns are
            ``{name, type, nullable?, description?}`` where
            ``type`` is one of the 11 primitives accepted by
            :class:`DataProductColumnSpec`.
        name: Optional human-readable product name; defaults to
            ``"<catalog>.<schema>"``.
        description: One-paragraph product description.
        version: SemVer-shaped string.  Defaults to
            ``"0.1.0-draft"`` for agent-authored contracts.
        sla_minutes: Optional freshness SLA.
        steward_email: Optional steward contact.

    Returns:
        A validated :class:`DraftContract` ready to ``.save()``.

        Raises ``pydantic.ValidationError`` when the payload
        doesn't pass :class:`DataProductContract` validation.

    Example:
        >>> from pointlessql import pql
        >>> draft = pql.contract(
        ...     "main",
        ...     "sales_gold",
        ...     tables=[{
        ...         "name": "orders",
        ...         "columns": [
        ...             {"name": "id", "type": "long", "nullable": False},
        ...         ],
        ...         "primary_key": ["id"],
        ...     }],
        ...     description="Curated orders.",
        ... )
        >>> draft.save()
    """
    payload: dict[str, Any] = {
        "name": name or f"{catalog}.{schema_name}",
        "version": version,
        "description": description,
        "catalog": catalog,
        "schema": schema_name,
        "tables": tables,
    }
    if steward_email is not None:
        payload["steward_email"] = steward_email
    if sla_minutes is not None:
        payload["sla_minutes"] = sla_minutes
    validated = DataProductContract.model_validate(payload)
    return DraftContract(validated)
