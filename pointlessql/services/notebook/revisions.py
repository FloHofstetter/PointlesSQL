"""Notebook revision snapshots + diff.

Each save event optionally freezes the notebook's (cells + outputs)
state into a :class:`NotebookRevision` row so the editor can render
a Monaco-driven diff between two points in time and a future replay
surface can re-execute an old revision against today's
data.

This module owns:

* :func:`canonical_payload` — deterministic JSON encoding of the
  ``(cells, outputs)`` pair used both for SHA-256 hashing and the
  Monaco diff side-by-side.
* :func:`create_revision` — write a new snapshot; idempotent on the
  canonical hash so saving an unchanged notebook does not blow up
  the history list.
* :func:`list_revisions` / :func:`get_revision` — read accessors
  the REST layer maps over.
* :func:`compute_diff` — cell-by-cell diff using the stable
  ``content_hash`` identity, returning ``added`` / ``removed`` /
  ``changed`` lists.

Cryptographic signing via shoreguard-fresh is deferred until the
shoreguard signing API ships (the ``signature_alg`` / ``signature``
columns are nullable and reserved for it).  Every snapshot still
records its deterministic SHA-256, so a future migration can sign
historical rows without re-writing the payload.
"""

from __future__ import annotations

import hashlib
import json
import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookRevision


def canonical_payload(
    *, cells: list[dict[str, Any]], outputs: list[dict[str, Any]]
) -> tuple[str, str, str]:
    """Encode cells + outputs as deterministic JSON and hash the result.

    Args:
        cells: One dict per cell with the keys ``content_hash`` /
            ``cell_type`` / ``source`` / ``result_var`` / ``tags``.
        outputs: ``notebook_outputs`` rows in load-time shape; only
            the durable fields (``content_hash`` /
            ``kernel_session_id`` / ``output_index`` / ``msg_type``
            / ``content`` / ``metadata``) survive the canonical
            encoding so the hash does not drift when transient
            columns (``created_at``) change.

    Returns:
        Triple ``(cells_json, outputs_json, content_sha256)`` where
        the two JSON strings are stable-sorted by key + use
        no-whitespace separators so the SHA-256 is byte-stable.
    """
    cells_canonical = [
        {
            "content_hash": str(c.get("content_hash") or ""),
            "cell_type": str(c.get("cell_type") or "code"),
            "source": str(c.get("source") or ""),
            "result_var": c.get("result_var"),
            "tags": list(c.get("tags") or []),
        }
        for c in cells
    ]
    outputs_canonical = [
        {
            "content_hash": str(o.get("content_hash") or ""),
            "kernel_session_id": str(o.get("kernel_session_id") or ""),
            "output_index": int(o.get("output_index") or 0),
            "msg_type": str(o.get("msg_type") or ""),
            "content": o.get("content"),
            "metadata": o.get("metadata"),
        }
        for o in outputs
    ]
    cells_json = json.dumps(cells_canonical, sort_keys=True, separators=(",", ":"))
    outputs_json = json.dumps(outputs_canonical, sort_keys=True, separators=(",", ":"))
    sha = hashlib.sha256()
    sha.update(cells_json.encode("utf-8"))
    sha.update(b"|")
    sha.update(outputs_json.encode("utf-8"))
    return cells_json, outputs_json, sha.hexdigest()


