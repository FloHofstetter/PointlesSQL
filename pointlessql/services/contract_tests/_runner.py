"""Orchestrate one contract-test run for a product.

The runner walks every enabled :class:`DataProductContractTest` for
the named product, evaluates the assertion against either the live
table (resolved through the UC client) or a synthetic fixture (built
by :mod:`_generator`), persists a result row, and returns a summary.

Live mode is best-effort: when the UC client cannot find or open the
table the runner falls back to ``error`` rather than crashing the
loop — the surface reports that as the verdict.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import time
from typing import Any

import pyarrow as pa
from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductFixture,
)
from pointlessql.services.audit._core import log_action
from pointlessql.services.contract_tests._assertions import (
    AssertionVerdict,
    evaluate_assertion,
)
from pointlessql.services.contract_tests._generator import (
    generate_arrow_table,
)
from pointlessql.types import SessionFactory

#: Supported run modes.  ``synthetic`` evaluates against generated
#: fixture data; ``live`` (best-effort) loads the storage table.
RUN_MODES: tuple[str, ...] = ("live", "synthetic")


@dataclasses.dataclass(slots=True, frozen=True)
class RunOutcome:
    """Summary of one ``run_contract_tests`` call.

    Attributes:
        mode: Mode that produced the outcome.
        total: Total tests evaluated.
        passed: Count of ``pass`` verdicts.
        failed: Count of ``fail`` verdicts.
        errored: Count of ``error`` verdicts (config / load errors).
        results: List of per-test result dicts, in evaluation order.
    """

    mode: str
    total: int
    passed: int
    failed: int
    errored: int
    results: list[dict[str, Any]]


def run_contract_tests(
    session_factory: SessionFactory,
    *,
    data_product_id: int,
    mode: str = "synthetic",
    table_provider: Any = None,
    user_id: int = 0,
    user_email: str = "system",
    workspace_id: int = 1,
) -> RunOutcome:
    """Evaluate every enabled test for a product.

    Args:
        session_factory: Sessionmaker callable.
        data_product_id: Product to evaluate.
        mode: ``synthetic`` (default; uses fixtures) or ``live``
            (requires *table_provider*).
        table_provider: Optional callable ``(catalog, schema,
            table_name) -> pyarrow.Table | None`` the live mode
            consults.  When ``None`` and mode is ``live`` every test
            falls back to ``error``.
        user_id: Auditing principal id.
        user_email: Auditing principal email.
        workspace_id: Workspace the run belongs to.

    Returns:
        :class:`RunOutcome` summary.
    """
    if mode not in RUN_MODES:
        raise ValueError(f"unknown run mode: {mode}")
    with session_factory() as session:
        product = session.get(DataProduct, data_product_id)
        if product is None:
            raise LookupError(f"data product {data_product_id} not found")
        catalog = product.catalog_name
        schema = product.schema_name
        tests = session.scalars(
            select(DataProductContractTest)
            .where(DataProductContractTest.data_product_id == data_product_id)
            .where(DataProductContractTest.enabled.is_(True))
            .order_by(DataProductContractTest.id)
        ).all()
        fixtures_by_table: dict[str, DataProductFixture] = {}
        for row in session.scalars(
            select(DataProductFixture).where(DataProductFixture.data_product_id == data_product_id)
        ):
            fixtures_by_table[row.table_name] = row

    passed = failed = errored = 0
    results: list[dict[str, Any]] = []
    for test in tests:
        outcome = _run_single_test(
            session_factory,
            test=test,
            mode=mode,
            catalog=catalog,
            schema=schema,
            fixtures_by_table=fixtures_by_table,
            table_provider=table_provider,
        )
        results.append(outcome)
        if outcome["status"] == "pass":
            passed += 1
        elif outcome["status"] == "fail":
            failed += 1
        else:
            errored += 1
    log_action(
        session_factory,  # type: ignore[arg-type]
        user_id=user_id,
        user_email=user_email,
        action="contract_test.run",
        target=f"data_product:{data_product_id}",
        detail={
            "mode": mode,
            "total": len(tests),
            "passed": passed,
            "failed": failed,
            "errored": errored,
        },
        actor_role="system",
        workspace_id=workspace_id,
    )
    return RunOutcome(
        mode=mode,
        total=len(tests),
        passed=passed,
        failed=failed,
        errored=errored,
        results=results,
    )


def _run_single_test(
    session_factory: SessionFactory,
    *,
    test: DataProductContractTest,
    mode: str,
    catalog: str,
    schema: str,
    fixtures_by_table: dict[str, DataProductFixture],
    table_provider: Any,
) -> dict[str, Any]:
    """Evaluate one test and persist a result row."""
    started_at = time.monotonic()
    spec_dict = _decode_spec_dict(test.assertion_spec_json)
    target_table = str(spec_dict.get("table", "")) if spec_dict else ""
    table: pa.Table | None = None
    error_reason: str | None = None
    if mode == "synthetic":
        fixture = fixtures_by_table.get(target_table)
        if fixture is None and fixtures_by_table:
            fixture = next(iter(fixtures_by_table.values()))
        if fixture is None:
            error_reason = "no fixture available for synthetic mode"
        else:
            try:
                table = generate_arrow_table(
                    fixture.generator_spec_json,
                    row_count=int(fixture.row_count),
                )
            except ValueError as exc:
                error_reason = f"fixture generation failed: {exc}"
    else:
        if table_provider is None:
            error_reason = "live mode requires a table_provider"
        else:
            try:
                table = table_provider(catalog, schema, target_table)
            except Exception as exc:  # noqa: BLE001
                # bare-broad-ok: provider may raise arbitrary classes.
                error_reason = f"live table load failed: {exc}"
            if table is None and error_reason is None:
                error_reason = "live table not found"

    verdict: AssertionVerdict
    if table is None:
        verdict = AssertionVerdict(
            status="error",
            observation={"reason": error_reason or "no table to evaluate"},
        )
    else:
        try:
            verdict = evaluate_assertion(
                assertion_kind=test.assertion_kind,
                spec_json=test.assertion_spec_json,
                table=table,
            )
        except ValueError as exc:
            verdict = AssertionVerdict(
                status="error",
                observation={"reason": f"assertion spec invalid: {exc}"},
            )
    duration_ms = int((time.monotonic() - started_at) * 1000)
    now = datetime.datetime.now(datetime.UTC)
    obs_encoded = json.dumps(
        {
            "mode": mode,
            "table": target_table,
            **verdict.observation,
        },
        default=str,
        separators=(",", ":"),
    )
    with session_factory() as session:
        session.add(
            DataProductContractTestResult(
                contract_test_id=int(test.id),
                run_at=now,
                status=verdict.status,
                observation_json=obs_encoded,
                duration_ms=duration_ms,
            )
        )
        session.commit()
    return {
        "contract_test_id": int(test.id),
        "name": test.name,
        "assertion_kind": test.assertion_kind,
        "status": verdict.status,
        "observation": verdict.observation,
        "duration_ms": duration_ms,
    }


def _decode_spec_dict(spec_json: str | None) -> dict[str, Any]:
    """Decode the assertion spec for the runner without failing hard."""
    if not spec_json:
        return {}
    try:
        decoded = json.loads(spec_json)
    except json.JSONDecodeError, TypeError, ValueError:
        return {}
    return decoded if isinstance(decoded, dict) else {}
