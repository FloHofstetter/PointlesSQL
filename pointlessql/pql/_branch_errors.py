"""Error family for the  Delta-branching primitives.

Mirrors the  ``RollbackError`` family in spirit: hard,
domain-named exceptions raised by ``pql.branch`` /
``pql.branch_promote`` / ``pql.branch_discard`` so callers (and
the Control-Room UI) can map them onto specific HTTP status codes
and user-facing messages without parsing free-form strings.

All errors derive from :class:`BranchError` so call sites can
``except BranchError`` for a coarse "branch-op failed" gate while
still surfacing the specific subclass for telemetry and UI.
"""

from __future__ import annotations


class BranchError(Exception):
    """Base class for every branch-primitive failure."""


class BranchAlreadyExistsError(BranchError):
    """Raised by :func:`pql.branch` when *branch_name* already exists.

    The branch primitive refuses to "adopt" an existing schema —
    silently merging into someone else's schema would be a foot-gun.
    Caller must either pick a different name or explicitly discard
    the conflicting schema first.
    """


class BranchNotFoundError(BranchError):
    """Raised by :func:`pql.branch_discard` and :func:`pql.branch_promote`.

    Surfaces in two situations:

    * The named schema does not exist in UC at all.
    * The schema exists but carries no ``pointlessql.branch.*`` tags
      — discarding / promoting a non-branch schema would be an
      irrecoverable mistake, so we refuse rather than guess.
    """


class BranchCloudUnsupportedError(BranchError):
    """Raised when a branch op against cloud storage is denied by config.

    The default ``branch.cloud_strategy='error'`` setting refuses
    branches whose parent ``storage_root`` lives on object storage
    (``s3://``, ``gs://``, ``abfss://``, ``wasbs://``).  Operators
    flip the knob to ``'deep_copy'`` to opt into the bigger storage
    cost, or override via ``pql.branch(strategy='deep_copy')`` per
    call.
    """


class BranchPromotionConflictError(BranchError):
    """Raised by :func:`pql.branch_promote` when the parent moved.

    The promotion primitive snapshots the parent's per-table Delta
    versions when the branch is created.  If any of those versions
    has changed by promotion time, the branch's symlinks (or
    deep-copied files) point at a stale view of the parent, so
    pointer-swap promotion would silently re-anchor the parent at
    an obsolete state.  Callers must discard and re-branch.

    Args:
        table_name: Two-part ``schema.table`` name of the table that
            moved (the first detected — there may be more).
        expected_version: The version recorded in
            ``pointlessql.branch.parent_version_at_create`` for that
            table.
        actual_version: The current ``DeltaTable.version()`` at
            promotion time.
    """

    def __init__(self, table_name: str, expected_version: int, actual_version: int) -> None:
        self.table_name = table_name
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"branch promotion conflict on table {table_name!r}: "
            f"expected version {expected_version}, found {actual_version}.  "
            f"Discard the branch and re-branch from the current parent state."
        )


class BranchInUseError(BranchError):
    """Raised when a branch op is incompatible with the current status.

    Examples:
        * ``branch_discard`` on a ``status='promoted'`` branch
          (promotion is final).
        * ``branch_promote`` on a ``status='promoted'`` or
          ``status='discarded'`` branch.
    """


class BranchOfBranchError(BranchError):
    """Raised by :func:`pql.branch` when source schema is itself a branch.

    Branch-of-branch is intentionally out of scope for v1 because the
    promotion conflict-detection (one parent-version snapshot per
    table) doesn't generalise to multi-level lineage.  A user who
    wants nested isolation should ``branch_promote`` the inner
    branch first, then re-branch from the now-promoted parent.
    """
