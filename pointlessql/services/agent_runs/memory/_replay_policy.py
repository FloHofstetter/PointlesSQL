"""Replay-policy types shared between dispatcher and facade.

These live in their own module so the facade can import them
without dragging the heavy ``_replay`` dispatcher (and the
primitive imports it pulls) into the import graph of every caller
that just wants to *talk about* a policy.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import StrEnum

from pointlessql.types import OpId, OpName, RunId


class ReplayPolicy(StrEnum):
    """How the replay dispatcher treats unsafe-to-replay operations.

    The split exists because the *same* recorded operation log can be
    replayed under different intentions: a CI-time replay-test wants
    `STRICT` (fail loud on anything ambiguous), an interactive
    "rebuild my branch" wants `SKIP_UNSAFE` (skip dbt / train_model
    / destructive-mutation ops but proceed with the safe ones), and
    `LENIENT` exists for the rare case where the caller has audited
    every op and is willing to take the risk.
    """

    STRICT = "strict"
    SKIP_UNSAFE = "skip_unsafe"
    LENIENT = "lenient"


@dataclass(frozen=True, slots=True)
class ReplaySkip:
    """One operation that the dispatcher refused to re-invoke.

    Attributes:
        op_id: PK of the source :class:`AgentRunOperation` row.
        op_name: The op_name of the skipped operation.
        reason: Short machine-readable reason
            (``"unsafe_op"``, ``"dispatch_failed"``,
            ``"target_rewrite_failed"``).
    """

    op_id: OpId
    op_name: OpName
    reason: str


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Final stats of a replay invocation.

    Attributes:
        replay_run_id: The :class:`AgentRun.id` of the new run that
            wraps the replayed operations.
        ops_replayed: Number of source ops that were re-invoked
            successfully.
        ops_skipped: List of :class:`ReplaySkip` entries describing
            every op the dispatcher refused to touch.
        started_at: Wall-clock instant the replay began.
        finished_at: Wall-clock instant the replay ended.
    """

    replay_run_id: RunId
    ops_replayed: int
    ops_skipped: tuple[ReplaySkip, ...]
    started_at: datetime.datetime
    finished_at: datetime.datetime
