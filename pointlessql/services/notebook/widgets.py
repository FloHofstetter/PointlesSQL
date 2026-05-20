"""Notebook parameter widgets (Phase 99).

Widgets are interactive controls rendered as a form above the
notebook — dropdowns / sliders / text inputs.  The kernel-side
``pql.widgets`` shim resolves the current value from the env bridge
the WS handler exports, so the same notebook ``.py`` runs both
interactively (form-driven) and headlessly (CLI-driven via the same
env vars).

This module is the CRUD + value-bag helper layer the REST routes
call.  Widget definitions are SQL-side; current values are session-
scoped (held by the WS handler) and not persisted — the user can
override the default at run time without polluting the DB.

The widget vocabulary is intentionally small:

* ``dropdown`` — ``config.options`` is a list of ``{value, label}``
  dicts; default_value picks one.
* ``slider`` — ``config.min`` / ``config.max`` / ``config.step``;
  default_value is the start.
* ``text`` — ``config.placeholder`` for the input affordance;
  default_value seeds the box.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookWidget

VALID_WIDGET_KINDS: frozenset[str] = frozenset({"dropdown", "slider", "text"})

_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")


def _normalise_name(raw: str) -> str:
    """Validate the kernel-visible widget identifier.

    Args:
        raw: Tentative widget name from the request body.

    Returns:
        The trimmed name when valid.

    Raises:
        ValidationError: When the name is empty or contains a
            character outside ``[A-Za-z_][A-Za-z0-9_]*``.
    """
    name = (raw or "").strip()
    if not _NAME_PATTERN.fullmatch(name):
        raise ValidationError(
            "widget name must match [A-Za-z_][A-Za-z0-9_]* and be 1-64 chars"
        )
    return name


def _validate_config(kind: str, config: dict[str, Any]) -> None:
    """Reject configs that do not match the widget kind.

    Args:
        kind: One of :data:`VALID_WIDGET_KINDS`.
        config: Parsed config payload.

    Raises:
        ValidationError: When the shape does not match the kind.
    """
    if kind == "dropdown":
        options = config.get("options")
        if not isinstance(options, list) or not options:
            raise ValidationError("dropdown.config.options must be a non-empty list")
    elif kind == "slider":
        for key in ("min", "max"):
            if not isinstance(config.get(key), (int, float)):
                raise ValidationError(f"slider.config.{key} must be numeric")
        if config["min"] >= config["max"]:
            raise ValidationError("slider.config.min must be less than max")
    elif kind == "text":
        pass  # placeholder is optional


def upsert_widget(
    session: Session,
    *,
    notebook_id: str,
    name: str,
    widget_kind: str,
    label: str,
    config: dict[str, Any],
    default_value: Any = None,
    position: int = 0,
) -> NotebookWidget:
    """Insert or replace one widget definition.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        name: Identifier the kernel sees.  Validated.
        widget_kind: One of :data:`VALID_WIDGET_KINDS`.
        label: Human-friendly label.
        config: Widget-kind-specific config (``options`` /
            ``min`` / ``max`` / ``placeholder`` / etc.).
        default_value: Default value; JSON-encoded for storage.
        position: Display order; smaller is earlier.

    Returns:
        The (new or updated) row.

    Raises:
        ValidationError: On bad input shape or unknown notebook.
    """
    if widget_kind not in VALID_WIDGET_KINDS:
        raise ValidationError(
            f"widget_kind must be one of {sorted(VALID_WIDGET_KINDS)}"
        )
    _validate_config(widget_kind, config)
    normalised = _normalise_name(name)
    nb = session.get(Notebook, notebook_id)
    if nb is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    now = datetime.datetime.now(datetime.UTC)
    row = session.execute(
        select(NotebookWidget).where(
            NotebookWidget.notebook_id == notebook_id,
            NotebookWidget.name == normalised,
        )
    ).scalar_one_or_none()
    config_blob = json.dumps(config, sort_keys=True)
    default_blob = (
        json.dumps(default_value, sort_keys=True)
        if default_value is not None
        else None
    )
    if row is None:
        row = NotebookWidget(
            notebook_id=notebook_id,
            name=normalised,
            widget_kind=widget_kind,
            label=label,
            config_json=config_blob,
            default_value=default_blob,
            position=position,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.widget_kind = widget_kind
        row.label = label
        row.config_json = config_blob
        row.default_value = default_blob
        row.position = position
        row.updated_at = now
    session.flush()
    return row


def list_widgets(
    session: Session, *, notebook_id: str
) -> list[dict[str, Any]]:
    """Return every widget on a notebook in display order.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        List of widget dicts ordered by ``position, id``.
    """
    rows = session.execute(
        select(NotebookWidget)
        .where(NotebookWidget.notebook_id == notebook_id)
        .order_by(NotebookWidget.position.asc(), NotebookWidget.id.asc())
    ).scalars().all()
    return [widget_to_envelope(r) for r in rows]


def widget_to_envelope(row: NotebookWidget) -> dict[str, Any]:
    """Serialise a row for REST output."""
    return {
        "id": row.id,
        "name": row.name,
        "widget_kind": row.widget_kind,
        "label": row.label,
        "config": json.loads(row.config_json),
        "default_value": (
            json.loads(row.default_value) if row.default_value is not None else None
        ),
        "position": row.position,
    }


def delete_widget(
    session: Session, *, notebook_id: str, name: str
) -> bool:
    """Delete one widget; idempotent.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        name: Widget identifier.

    Returns:
        ``True`` when a row was removed; ``False`` when no widget
        matched.
    """
    row = session.execute(
        select(NotebookWidget).where(
            NotebookWidget.notebook_id == notebook_id,
            NotebookWidget.name == name,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def resolve_widget_values(
    session: Session,
    *,
    notebook_id: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the ``name → value`` map the kernel reads.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        overrides: Per-execution overrides (e.g. the form's current
            values).  Missing keys fall back to ``default_value``.

    Returns:
        Mapping ``widget.name → resolved value``.  Missing defaults
        surface as ``None`` so the kernel can treat them as unset.
    """
    out: dict[str, Any] = {}
    widgets = list_widgets(session, notebook_id=notebook_id)
    overrides = overrides or {}
    for w in widgets:
        if w["name"] in overrides:
            out[w["name"]] = overrides[w["name"]]
        else:
            out[w["name"]] = w["default_value"]
    return out


__all__ = [
    "VALID_WIDGET_KINDS",
    "delete_widget",
    "list_widgets",
    "resolve_widget_values",
    "upsert_widget",
]