def create_revision(
    session: Session,
    *,
    notebook_id: str,
    cells: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    created_by: str | None,
    message: str | None = None,
) -> NotebookRevision:
    """Snapshot (cells + outputs) under ``notebook_id``.

    Idempotent on the canonical ``content_sha256`` — saving an
    unchanged notebook returns the existing row rather than inserting
    a duplicate.  Newly inserted rows get the most-recent prior
    revision's id as their ``parent_revision_id`` so the diff
    surface can render an ancestry chain.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        cells: Cell list.
        outputs: ``notebook_outputs`` rows in load-time shape.
        created_by: Author email; ``None`` for agent / scheduler
            writers.
        message: Optional human-readable save message.

    Returns:
        The :class:`NotebookRevision` row (new or pre-existing).

    Raises:
        ValidationError: When ``notebook_id`` is unknown.
    """
    notebook = session.get(Notebook, notebook_id)
    if notebook is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    cells_json, outputs_json, sha = canonical_payload(cells=cells, outputs=outputs)
    existing = session.execute(
        select(NotebookRevision).where(
            NotebookRevision.notebook_id == notebook_id,
            NotebookRevision.content_sha256 == sha,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    parent = session.execute(
        select(NotebookRevision)
        .where(NotebookRevision.notebook_id == notebook_id)
        .order_by(NotebookRevision.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    rev = NotebookRevision(
        revision_uuid=str(_uuid.uuid4()),
        notebook_id=notebook_id,
        parent_revision_id=parent.id if parent is not None else None,
        created_by=created_by,
        message=message,
        cells_json=cells_json,
        outputs_json=outputs_json,
        content_sha256=sha,
    )
    session.add(rev)
    session.flush()
    return rev


def row_to_envelope(row: NotebookRevision) -> dict[str, Any]:
    """Serialise one revision row for REST output."""
    return {
        "revision_uuid": row.revision_uuid,
        "notebook_id": row.notebook_id,
        "parent_revision_uuid": _parent_uuid(row),
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "message": row.message,
        "content_sha256": row.content_sha256,
        "signed": row.signature is not None,
        "signature_alg": row.signature_alg,
    }


def set_revision_signature(
    session: Session,
    *,
    revision_uuid: str,
    signature: str,
    signature_alg: str,
) -> NotebookRevision:
    """Persist a signature blob produced by an external signer.

    reserved ``signature`` + ``signature_alg`` for the
    forthcoming shoreguard sign-revision API.  Phase 97 Wave-D ships
    the *receiving* half: any out-of-band signer (shoreguard, an
    enterprise reviewer, a CI step) POSTs the signature back here and
    the row gets ``signed=true`` for the UI badge.  No verification is
    done on receipt — the alg field tells consumers how to verify
    (e.g. ``ed25519:<key-id>``) and the receiver's role gate is the
    admin-only REST surface.

    Args:
        session: A SQLAlchemy session.
        revision_uuid: 36-char revision UUID.
        signature: Base64 / hex signature blob.
        signature_alg: Algorithm identifier (free-text; consumers parse).

    Returns:
        The updated row.

    Raises:
        ValidationError: When the UUID is unknown or *signature* /
            *signature_alg* are empty.
    """
    if not signature or not signature_alg:
        raise ValidationError("signature and signature_alg must both be non-empty")
    row = session.execute(
        select(NotebookRevision).where(NotebookRevision.revision_uuid == revision_uuid)
    ).scalar_one_or_none()
    if row is None:
        raise ValidationError(f"revision {revision_uuid!r} not found")
    row.signature = signature
    row.signature_alg = signature_alg
    session.flush()
    return row


def _parent_uuid(row: NotebookRevision) -> str | None:
    """Resolve the parent revision's UUID without an explicit JOIN."""
    if row.parent_revision_id is None:
        return None
    sess = Session.object_session(row)
    if sess is None:
        return None
    parent = sess.get(NotebookRevision, row.parent_revision_id)
    return parent.revision_uuid if parent is not None else None


def list_revisions(
    session: Session,
    *,
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return revisions for one notebook, newest first.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        limit: Newest-N cap; defaults to 50.
        offset: Zero-indexed row offset for paginated reads.
            Defaults to 0 (no skip).

    Returns:
        List of revision dicts in ``created_at desc`` order.
    """
    rows = (
        session.execute(
            select(NotebookRevision)
            .where(NotebookRevision.notebook_id == notebook_id)
            .order_by(NotebookRevision.created_at.desc())
            .offset(max(0, int(offset)))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [row_to_envelope(r) for r in rows]


def get_revision(session: Session, *, revision_uuid: str) -> dict[str, Any] | None:
    """Return one revision's full payload (cells + outputs included).

    Args:
        session: A SQLAlchemy session.
        revision_uuid: The 36-char UUID.

    Returns:
        Revision dict with parsed ``cells`` + ``outputs`` lists, or
        ``None`` when the UUID is unknown.
    """
    row = session.execute(
        select(NotebookRevision).where(NotebookRevision.revision_uuid == revision_uuid)
    ).scalar_one_or_none()
    if row is None:
        return None
    out = row_to_envelope(row)
    out["cells"] = json.loads(row.cells_json)
    out["outputs"] = json.loads(row.outputs_json)
    return out


def compute_diff(session: Session, *, left_uuid: str, right_uuid: str) -> dict[str, Any]:
    """Cell-by-cell diff between two revisions.

    Diff uses the stable cell ``content_hash`` so a pure reorder
    surfaces as ``moved`` rather than ``changed``.  Returned shape
    is intentionally Monaco-friendly: per-cell entries carry the
    full source so the front-end can pass ``original`` + ``modified``
    straight to ``monaco.editor.createDiffEditor``.

    Args:
        session: A SQLAlchemy session.
        left_uuid: Older revision.
        right_uuid: Newer revision.

    Returns:
        Diff envelope ``{added, removed, changed, moved, unchanged}``;
        each list holds ``{content_hash, cell_type, ...}`` dicts.

    Raises:
        ValidationError: When either UUID is unknown.
    """
    left = get_revision(session, revision_uuid=left_uuid)
    right = get_revision(session, revision_uuid=right_uuid)
    if left is None:
        raise ValidationError(f"revision {left_uuid!r} not found")
    if right is None:
        raise ValidationError(f"revision {right_uuid!r} not found")

    left_cells = {c["content_hash"]: (idx, c) for idx, c in enumerate(left["cells"])}
    right_cells = {c["content_hash"]: (idx, c) for idx, c in enumerate(right["cells"])}

    left_hashes = set(left_cells.keys())
    right_hashes = set(right_cells.keys())

    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    moved: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    for h in right_hashes - left_hashes:
        idx, cell = right_cells[h]
        added.append({"position": idx, "cell": cell})
    for h in left_hashes - right_hashes:
        idx, cell = left_cells[h]
        removed.append({"position": idx, "cell": cell})
    for h in left_hashes & right_hashes:
        l_idx, _l_cell = left_cells[h]
        r_idx, r_cell = right_cells[h]
        entry = {"content_hash": h, "left_position": l_idx, "right_position": r_idx}
        if l_idx != r_idx:
            moved.append({**entry, "cell": r_cell})
        else:
            unchanged.append({**entry, "cell": r_cell})

    # ``changed`` collapses "removed + added at the same position"
    # into a single Monaco-paired diff entry — the front-end renders
    # one diff editor per pair rather than two separate cards.
    changed: list[dict[str, Any]] = []
    used_removed: set[int] = set()
    used_added: set[int] = set()
    for idx, ad in enumerate(added):
        for ridx, rm in enumerate(removed):
            if ridx in used_removed:
                continue
            if ad["position"] == rm["position"]:
                changed.append(
                    {
                        "position": ad["position"],
                        "old": rm["cell"],
                        "new": ad["cell"],
                    }
                )
                used_removed.add(ridx)
                used_added.add(idx)
                break
    added = [a for i, a in enumerate(added) if i not in used_added]
    removed = [r for i, r in enumerate(removed) if i not in used_removed]

    return {
        "left_uuid": left_uuid,
        "right_uuid": right_uuid,
        "added": added,
        "removed": removed,
        "changed": changed,
        "moved": moved,
        "unchanged": unchanged,
    }


__all__ = [
    "canonical_payload",
    "compute_diff",
    "create_revision",
    "get_revision",
    "list_revisions",
    "set_revision_signature",
]
