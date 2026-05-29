"""Per-product contract tests: synthetic data + assertion runner.

Public surface for the contract-test subsystem.  Three concerns
sit under one package:

* :mod:`_generator` turns a Faker-style spec into a deterministic
  :class:`pyarrow.Table` the runner can evaluate without touching
  live storage.
* :mod:`_assertions` evaluates one of the six declarative kinds the
  CHECK constraint allows against an Arrow table + spec dict.
* :mod:`_runner` orchestrates both: pulls every enabled test for a
  product, runs the assertions in ``live`` or ``synthetic`` mode,
  persists a result row, and emits an audit entry.

CRUD on the fixture + test rows lives in :mod:`_crud` so the route
layer never reaches into the ORM directly.
"""

from __future__ import annotations

from pointlessql.services.contract_tests._assertions import (
    AssertionVerdict,
    evaluate_assertion,
)
from pointlessql.services.contract_tests._crud import (
    declare_contract_test,
    declare_fixture,
    delete_contract_test,
    delete_fixture,
    list_contract_tests,
    list_fixtures,
    list_results,
)
from pointlessql.services.contract_tests._generator import (
    generate_arrow_table,
)
from pointlessql.services.contract_tests._runner import (
    RunOutcome,
    run_contract_tests,
)

__all__ = [
    "AssertionVerdict",
    "RunOutcome",
    "declare_contract_test",
    "declare_fixture",
    "delete_contract_test",
    "delete_fixture",
    "evaluate_assertion",
    "generate_arrow_table",
    "list_contract_tests",
    "list_fixtures",
    "list_results",
    "run_contract_tests",
]
