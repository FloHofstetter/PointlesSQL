"""Policy-compliance scanner — flags declared-vs-actual drift.

Two deterministic checks per product (not statistical anomalies, so
findings are written to the durable audit log rather than the
baseline-driven anomaly inbox):

* **retention** — a product that declares a retention window but holds
  data older than it (oldest Delta commit age > ``retention_days``).
* **classification coverage** — a column whose name looks like PII
  (:func:`is_pii_by_name`) but carries no declared classification, so
  the masking sidecar would let it through in the clear.

Findings are emitted as ``policy.compliance_violation`` audit rows
(``target = "data_product:{catalog}.{schema}"``) so they surface in the
existing audit cockpit and the product's Governance tab.  The pure
check helpers take their inputs as plain data so they unit-test without
a database or live Delta tables.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.data_products import DataProductContract
from pointlessql.models import DataProduct
from pointlessql.services.audit._core import log_action
from pointlessql.services.governance._classifications import classifications_for_schema
from pointlessql.services.governance._policy import get_effective_policy
from pointlessql.services.pii._redactor import is_pii_by_name

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

#: Audit action stamped for every compliance finding.
COMPLIANCE_VIOLATION_ACTION = "policy.compliance_violation"


def unclassified_pii_findings(
    contract: DataProductContract,
    classification_index: dict[tuple[str, str], tuple[str, str]],
) -> list[dict[str, Any]]:
    """Return findings for PII-looking columns that lack a classification.

    Args:
        contract: The parsed product contract (declares tables/columns).
        classification_index: ``{(table, column): (class, strategy)}``
            from :func:`classifications_for_schema`.

    Returns:
        One ``{"kind", "table", "column", "severity", "message"}`` dict
        per unclassified PII-looking column.
    """
    findings: list[dict[str, Any]] = []
    for table in contract.tables:
        for column in table.columns:
            if not is_pii_by_name(column.name):
                continue
            if (table.name, column.name) in classification_index:
                continue
            findings.append(
                {
                    "kind": "unclassified_pii",
                    "table": table.name,
                    "column": column.name,
                    "severity": "warn",
                    "message": (
                        f"column {column.name!r} looks like PII but has no "
                        "classification — it will not be masked"
                    ),
                }
            )
    return findings


def retention_findings(
    retention_days: int | None,
    table_ages: dict[str, float | None],
) -> list[dict[str, Any]]:
    """Return findings for tables holding data past the retention window.

    Args:
        retention_days: Effective retention window, or ``None`` (no
            expectation → no findings).
        table_ages: ``{table_name: oldest_data_age_in_days | None}``;
            ``None`` ages are skipped (age unknown).

    Returns:
        One ``{"kind", "table", "severity", "message"}`` dict per
        overdue table.
    """
    if retention_days is None:
        return []
    findings: list[dict[str, Any]] = []
    for table, age in table_ages.items():
        if age is None:
            continue
        if age > retention_days:
            findings.append(
                {
                    "kind": "retention_overdue",
                    "table": table,
                    "severity": "critical",
                    "message": (
                        f"table {table!r} holds data ~{int(age)}d old, past the "
                        f"{retention_days}d retention window"
                    ),
                }
            )
    return findings


def _table_age_days(settings: Any, catalog: str, schema: str, table: str) -> float | None:
    """Return the age in days of a table's oldest Delta commit, or ``None``.

    Best-effort: resolves the table's storage location and reads the
    Delta history; any failure (missing table, no history, IO error)
    yields ``None`` so the scan never flags on uncertainty and never
    crashes on one bad table.
    """
    import datetime  # noqa: PLC0415

    try:
        from deltalake import DeltaTable  # noqa: PLC0415

        from pointlessql.pql._write import derive_storage_location  # noqa: PLC0415
        from pointlessql.services.soyuz_client import make_soyuz_client  # noqa: PLC0415

        client = make_soyuz_client(settings)
        location = derive_storage_location(client, catalog, schema, table)
        history = DeltaTable(location).history()
        timestamps = [h["timestamp"] for h in history if h.get("timestamp")]
        if not timestamps:
            return None
        oldest_ms = min(timestamps)
        oldest = datetime.datetime.fromtimestamp(oldest_ms / 1000, tz=datetime.UTC)
        return (datetime.datetime.now(datetime.UTC) - oldest).total_seconds() / 86400
    except Exception:  # noqa: BLE001
        # bare-broad-ok: retention age is best-effort, must never crash a scan
        return None


def scan_workspace(
    session_factory: sessionmaker[Session],
    settings: Any,
    *,
    workspace_id: int,
    actor_user_id: int = 0,
    actor_email: str = "system",
    age_provider: Any = None,
) -> dict[str, Any]:
    """Scan every product in a workspace + log findings to the audit log.

    Args:
        session_factory: Sessionmaker callable.
        settings: App :class:`Settings` (for the Delta history reader).
        workspace_id: Workspace to scan.
        actor_user_id: Audit actor id (the run-as user, or 0 for system).
        actor_email: Audit actor email.
        age_provider: Override for the per-table age lookup
            ``(settings, catalog, schema, table) -> float | None``;
            defaults to the Delta-history reader.  Injected by tests.

    Returns:
        ``{"products_scanned", "violations": [...]}`` — each violation
        carries the product ref + the finding fields.
    """
    age_fn = age_provider or _table_age_days
    with session_factory() as session:
        products = list(
            session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            ).all()
        )
        product_meta = [(p.id, p.catalog_name, p.schema_name, p.contract_json) for p in products]

    violations: list[dict[str, Any]] = []
    for product_id, catalog, schema, contract_json in product_meta:
        try:
            contract = DataProductContract.model_validate(json.loads(contract_json))
        except TypeError, ValueError:
            continue
        class_index = classifications_for_schema(session_factory, catalog=catalog, schema=schema)
        effective = get_effective_policy(
            session_factory, data_product_id=product_id, workspace_id=workspace_id
        )
        retention_days = effective["retention_days"]["value"]

        findings = unclassified_pii_findings(contract, class_index)
        if retention_days is not None:
            table_ages = {
                t.name: age_fn(settings, catalog, schema, t.name) for t in contract.tables
            }
            findings.extend(retention_findings(retention_days, table_ages))

        target = f"data_product:{catalog}.{schema}"
        for finding in findings:
            violations.append(
                {**finding, "data_product_id": product_id, "ref": f"{catalog}.{schema}"}
            )
            log_action(
                session_factory,
                actor_user_id,
                actor_email,
                COMPLIANCE_VIOLATION_ACTION,
                target,
                finding,
                actor_role="system",
                workspace_id=workspace_id,
            )

    return {"products_scanned": len(product_meta), "violations": violations}
