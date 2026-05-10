"""ORM models for agent runs, operations, audit, reviews, and rewrite attempts.

Four tightly-related model files consolidated into one
``pointlessql.models.agent`` package whose ``__init__.py``
re-exports the full public surface so existing
``from pointlessql.models import AgentRun`` call sites resolve
unchanged.

Layout (all private — consumers go through ``pointlessql.models``):

* ``_runs``     — :class:`AgentRun` (the lifecycle row).
* ``_audit``    — :class:`AgentRunSource`, :class:`AgentRunOperation`,
                  :class:`AgentRunEvent`, :class:`AgentRunToolCall`
                  (the per-run audit-trail tables).
* ``_reviews``  — :class:`AgentReview`, :class:`ReviewDestination`
                  + ``REVIEW_SEVERITIES`` constant.
* ``_rewrites`` — :class:`RewriteAttempt` + ``REWRITE_VERDICTS`` /
                  per-verdict constants for the EXPLAIN-rewrite loop.
"""

from __future__ import annotations

from pointlessql.models.agent._audit import (
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
)
from pointlessql.models.agent._reviews import (
    REVIEW_SEVERITIES,
    AgentReview,
    ReviewDestination,
)
from pointlessql.models.agent._rewrites import (
    REWRITE_VERDICTS,
    VERDICT_AUTO_REWRITE_FAILED,
    VERDICT_AUTO_REWRITE_SUCCEEDED,
    VERDICT_HUMAN_APPROVAL_REQUIRED,
    VERDICT_ORIGINAL_APPROVED,
    RewriteAttempt,
)
from pointlessql.models.agent._runs import AgentRun

__all__ = [
    "REVIEW_SEVERITIES",
    "REWRITE_VERDICTS",
    "VERDICT_AUTO_REWRITE_FAILED",
    "VERDICT_AUTO_REWRITE_SUCCEEDED",
    "VERDICT_HUMAN_APPROVAL_REQUIRED",
    "VERDICT_ORIGINAL_APPROVED",
    "AgentReview",
    "AgentRun",
    "AgentRunEvent",
    "AgentRunOperation",
    "AgentRunSource",
    "AgentRunToolCall",
    "ReviewDestination",
    "RewriteAttempt",
]
