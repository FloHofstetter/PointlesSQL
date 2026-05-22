"""Shared constants for the data-product comments surfaces.

The values stay here (not in :mod:`._helpers`) so test files and the
``social_routes`` polymorphic dispatcher can import them without
pulling in the route bodies and their DB session imports.
"""

from __future__ import annotations

import re

# Phase 72.5 — audit-bound discussions sidecar.  Each comment
# POST / DELETE drops an ``audit_log`` row alongside the
# DataProductComment write so the Phase-18.7 audit-search FTS
# index picks comments up.  The comments stay system-of-record;
# the audit row is a discoverability mirror.
DISCUSSION_POSTED = "audit.discussion.posted"
DISCUSSION_DELETED = "audit.discussion.deleted"
DISCUSSION_ANSWER_ACCEPTED = "audit.discussion.answer_accepted"
DISCUSSION_MENTION_AMBIGUOUS = "audit.discussion.mention_ambiguous"
BODY_PREVIEW_LEN = 140

# Phase 76.1 — comment-category enum + reactions canonical set.
# Phase 101 Wave-D added ``review`` for cell-level review decisions
# (notebook_cell entity-kind); kept in lockstep with
# ``_polymorphic_handlers._shared.ALLOWED_CATEGORIES``.
ALLOWED_CATEGORIES: tuple[str, ...] = (
    "general",
    "question",
    "announcement",
    "idea",
    "review",
)
ALLOWED_EMOJI: tuple[str, ...] = ("👍", "❤️", "🎉", "😄", "😕", "👀")


MAX_THREAD_DEPTH = 5
MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")
# Display-name mention pattern — must start with a letter and not
# contain '@' (so it never matches the email path above).  Bounded
# length to prevent runaway regex matches on adversarial input.
DISPLAYNAME_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9._-]{2,30})\b")
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
