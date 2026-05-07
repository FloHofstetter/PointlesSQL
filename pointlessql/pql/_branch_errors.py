"""Error family for the Delta-branching primitives.

Mirrors the ``RollbackError`` family in spirit: hard, domain-named
exceptions raised by ``pql.branch`` / ``pql.branch_promote`` /
``pql.branch_discard`` so callers (and the Control-Room UI) can map
them onto specific HTTP status codes and user-facing messages
without parsing free-form strings.

All errors derive from :class:`BranchError` (which itself inherits
from :class:`pointlessql.exceptions.PointlessSQLError`) so the
centralised RFC 9457 handler picks them up automatically.
"""

from __future__ import annotations

from typing import Any

from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import PointlessSQLError


class BranchError(PointlessSQLError):
    """Base class for every branch-primitive failure.

    Defaults to 409 ``branch_error`` — most subclasses surface a
    state conflict (already exists, in use, parent moved).
    Subclasses override to 404 / 422 where the failure mode is
    semantically distinct.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.BRANCH_ERROR


class BranchAlreadyExistsError(BranchError):
    """Raised by :func:`pql.branch` when *branch_name* already exists.

    The branch primitive refuses to "adopt" an existing schema —
    silently merging into someone else's schema would be a foot-gun.
    Caller must either pick a different name or explicitly discard
    the conflicting schema first.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.BRANCH_ALREADY_EXISTS


class BranchNotFoundError(BranchError):
    """Raised by :func:`pql.branch_discard` and :func:`pql.branch_promote`.

    Surfaces in two situations:

    * The named schema does not exist in UC at all.
    * The schema exists but carries no ``pointlessql.branch.*`` tags
      — discarding / promoting a non-branch schema would be an
      irrecoverable mistake, so we refuse rather than guess.
    """

    status_code: int = 404
    error_code: ErrorCode = ErrorCode.BRANCH_NOT_FOUND


class BranchCloudUnsupportedError(BranchError):
    """Raised when a branch op against cloud storage is denied by config.

    The default ``branch.cloud_strategy='error'`` setting refuses
    branches whose parent ``storage_root`` lives on object storage
    (``s3://``, ``gs://``, ``abfss://``, ``wasbs://``).  Operators
    flip the knob to ``'deep_copy'`` to opt into the bigger storage
    cost, or override via ``pql.branch(strategy='deep_copy')`` per
    call.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.BRANCH_CLOUD_UNSUPPORTED


class BranchPromotionConflictError(BranchError):
    """Raised by :func:`pql.branch_promote` when the parent moved.

    The promotion primitive snapshots the parent's per-table Delta
    versions when the branch is created.  If any of those versions
    has changed by promotion time, the branch's symlinks (or
    deep-copied files) point at a stale view of the parent, so
    pointer-swap promotion would silently re-anchor the parent at
    an obsolete state.  Callers must discard and re-branch.

    Attributes:
        status_code: Always 409.
        error_code: Always ``ErrorCode.BRANCH_PROMOTION_CONFLICT``.

    Args:
        table_name: Two-part ``schema.table`` name of the table that
            moved (the first detected — there may be more).
        expected_version: The version recorded in
            ``pointlessql.branch.parent_version_at_create`` for that
            table.
        actual_version: The current ``DeltaTable.version()`` at
            promotion time.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.BRANCH_PROMOTION_CONFLICT

    def __init__(self, table_name: str, expected_version: int, actual_version: int) -> None:
        self.table_name = table_name
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"branch promotion conflict on table {table_name!r}: "
            f"expected version {expected_version}, found {actual_version}.  "
            f"Discard the branch and re-branch from the current parent state."
        )

    def extension_members(self) -> dict[str, Any] | None:
        """Surface table+version triple as RFC 9457 extension members."""
        return {
            "table_name": self.table_name,
            "expected_version": self.expected_version,
            "actual_version": self.actual_version,
        }


class BranchInUseError(BranchError):
    """Raised when a branch op is incompatible with the current status.

    Examples:
        * ``branch_discard`` on a ``status='promoted'`` branch
          (promotion is final).
        * ``branch_promote`` on a ``status='promoted'`` or
          ``status='discarded'`` branch.

    Attributes:
        status_code: Always 409.
        error_code: Always ``ErrorCode.BRANCH_IN_USE``.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.BRANCH_IN_USE


class BranchOfBranchError(BranchError):
    """Raised by :func:`pql.branch` when source schema is itself a branch.

    Branch-of-branch is intentionally out of scope for v1 because the
    promotion conflict-detection (one parent-version snapshot per
    table) doesn't generalise to multi-level lineage.  A user who
    wants nested isolation should ``branch_promote`` the inner
    branch first, then re-branch from the now-promoted parent.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.BRANCH_OF_BRANCH
