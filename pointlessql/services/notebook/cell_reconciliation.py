"""Save-path cell-identity reconciliation.

The ``notebook_cells`` table maps each cell in a notebook to a stable
UUID so per-cell social rows (comments / reactions / follows / tags)
survive content edits.  The on-disk ``.py`` is IDE-agnostic — no UUID
sidecar can ride the marker grammar (memory rule
``feedback_notebook_py_editability``) — so identity must be derived
from the source text at save time.

Algorithm (three passes, executed inside the save transaction):

1. **Exact-hash** — every still-unmatched existing row with
   ``current_content_hash == new.hash`` is matched, tiebreaking by
   smallest ``|ordinal_hint - i|`` when multiple rows share a hash.
   Handles reorderings + no-op saves + whitespace-only edits.
2. **Similarity-gated ordinal** — for each new cell at position ``i``
   not yet matched, the unmatched existing row with
   ``ordinal_hint == i`` is matched **only if** the Jaccard similarity
   of its ``last_source_excerpt`` against the new source ≥ 0.5.  The
   gate prevents the dark-corner case "delete cell, insert different
   cell at same position" from stealing the UUID.  Pure edits at the
   same position pass the gate and keep their UUID.
3. **Fresh UUID** — any new cell still unmatched gets a freshly-minted
   UUID inserted.

Existing rows that finish all three passes unmatched are soft-deleted
via ``removed_at = NOW()`` so the social anchor stays reachable from
the notebook-level activity feed even after the cell is gone from the
file.

**Known limitation:** "cut + edit + paste-elsewhere" loses identity
because the moved-and-edited cell will fall below the similarity gate
at its new position.  Without on-disk cell-UUIDs there is no signal to
distinguish this from "delete + insert".  Accept and document; the
adversarial edit pattern is rare in practice.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.models.notebook import NotebookCellIdentity

logger = logging.getLogger(__name__)

_SOURCE_EXCERPT_LIMIT = 500
"""Cap on stored ``last_source_excerpt`` length; drives pass-2 gate."""

_SIMILARITY_THRESHOLD = 0.5
"""Jaccard score below which pass-2 ordinal fallback is rejected.

