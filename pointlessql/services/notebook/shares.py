"""Public share + dashboard render (Phase 100).

Mints an unguessable v4 UUID per share so a notebook can be reached
read-only under ``/share/notebook/{share_uuid}`` without auth.  Two
modes share the same row:

* ``snapshot`` — freezes the current state as a Phase-97
  :class:`NotebookRevision` and stores the revision UUID; subsequent
  edits do not leak.  Re-publish updates the snapshot under the
  same share UUID so links stay stable.
* ``live`` — link reflects the current ``.py`` + last-known
  outputs.  No revision pin.

The ``dashboard_mode`` flag toggles between the regular notebook
render (cells + outputs) and the dashboard render that strips code
cells and shows only markdown + outputs.  Both modes call into the
existing :func:`pointlessql.services.notebook.export.render_notebook_html`
pipeline so the chrome stays consistent.
"""

from __future__ import annotations

import datetime
import uuid as _uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import (
    Notebook,
    NotebookRevision,
    NotebookShare,
)

ShareMode = Literal["snapshot", "live"]
VALID_SHARE_MODES: tuple[str, ...] = ("snapshot", "live")


def create_share(
    session: Session,
    *,
    notebook_id: str,
    share_mode: ShareMode,
    dashboard_mode: bool,
    revision_uuid: str | None,
    created_by_user_id: int | None,
    expires_at: datetime.datetime | None = None,
) -> NotebookShare:
    """Mint a new share row.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        share_mode: ``"snapshot"`` or ``"live"``.
        dashboard_mode: ``True`` to render only markdown + outputs.
        revision_uuid: For ``snapshot`` mode — required.  Must
            already exist via :class:`NotebookRevision`.
        created_by_user_id: Audit pointer to the publisher.
        expires_at: Optional auto-expiry.

    Returns:
        The persisted :class:`NotebookShare` row.

    Raises:
        ValidationError: On bad input shape or unknown FK.
    """
    if share_mode not in VALID_SHARE_MODES:
        raise ValidationError(
            f"share_mode must be one of {VALID_SHARE_MODES}; got {share_mode!r}"
        )
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    if share_mode == "snapshot":
        if not revision_uuid:
            raise ValidationError(
                "share_mode='snapshot' requires revision_uuid"
            )
        rev = session.execute(
            select(NotebookRevision).where(
                NotebookRevision.revision_uuid == revision_uuid,
                NotebookRevision.notebook_id == notebook_id,
            )
        ).scalar_one_or_none()
        if rev is None:
            raise ValidationError(
                f"revision {revision_uuid!r} not found under notebook"
            )
    else:
        revision_uuid = None  # ignore stray value for live mode
    row = NotebookShare(
        share_uuid=str(_uuid.uuid4()),
        notebook_id=notebook_id,
        share_mode=share_mode,
        dashboard_mode=bool(dashboard_mode),
        revision_uuid=revision_uuid,
        created_by_user_id=created_by_user_id,
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()
    return row


def update_share(
    session: Session,
    *,
    share_uuid: str,
    share_mode: ShareMode | None = None,
    dashboard_mode: bool | None = None,
    revision_uuid: str | None = None,
    expires_at: datetime.datetime | None = None,
) -> NotebookShare:
    """Update an existing share row in place.

    Re-publish: keeps the same ``share_uuid`` so external links stay
    stable.  ``None`` arguments leave the corresponding column
    untouched; explicit ``revision_uuid`` is required when flipping
    to ``snapshot`` mode.

    Args:
        session: A SQLAlchemy session.
        share_uuid: The 36-char UUID minted at create time.
        share_mode: Optional new mode.
        dashboard_mode: Optional new render flag.
        revision_uuid: Required when ``share_mode == 'snapshot'``.
        expires_at: Optional new expiry.

    Returns:
        The updated row.

    Raises:
        ValidationError: When ``share_uuid`` is unknown or the
            snapshot mode lands without a revision.
    """
    row = session.execute(
        select(NotebookShare).where(NotebookShare.share_uuid == share_uuid)
    ).scalar_one_or_none()
    if row is None:
        raise ValidationError(f"share {share_uuid!r} not found")
    if row.revoked_at is not None:
        raise ValidationError(f"share {share_uuid!r} is revoked")
    target_mode = share_mode or row.share_mode
    if target_mode not in VALID_SHARE_MODES:
        raise ValidationError(
            f"share_mode must be one of {VALID_SHARE_MODES}"
        )
    if target_mode == "snapshot":
        if revision_uuid is None and row.revision_uuid is None:
            raise ValidationError(
                "share_mode='snapshot' requires revision_uuid"
            )
        if revision_uuid is not None:
            rev = session.execute(
                select(NotebookRevision).where(
                    NotebookRevision.revision_uuid == revision_uuid,
                    NotebookRevision.notebook_id == row.notebook_id,
                )
            ).scalar_one_or_none()
            if rev is None:
                raise ValidationError(
                    f"revision {revision_uuid!r} not under share's notebook"
                )
            row.revision_uuid = revision_uuid
    else:
        row.revision_uuid = None
    row.share_mode = target_mode
    if dashboard_mode is not None:
        row.dashboard_mode = bool(dashboard_mode)
    if expires_at is not None:
        row.expires_at = expires_at
    session.flush()
    return row


def revoke_share(session: Session, *, share_uuid: str) -> bool:
    """Soft-revoke a share row; idempotent.

    Args:
        session: A SQLAlchemy session.
        share_uuid: The 36-char UUID.

    Returns:
        ``True`` when the row was newly revoked; ``False`` when
        the share was unknown or already revoked.
    """
    row = session.execute(
        select(NotebookShare).where(NotebookShare.share_uuid == share_uuid)
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = datetime.datetime.now(datetime.UTC)
    session.flush()
    return True


def get_active_share(
    session: Session, *, share_uuid: str
) -> NotebookShare | None:
    """Return the share row if it is active (not revoked + not expired).

    Args:
        session: A SQLAlchemy session.
        share_uuid: The 36-char UUID.

    Returns:
        The :class:`NotebookShare` row or ``None``.
    """
    row = session.execute(
        select(NotebookShare).where(NotebookShare.share_uuid == share_uuid)
    ).scalar_one_or_none()
    if row is None:
        return None
    if row.revoked_at is not None:
        return None
    if row.expires_at is not None and row.expires_at <= datetime.datetime.now(
        datetime.UTC
    ):
        return None
    return row


def list_shares_for_notebook(
    session: Session, *, notebook_id: str
) -> list[dict[str, Any]]:
    """Return every share row (active + revoked) for a notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        List of ``{share_uuid, share_mode, dashboard_mode,
        revision_uuid, created_at, expires_at, revoked_at, active}``.
    """
    rows = session.execute(
        select(NotebookShare)
        .where(NotebookShare.notebook_id == notebook_id)
        .order_by(NotebookShare.created_at.desc())
    ).scalars().all()
    now = datetime.datetime.now(datetime.UTC)
    out: list[dict[str, Any]] = []
    for r in rows:
        active = r.revoked_at is None and (
            r.expires_at is None or r.expires_at > now
        )
        out.append(
            {
                "share_uuid": r.share_uuid,
                "share_mode": r.share_mode,
                "dashboard_mode": bool(r.dashboard_mode),
                "revision_uuid": r.revision_uuid,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                "active": active,
            }
        )
    return out


def render_dashboard_html(
    *,
    title: str,
    cells: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> str:
    """Render the dashboard variant — strips code, keeps markdown + outputs.

    Re-uses the Phase-98.D HTML pipeline but filters out non-markdown
    cells before handing off so the rendered document carries only
    the narrative + result frames.

    Args:
        title: Page title.
        cells: Cell list (Phase-96 shape).
        outputs: Persisted output rows (load shape).

    Returns:
        Self-contained HTML string with a "Dashboard" badge.
    """
    from pointlessql.services.notebook import export as export_service

    # Dashboard render: keep markdown cells as-is; replace every other
    # cell with a zero-source placeholder so its outputs still render
    # in the original order without exposing the code.
    relevant_hashes = {c.get("content_hash") for c in cells}
    filtered_outputs = [
        o for o in outputs if o.get("content_hash") in relevant_hashes
    ]
    interleaved: list[dict[str, Any]] = []
    for cell in cells:
        cell_type = cell.get("cell_type") or "code"
        if cell_type == "markdown":
            interleaved.append(cell)
        else:
            interleaved.append(
                {
                    "content_hash": cell.get("content_hash") or "",
                    "cell_type": "markdown",
                    "source": "",
                }
            )
    return export_service.render_notebook_html(
        title=f"{title} (dashboard)",
        cells=interleaved,
        outputs=filtered_outputs,
    ).replace(
        "<body>",
        '<body data-mode="dashboard">'
        '<div style="background:#dbeafe;color:#1e40af;'
        'padding:0.25rem 0.75rem;font-size:0.85rem;'
        'border-bottom:1px solid #93c5fd;margin:-2rem -3rem 1.5rem -3rem;">'
        "DASHBOARD · code cells hidden"
        "</div>",
        1,
    )


__all__ = [
    "VALID_SHARE_MODES",
    "create_share",
    "get_active_share",
    "list_shares_for_notebook",
    "render_dashboard_html",
    "revoke_share",
    "update_share",
]
