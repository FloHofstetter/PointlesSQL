"""Pre-write contract enforcement: resolve schema → product → diff.

The :func:`check_contract_for_write` entry point is called from the
``pql.write`` / ``pql.merge`` primitives just inside the
``operation_context`` block, after the recorder is available but
before any Delta IO.  When the resolved diff is breaking, we build
a :class:`DataProductContractViolation` and tell the caller to
raise it; when the diff is non-breaking but drift is observed, we
return a ``schema_drift_warning`` outcome the caller stamps onto
:class:`OperationRecorder.pending_contract_event`.

Three early-exits keep the hot path cheap:

1. ``factory is None`` (interactive PQL, no audit run) → ``no_contract``
   with no DB lookup.
2. No row in ``data_products`` for the target schema → ``no_contract``.
3. Target table not declared in the cached contract → ``no_contract``.

Only when all three pass do we hit the diff.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import select

from pointlessql.data_products._diff import (
    ContractDiffResult,
    diff_contract_against_engine_columns,
)
from pointlessql.data_products._errors import DataProductContractViolation
from pointlessql.data_products._schema import DataProductContract
from pointlessql.models import AgentRun
from pointlessql.models.catalog._data_products import DataProduct

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


EnforcementOutcome = Literal[
    "compliant",
    "schema_drift_warning",
    "violated",
    "no_contract",
]


@dataclass
class EnforcementResult:
    """Outcome of one pre-write enforcement check.

    The caller (``pql/_write.py`` etc.) reads ``violation`` to
    decide whether to ``raise``; otherwise stamps
    ``(outcome, details)`` onto the recorder so the post-commit
    hook persists a :class:`DataProductContractEvent` row.
    """

    outcome: EnforcementOutcome
    details: dict[str, Any] = field(default_factory=dict[str, Any])
    data_product_id: int | None = None
    violation: DataProductContractViolation | None = None


def _load_cached_contract(
    session: Session,
    *,
    workspace_id: int,
    catalog: str,
    schema: str,
) -> tuple[DataProduct, DataProductContract] | None:
    """Look up the cache row + parse its ``contract_json``.

    Returns ``None`` when no row matches; the caller treats this
    as ``no_contract``.
    """
    row = session.execute(
        select(DataProduct).where(
            DataProduct.workspace_id == workspace_id,
            DataProduct.catalog_name == catalog,
            DataProduct.schema_name == schema,
        )
    ).scalar_one_or_none()
    if row is None:
        return None

    contract = DataProductContract.model_validate(json.loads(row.contract_json))
    return row, contract


def _resolve_workspace_id(session: Session, agent_run_id: str) -> int:
    """Look up an agent-run's ``workspace_id``.

    Defaults to the seeded workspace (id=1) when the parent row is
    missing; the audit lifecycle catches that mismatch separately.
    """
    ws = session.scalar(
        select(AgentRun.workspace_id).where(AgentRun.id == agent_run_id)
    )
    return int(ws or 1)


def check_contract_for_write(
    *,
    factory: sessionmaker[Session] | None,
    agent_run_id: str | None,
    catalog: str,
    schema: str,
    table: str,
    df_columns: list[tuple[str, str, str, bool]],
    mode: str,
) -> EnforcementResult:
    """Resolve target → cached contract → diff → outcome.

    Args:
        factory: SQLAlchemy session factory.  ``None`` short-circuits
            to ``no_contract`` (interactive PQL — no audit context to
            persist a violation against).
        agent_run_id: Owning audit run; the workspace scope is
            inherited from this run's ``workspace_id``.  ``None``
            short-circuits like ``factory=None``.
        catalog: UC catalog segment of the target table.
        schema: UC schema segment of the target table.
        table: UC table name (last segment).
        df_columns: Engine ``columns_info`` tuples for the to-be-
            written frame.
        mode: ``"overwrite"`` / ``"append"`` etc.  Affects which
            diffs are escalated to ``violated`` vs
            ``schema_drift_warning``.

    Returns:
        :class:`EnforcementResult` for the caller to act on.  When
        ``violation`` is non-None the caller MUST raise it before
        any IO happens.
    """
    if factory is None or agent_run_id is None:
        return EnforcementResult(outcome="no_contract")

    with factory() as session:
        workspace_id = _resolve_workspace_id(session, agent_run_id)
        cache = _load_cached_contract(
            session,
            workspace_id=workspace_id,
            catalog=catalog,
            schema=schema,
        )
        if cache is None:
            return EnforcementResult(outcome="no_contract")

        row, contract = cache
        table_contract = contract.get_table(table)
        if table_contract is None:
            return EnforcementResult(
                outcome="no_contract",
                data_product_id=row.id,
            )

        diff = diff_contract_against_engine_columns(table_contract, df_columns)

    return _classify_diff(
        diff,
        product_ref=f"{catalog}.{schema}",
        table_name=table,
        data_product_id=row.id,
        mode=mode,
    )


def _classify_diff(
    diff: ContractDiffResult,
    *,
    product_ref: str,
    table_name: str,
    data_product_id: int,
    mode: str,
) -> EnforcementResult:
    """Map a structured diff to an :class:`EnforcementResult`.

    Append mode tolerates extra columns and nullability widening
    silently (Delta merges them on write); only missing-required-
    columns and PK drops escalate.  Overwrite mode is stricter:
    type-mismatches also escalate.
    """
    if not diff.is_breaking and not (
        diff.extra_columns or diff.nullability_mismatches
    ):
        return EnforcementResult(
            outcome="compliant",
            details={},
            data_product_id=data_product_id,
        )

    if diff.is_breaking:
        violation = DataProductContractViolation(
            product_ref=product_ref,
            table_name=table_name,
            breaking_diff={
                "missing_columns": list(diff.missing_columns),
                "type_mismatches": [
                    {"name": n, "contract": c, "actual": a}
                    for (n, c, a) in diff.type_mismatches
                ],
                "dropped_pk_columns": list(diff.dropped_pk_columns),
                "mode": mode,
            },
        )
        return EnforcementResult(
            outcome="violated",
            details=diff.as_dict() | {"mode": mode},
            data_product_id=data_product_id,
            violation=violation,
        )

    return EnforcementResult(
        outcome="schema_drift_warning",
        details=diff.as_dict() | {"mode": mode},
        data_product_id=data_product_id,
    )