A value of 0.5 means: the new source must share at least half of its
3-char shingles with the candidate's last-known source for the UUID to
survive a same-position edit.  Whitespace-only and minor-edit cases
pass with ≥ 0.9; "wrote a completely different cell" lands well under
0.2 in practice.
"""

_SHINGLE_K = 3
"""Shingle width for the Jaccard similarity gate (3-grams)."""


@dataclass(frozen=True)
class ReconcileInput:
    """One new cell's identity-relevant slice on save.

    Attributes:
        content_hash: FNV-1a-64 hex digest of the cell's normalized
            source, as computed by
            :func:`pointlessql.services.notebook._doc.compute_content_hash`.
        source: Verbatim cell source text.  Only the first
            ``_SOURCE_EXCERPT_LIMIT`` chars are persisted on the
            identity row; the full text lives on disk.
    """

    content_hash: str
    source: str


@dataclass(frozen=True)
class ReconcileResult:
    """One reconciled cell's stable identity + position.

    Attributes:
        cell_id: 36-char UUID4 — the value the editor should embed in
            ``social_targets.entity_ref`` (composite
            ``"{notebook_id}:{cell_id}"``).
        content_hash: Identity-stable copy of the FNV digest.
        ordinal_hint: 0-based position in the file at save time.
        was_inserted: ``True`` for fresh UUIDs minted in pass 3,
            ``False`` for any existing row that was matched in pass 1
            or pass 2.
    """

    cell_id: str
    content_hash: str
    ordinal_hint: int
    was_inserted: bool


def reconcile(
    session: Session,
    *,
    workspace_id: int,
    notebook_id: str,
    new_cells: list[ReconcileInput],
) -> list[ReconcileResult]:
    """Reconcile new cell list against ``notebook_cells`` for *notebook_id*.

    Args:
        session: Active SQLAlchemy session.  Caller owns the
            transaction; this function INSERTs / UPDATEs but does not
            commit.
        workspace_id: Tenant scope, denormalised onto each inserted
            row so workspace-scoped queries skip the join.
        notebook_id: The 36-char UUID on :class:`Notebook`; the parent
            of every cell row this function touches.
        new_cells: Ordered list of one entry per cell in the saved
            file, in file order.

    Returns:
        One :class:`ReconcileResult` per input cell in the same order,
        carrying the stable UUID the editor should round-trip and the
        ``ordinal_hint`` the row was written at.
    """
    if not new_cells:
        _soft_delete_remaining(session, notebook_id, matched_ids=set())
        return []

    existing = list(
        session.execute(
            select(NotebookCellIdentity).where(
                NotebookCellIdentity.notebook_id == notebook_id,
                NotebookCellIdentity.removed_at.is_(None),
            )
        ).scalars()
    )
    matched_ids: set[str] = set()
    results: list[ReconcileResult | None] = [None] * len(new_cells)

    # PASS 1 — exact-hash match (with same-hash ordinal-proximity tiebreak).
    by_hash: dict[str, list[NotebookCellIdentity]] = {}
    for row in existing:
        by_hash.setdefault(row.current_content_hash, []).append(row)
    for i, new in enumerate(new_cells):
        candidates = [row for row in by_hash.get(new.content_hash, []) if row.id not in matched_ids]
        if not candidates:
            continue
        pick = min(candidates, key=lambda row: abs(row.ordinal_hint - i))
        matched_ids.add(pick.id)
        pick.ordinal_hint = i
        pick.last_source_excerpt = new.source[:_SOURCE_EXCERPT_LIMIT] or None
        results[i] = ReconcileResult(
            cell_id=pick.id,
            content_hash=new.content_hash,
            ordinal_hint=i,
            was_inserted=False,
        )

    # PASS 2 — similarity-gated ordinal fallback.
    by_ordinal: dict[int, NotebookCellIdentity] = {row.ordinal_hint: row for row in existing}
    for i, new in enumerate(new_cells):
        if results[i] is not None:
            continue
        candidate = by_ordinal.get(i)
        if candidate is None or candidate.id in matched_ids:
            continue
        score = _jaccard_shingles(candidate.last_source_excerpt or "", new.source)
        if score < _SIMILARITY_THRESHOLD:
            continue
        matched_ids.add(candidate.id)
        candidate.current_content_hash = new.content_hash
        candidate.ordinal_hint = i
        candidate.last_source_excerpt = new.source[:_SOURCE_EXCERPT_LIMIT] or None
        results[i] = ReconcileResult(
            cell_id=candidate.id,
            content_hash=new.content_hash,
            ordinal_hint=i,
            was_inserted=False,
        )

    # PASS 3 — anything still unmatched is a fresh cell.
    for i, new in enumerate(new_cells):
        if results[i] is not None:
            continue
        cell_id = str(uuid.uuid4())
        session.add(
            NotebookCellIdentity(
                id=cell_id,
                workspace_id=workspace_id,
                notebook_id=notebook_id,
                current_content_hash=new.content_hash,
                ordinal_hint=i,
                last_source_excerpt=(new.source[:_SOURCE_EXCERPT_LIMIT] or None),
            )
        )
        matched_ids.add(cell_id)
        results[i] = ReconcileResult(
            cell_id=cell_id,
            content_hash=new.content_hash,
            ordinal_hint=i,
            was_inserted=True,
        )

    _soft_delete_remaining(session, notebook_id, matched_ids=matched_ids)
    session.flush()
    # All positions are populated by construction; the cast tightens the
    # type without changing behaviour.
    return [r for r in results if r is not None]


def _soft_delete_remaining(session: Session, notebook_id: str, *, matched_ids: set[str]) -> None:
    """Mark unmatched live rows for *notebook_id* as removed.

    Runs as the close-out step of :func:`reconcile`.  Rows already
    tombstoned (``removed_at IS NOT NULL``) are skipped.

    Args:
        session: Active SQLAlchemy session.
        notebook_id: Parent notebook UUID.
        matched_ids: Set of cell-identity UUIDs the current save kept
            alive; everything else for this notebook is now stale.
    """
    now = datetime.datetime.now(datetime.UTC)
    live_rows = session.execute(
        select(NotebookCellIdentity).where(
            NotebookCellIdentity.notebook_id == notebook_id,
            NotebookCellIdentity.removed_at.is_(None),
        )
    ).scalars()
    for row in live_rows:
        if row.id not in matched_ids:
            row.removed_at = now


def _jaccard_shingles(a: str, b: str) -> float:
    """Return Jaccard similarity over k-char shingles of *a* and *b*.

    Args:
        a: First source text (the candidate's last-known excerpt).
        b: Second source text (the new cell's source).

    Returns:
        Jaccard score in ``[0.0, 1.0]``.  Empty inputs return 0.0
        (an empty cell never matches a non-empty one through pass 2).
    """
    if not a or not b:
        return 0.0
    a_norm = "\n".join(line.rstrip() for line in a.replace("\r\n", "\n").split("\n"))
    b_norm = "\n".join(line.rstrip() for line in b.replace("\r\n", "\n").split("\n"))
    a_shingles = _shingle_set(a_norm)
    b_shingles = _shingle_set(b_norm)
    if not a_shingles or not b_shingles:
        return 0.0
    inter = len(a_shingles & b_shingles)
    union = len(a_shingles | b_shingles)
    return inter / union if union else 0.0


def _shingle_set(text: str) -> set[str]:
    """Return the set of overlapping k-char shingles of *text*."""
    if len(text) < _SHINGLE_K:
        return {text} if text else set()
    return {text[i : i + _SHINGLE_K] for i in range(len(text) - _SHINGLE_K + 1)}


__all__: list[str] = ["ReconcileInput", "ReconcileResult", "reconcile"]
