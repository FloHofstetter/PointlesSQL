"""Error family for the data-product primitives.

Mirrors the :class:`BranchError` family in spirit: hard, domain-named
exceptions raised when contract validation, schema diff, or freshness
SLA fails.  Subclasses derive from :class:`DataProductError` (which
itself inherits from :class:`pointlessql.exceptions.PointlessSQLError`)
so the centralised RFC 9457 handler picks them up automatically.
"""

from __future__ import annotations

from typing import Any

from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import PointlessSQLError


class DataProductError(PointlessSQLError):
    """Base class for every data-product failure.

    Defaults to 409 ``data_product_error`` — most subclasses surface
    a state conflict (contract violated, schema drifted, SLA missed).
    Subclasses override to 400 / 422 where the failure mode is
    semantically distinct.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.DATA_PRODUCT_ERROR


class DataProductContractViolation(DataProductError):
    """Raised when a write would breaking-change a declared contract.

    The diff between the yaml contract and the to-be-written frame
    surfaced a missing required column, an incompatible type swap,
    or a primary-key column drop.  The write is refused before any
    Delta IO happens — caller must either bump the contract major
    version (yaml side) or fix the frame to match.

    Attributes:
        status_code: Always 409.
        error_code: Always
            ``ErrorCode.DATA_PRODUCT_CONTRACT_VIOLATION``.

    Args:
        product_ref: ``catalog.schema`` of the data product.
        table_name: Last segment of the offending table.
        breaking_diff: Structured diff that triggered the refusal
            (missing_columns / type_mismatches / dropped_pk_columns).
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.DATA_PRODUCT_CONTRACT_VIOLATION

    def __init__(
        self,
        product_ref: str,
        table_name: str,
        breaking_diff: dict[str, Any],
    ) -> None:
        self.product_ref = product_ref
        self.table_name = table_name
        self.breaking_diff = breaking_diff
        super().__init__(
            f"data-product contract violation on {product_ref}.{table_name}: "
            f"{breaking_diff!r}.  "
            f"Bump the contract major version in pointlessql.yaml or "
            f"adjust the frame to match the current contract."
        )

    def extension_members(self) -> dict[str, Any] | None:
        """Surface product/table/diff triple as RFC 9457 extension."""
        return {
            "product_ref": self.product_ref,
            "table_name": self.table_name,
            "breaking_diff": self.breaking_diff,
        }


class DataProductSchemaDrift(DataProductError):
    """Raised by the live-diff endpoint when on-disk schema drifted.

    Used by ``GET /api/data-products/{ref}/diff`` to surface the
    discrepancy in JSON form when the caller asks for a strict diff.
    Pre-write hook does **not** raise this — it stamps a warning
    event instead and lets the write through (drift is detective,
    not preventive).

    Attributes:
        status_code: Always 422.
        error_code: Always ``ErrorCode.DATA_PRODUCT_SCHEMA_DRIFT``.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.DATA_PRODUCT_SCHEMA_DRIFT


class DataProductFreshnessViolation(DataProductError):
    """Raised by the freshness scanner when ``sla_minutes`` is exceeded.

    Carries the product reference + age so the CloudEvent and the
    sink-routing layer can surface specific context to the human
    steward.  The scanner stamps ``last_alerted_at`` for re-alert
    suppression (mirrors :class:`ExpectedLineageInbound`).

    Attributes:
        status_code: Always 422.
        error_code: Always
            ``ErrorCode.DATA_PRODUCT_FRESHNESS_VIOLATION``.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.DATA_PRODUCT_FRESHNESS_VIOLATION


class DataProductYamlInvalid(DataProductError):
    """Raised by :func:`load_contract` when the yaml fails validation.

    Wraps :class:`pydantic.ValidationError` and ``yaml.YAMLError``
    into a single project exception so the loader's HTTP callers
    surface a consistent ``400 data_product_yaml_invalid`` shape.

    Attributes:
        status_code: Always 400.
        error_code: Always ``ErrorCode.DATA_PRODUCT_YAML_INVALID``.
    """

    status_code: int = 400
    error_code: ErrorCode = ErrorCode.DATA_PRODUCT_YAML_INVALID
