"""Per-notebook Delta-branch binding.

A notebook can declare that its ``pql.write_table`` / ``pql.merge``
calls target a named Delta-branch instead of the canonical ``main``
state.  The kernel-side primitive reads the binding via the env
bridge (``POINTLESSQL_BRANCH``) so a single ``.py`` runs identically
against ``main`` and a branch — only the resolved storage layer
changes.

Promotion is a separate step gated by a human review.  Mark the
binding ``promoted_at`` once the reviewer approves; the actual
"merge branch into main" Delta-side operation happens in the
existing :mod:`pointlessql.services.agent_runs.memory._branch`
service.

This module is the binding-history + lifecycle helper.  One notebook
can carry many historical bindings (one per experiment); only one
without a ``superseded_at`` is the "current" binding for execution.
Promotion sets ``promoted_at``; discard sets ``discarded_at``; both
also set ``superseded_at`` so the next ``bind_branch`` call mints a
fresh current row.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookBranchBinding

_BRANCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$")


def _normalise_branch_name(raw: str) -> str:
    """Reject branch names outside ``[A-Za-z0-9][A-Za-z0-9._-]*``."""
    name = (raw or "").strip()
    if not _BRANCH_NAME_PATTERN.fullmatch(name):
        raise ValidationError(
            "branch_name must match [A-Za-z0-9][A-Za-z0-9._-]* and be 1-127 chars"
        )
    return name


def _current(
    session: Session, *, notebook_id: str
) -> NotebookBranchBinding | None:
    """Return the active (non-superseded) binding row or ``None``."""
    return session.execute(
        select(NotebookBranchBinding)
        .where(
            NotebookBranchBinding.notebook_id == notebook_id,
            NotebookBranchBinding.superseded_at.is_(None),
        )
        .order_by(NotebookBranchBinding.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def bind_branch(
    session: Session,
    *,
    notebook_id: str,
    branch_name: str,
    base_revision_uuid: str | None = None,
    created_by_user_id: int | None = None,
) -> NotebookBranchBinding:
    """Set the current branch binding for a notebook.

    Supersedes the prior active binding (if any) so only one is
    ever "current" at a time.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        branch_name: Delta-branch name.
        base_revision_uuid: Optional Phase-97 revision the branch
            forks from.
        created_by_user_id: Audit pointer.

    Returns:
        The new :class:`NotebookBranchBinding` row.

    Raises:
        ValidationError: On bad input or unknown notebook.
    """
    name = _normalise_branch_name(branch_name)
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    now = datetime.datetime.now(datetime.UTC)
    prior = _current(session, notebook_id=notebook_id)
    if prior is not None:
        prior.superseded_at = now
    row = NotebookBranchBinding(
        notebook_id=notebook_id,
        branch_name=name,
        base_revision_uuid=base_revision_uuid,
        created_by_user_id=created_by_user_id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_current_binding(
    session: Session, *, notebook_id: str
) -> dict[str, Any] | None:
    """Return the active binding envelope for a notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        Dict ``{branch_name, base_revision_uuid, created_at, …}`` or
        ``None`` when the notebook runs against ``main``.
    """
    row = _current(session, notebook_id=notebook_id)
    return binding_to_envelope(row) if row is not None else None


def _consult_promote_webhook(
    *,
    notebook_id: str,
    binding_branch: str,
    base_revision_uuid: str | None,
    promoted_by_user_id: int | None,
    promoted_by_user_email: str | None,
) -> None:
    """POST the promote-intent to an external reviewer webhook.

    when the
    ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL`` env var is set, every
    :func:`promote_binding` call first POSTs the binding payload to
    that URL.  HTTP 200 = approved (promote proceeds); 4xx = denied
    (promote blocked with ``ValidationError`` carrying the response
    body so the UI can surface the reviewer's reason).  Any network
    failure is treated as ``denied`` so the gate stays closed by
    default.

    When ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET`` is also set
    the request carries a ``X-PointlesSQL-Signature`` header of the
    form ``sha256=<hex>`` over the raw JSON body — the same shape
    GitHub + Stripe webhooks use, so any standard verifier (and
    shoreguard's intake) can be pointed at this without bespoke
    code.  Without a secret the header is omitted and the receiver
    must accept unsigned requests on its own risk.

    The webhook URL itself is otherwise unauthenticated; the
    receiving system (shoreguard or any other reviewer) is
    responsible for whatever transport-level checks it needs beyond
    the HMAC signature.

    Args:
        notebook_id: Notebook UUID being promoted.
        binding_branch: Branch name about to be promoted.
        base_revision_uuid: Optional Phase-97 revision the branch
            forks from — forwarded so the reviewer can resolve the
            exact diff under review without a follow-up RPC.
        promoted_by_user_id: Acting user id (forwarded for audit).
        promoted_by_user_email: Acting user's email — populated by
            the API route so the receiver can surface the reviewer
            request to the right human without joining back to
            PointlesSQL.

    Raises:
        ValidationError: On non-2xx response or network failure.
    """
    import hashlib
    import hmac
    import json
    import os

    url = os.environ.get("POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL", "").strip()
    if not url:
        return  # No webhook configured → legacy behaviour, no gate.
    payload: dict[str, Any] = {
        "notebook_id": notebook_id,
        "branch_name": binding_branch,
        "base_revision_uuid": base_revision_uuid,
        "promoted_by_user_id": promoted_by_user_id,
        "promoted_by_user_email": promoted_by_user_email,
        "promote_intent_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    headers = {"content-type": "application/json"}
    secret = os.environ.get(
        "POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET", ""
    ).strip()
    if secret:
        signature = hmac.new(
            secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        headers["x-pointlessql-signature"] = f"sha256={signature}"
    try:
        import httpx

        resp = httpx.post(url, content=raw, headers=headers, timeout=10.0)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(
            f"branch-promote webhook unreachable ({url}): {exc}"
        ) from exc
    if 200 <= resp.status_code < 300:
        return
    raise ValidationError(
        f"branch-promote denied by reviewer "
        f"(HTTP {resp.status_code}): {resp.text[:200]}"
    )


def promote_binding(
    session: Session,
    *,
    notebook_id: str,
    promoted_by_user_id: int | None = None,
    promoted_by_user_email: str | None = None,
) -> NotebookBranchBinding:
    """Mark the current binding as promoted.

    The actual Delta-side merge into ``main`` happens in
    :mod:`pointlessql.services.agent_runs.memory._branch`; this
    method only records the lifecycle transition on the binding.

    When ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL`` is set, the
    intent is POSTed to the configured reviewer first
    (:func:`_consult_promote_webhook`) — a non-2xx response blocks
    the promote with a :class:`ValidationError` carrying the
    reviewer's reason.  This is the Phase 102 Wave-D scaffolding
    that lets shoreguard (or any external reviewer system) gate the
    transition without coupling promote_binding to a specific
    backend.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        promoted_by_user_id: Audit pointer to the reviewer.
        promoted_by_user_email: Optional email forwarded to the
            reviewer webhook so the receiver can address the
            requester without joining back to PointlesSQL.

    Returns:
        The updated row.

    Raises:
        ValidationError: When no current binding exists, or when the
            reviewer webhook denies the promote.
    """
    row = _current(session, notebook_id=notebook_id)
    if row is None:
        raise ValidationError(
            f"notebook {notebook_id!r} has no active branch binding to promote"
        )
    _consult_promote_webhook(
        notebook_id=notebook_id,
        binding_branch=row.branch_name,
        base_revision_uuid=row.base_revision_uuid,
        promoted_by_user_id=promoted_by_user_id,
        promoted_by_user_email=promoted_by_user_email,
    )
    now = datetime.datetime.now(datetime.UTC)
    row.promoted_at = now
    row.promoted_by_user_id = promoted_by_user_id
    row.superseded_at = now
    session.flush()
    return row


def discard_binding(
    session: Session, *, notebook_id: str
) -> NotebookBranchBinding | None:
    """Roll back the current binding without promoting.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        The discarded row or ``None`` when none existed.
    """
    row = _current(session, notebook_id=notebook_id)
    if row is None:
        return None
    now = datetime.datetime.now(datetime.UTC)
    row.discarded_at = now
    row.superseded_at = now
    session.flush()
    return row


def list_bindings(
    session: Session,
    *,
    notebook_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return historical bindings for a notebook, newest first.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        limit: Newest-N cap.
        offset: Zero-indexed row offset for paginated reads.
            Defaults to 0 (no skip).

    Returns:
        List of binding dicts ordered ``created_at desc``.
    """
    rows = session.execute(
        select(NotebookBranchBinding)
        .where(NotebookBranchBinding.notebook_id == notebook_id)
        .order_by(NotebookBranchBinding.created_at.desc())
        .offset(max(0, int(offset)))
        .limit(limit)
    ).scalars().all()
    return [binding_to_envelope(r) for r in rows]


def binding_to_envelope(row: NotebookBranchBinding) -> dict[str, Any]:
    """Serialise a row for REST output."""
    return {
        "id": row.id,
        "notebook_id": row.notebook_id,
        "branch_name": row.branch_name,
        "base_revision_uuid": row.base_revision_uuid,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
        "promoted_by_user_id": row.promoted_by_user_id,
        "discarded_at": row.discarded_at.isoformat()
        if row.discarded_at
        else None,
        "superseded_at": row.superseded_at.isoformat()
        if row.superseded_at
        else None,
        "is_current": row.superseded_at is None,
    }


__all__ = [
    "bind_branch",
    "discard_binding",
    "get_current_binding",
    "list_bindings",
    "promote_binding",
]
