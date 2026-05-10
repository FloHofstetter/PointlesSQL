"""Refusal-mode exception classes for ``pql.rollback``.

Five classes cover the contract the rollback primitive surfaces:
target-not-found, ambiguous (multi-op runs), invalid (creation ops),
and stale (intervening writes).  All five are raised by the rollback
primitive in :mod:`pointlessql.pql._rollback`; this module is the
carrier so route handlers can ``import`` them without pulling
deltalake in.

The base class :class:`RollbackError` reparents
:class:`PointlessSQLError` so the centralised FastAPI handler picks
every refusal up automatically — no inline ``except`` translation
at the route layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.exceptions import PointlessSQLError
from pointlessql.types import ErrorCode

if TYPE_CHECKING:
    from pointlessql.models import AgentRunOperation


class RollbackError(PointlessSQLError):
    """Base class for ``pql.rollback`` failures.

    Subclasses encode the four refusal modes the rollback primitive
    surfaces: target-not-found, ambiguous (multi-op runs), invalid
    (creation ops), and stale (intervening writes).  Raising any
    subclass guarantees no Delta state has been mutated — the
    ``DeltaTable.restore(...)`` call is gated on all four checks
    passing first.

    Reparented from :class:`Exception` so the centralised
    :class:`PointlessSQLError` handler picks every refusal up
    automatically (no inline ``except`` translation at the route).
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.ROLLBACK_ERROR


class RollbackTargetNotFound(RollbackError):
    """No ``agent_run_operations`` row matches ``(run_id, target)``.

    Either the run never wrote to the named target, or the run id is
    unknown to the registry.  The caller should treat this as a
    user error (likely mistyped FQN or wrong run id).
    """

    status_code: int = 404
    error_code: ErrorCode = ErrorCode.ROLLBACK_TARGET_NOT_FOUND


class RollbackAmbiguous(RollbackError):
    """Multiple ops in one run touched the same target.

    Common for runs that ran ``pql.merge`` more than once on the
    same table.  The caller must re-issue with an explicit
    ``op_ordinal=N`` to disambiguate.  ``self.candidates`` carries
    the matching operation rows ordered by ``ordinal``; each row
    exposes the ``ordinal`` / ``delta_version_before`` /
    ``delta_version_after`` triple the caller needs to pick.

    Attributes:
        status_code: HTTP 409 — surfaced via the FastAPI handler.
        error_code: :data:`ErrorCode.ROLLBACK_AMBIGUOUS` for the
            problem-detail envelope.

    Args:
        candidates: The list of matching operation rows ordered
            by ``ordinal``.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.ROLLBACK_AMBIGUOUS

    def __init__(self, candidates: list[AgentRunOperation]) -> None:
        ordinals = [c.ordinal for c in candidates]
        super().__init__(
            f"rollback: {len(candidates)} ops match (ordinals={ordinals}); "
            f"pass op_ordinal=N to pick"
        )
        self.candidates = candidates

    def extension_members(self) -> dict[str, Any] | None:
        """Surface candidate ordinals as RFC 9457 extension members."""
        return {"candidate_ordinals": [c.ordinal for c in self.candidates]}


class RollbackInvalid(RollbackError):
    """Chosen op has ``delta_version_before is None``.

    The op created the table, so rolling it back would mean
    dropping the table — that is a different primitive
    (``pql.drop_table``) and is out of v1 scope.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.ROLLBACK_INVALID


class RollbackStale(RollbackError):
    """Current Delta version moved past the targeted op's version.

    Restoring would silently overwrite intervening writes by other
    runs.  The caller must re-issue with ``allow_force=True`` to
    confirm they accept that loss.  ``self.current_version`` /
    ``self.expected_version`` / ``self.intervening_op_count``
    carry the staleness-check result for the UI confirmation
    dialog.

    Attributes:
        status_code: HTTP 409 — surfaced via the FastAPI handler.
        error_code: :data:`ErrorCode.ROLLBACK_STALE` for the
            problem-detail envelope.

    Args:
        current_version: ``DeltaTable.version()`` at the moment
            of the staleness check.
        expected_version: The targeted op's
            ``delta_version_after``; equal to
            ``current_version`` for the non-stale path.
        intervening_op_count: Number of ``agent_run_operations``
            rows with the same ``target_table`` and a
            ``delta_version_after`` strictly greater than the
            targeted op's.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.ROLLBACK_STALE

    def __init__(
        self,
        *,
        current_version: int,
        expected_version: int,
        intervening_op_count: int,
    ) -> None:
        super().__init__(
            f"rollback stale: current_version={current_version} "
            f"expected={expected_version} "
            f"intervening_op_count={intervening_op_count}; "
            f"pass allow_force=True to overwrite intervening writes"
        )
        self.current_version = current_version
        self.expected_version = expected_version
        self.intervening_op_count = intervening_op_count

    def extension_members(self) -> dict[str, Any] | None:
        """Surface staleness-check fields as RFC 9457 extension members."""
        return {
            "current_version": self.current_version,
            "expected_version": self.expected_version,
            "intervening_op_count": self.intervening_op_count,
        }
