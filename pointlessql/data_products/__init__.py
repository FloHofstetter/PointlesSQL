"""Data-product support: yaml-contract loader + DB cache + diff + enforcement.

A *data product* in PointlesSQL is the convention "this UC schema is
a named, owned, versioned bundle of tables".  The schema metadata
(steward, version, freshness SLA, expected per-table schema) lives
in a ``pointlessql.yaml`` file committed to the data team's repo;
the file is canonical (git-blame is the audit log).  When the loader
is invoked, the parsed contract is materialised into the
``data_products`` row so the ``/api/data-products`` UI and the
hermes-plugin tools don't need filesystem access.

Entry points:

* :class:`DataProductContract` (top-level Pydantic model)
* :func:`load_contract` (yaml → Pydantic → optional DB UPSERT)
* :class:`DataProductRef` (validated ``catalog.schema`` identifier)
* :class:`DataProductError` family (fail-loud exceptions)
* :func:`check_contract_for_write` (pre-write enforcement hook,
  Phase 50.3)
* :func:`diff_contract_against_table` (yaml ↔ on-disk Delta schema
  diff, Phase 50.3)
"""

from __future__ import annotations

from pointlessql.data_products._diff import (
    ActualColumn,
    ContractDiffResult,
    diff_contract_against_delta_table,
    diff_contract_against_engine_columns,
)
from pointlessql.data_products._enforce import (
    EnforcementResult,
    check_contract_for_write,
)
from pointlessql.data_products._errors import (
    DataProductContractViolation,
    DataProductError,
    DataProductFreshnessViolation,
    DataProductSchemaDrift,
    DataProductYamlInvalid,
)
from pointlessql.data_products._loader import (
    load_contract,
    load_contracts_for_workspace,
    load_contracts_from_paths,
    parse_yaml,
)
from pointlessql.data_products._name import DataProductRef
from pointlessql.data_products._schema import (
    DataProductColumnSpec,
    DataProductContract,
    DataProductTableContract,
)

__all__ = [
    "ActualColumn",
    "ContractDiffResult",
    "DataProductColumnSpec",
    "DataProductContract",
    "DataProductContractViolation",
    "DataProductError",
    "DataProductFreshnessViolation",
    "DataProductRef",
    "DataProductSchemaDrift",
    "DataProductTableContract",
    "DataProductYamlInvalid",
    "EnforcementResult",
    "check_contract_for_write",
    "diff_contract_against_delta_table",
    "diff_contract_against_engine_columns",
    "load_contract",
    "load_contracts_for_workspace",
    "load_contracts_from_paths",
    "parse_yaml",
]
