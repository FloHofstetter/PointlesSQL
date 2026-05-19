"""Starter notebook template gallery (Phase 98.B).

Templates ship as plain ``.py`` files inside
``pointlessql/data/notebook_templates/`` plus a ``_manifest.json``
that describes the gallery cards.  ``list_templates`` returns the
manifest verbatim; ``copy_template`` reads the chosen ``.py`` and
writes it to the workspace at a caller-supplied relative path.

The on-disk format is the same marker-grammar ``.py`` the editor
loads everywhere else, so a freshly-created notebook opens with no
special handling at the editor.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import _workspace as notebook_workspace_service

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "notebook_templates"
_MANIFEST_PATH = _TEMPLATE_DIR / "_manifest.json"


def _load_manifest() -> list[dict[str, Any]]:
    """Read and parse ``_manifest.json``.

    Returns:
        The parsed manifest list — see ``_manifest.json`` for the
        per-row shape (``id``, ``title``, ``description``,
        ``category``, ``filename``).

    Raises:
        ValidationError: When the manifest is missing or unparseable.
            Surfaces as a 422 so a misconfigured deploy is obvious.
    """
    if not _MANIFEST_PATH.exists():
        raise ValidationError("notebook template manifest missing")
    try:
        data: Any = json.loads(_MANIFEST_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ValidationError(
            f"notebook template manifest parse error: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise ValidationError("notebook template manifest must be a JSON array")
    out: list[dict[str, Any]] = []
    for entry in data:  # type: ignore[reportUnknownVariableType]
        if isinstance(entry, dict):
            out.append({str(k): v for k, v in entry.items()})  # type: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    return out


def list_templates() -> list[dict[str, Any]]:
    """Return the gallery card list.

    Returns:
        A list of dicts with ``id`` / ``title`` / ``description`` /
        ``category`` / ``filename`` keys — already filtered to those
        whose ``filename`` exists on disk so a stale manifest does
        not surface a broken card.
    """
    out: list[dict[str, Any]] = []
    for entry in _load_manifest():
        filename = entry.get("filename")
        if not isinstance(filename, str):
            continue
        if not (_TEMPLATE_DIR / filename).exists():
            continue
        out.append(
            {
                "id": entry.get("id", filename.rsplit(".", 1)[0]),
                "title": entry.get("title", filename),
                "description": entry.get("description", ""),
                "category": entry.get("category", "starter"),
                "filename": filename,
            }
        )
    return out


def _resolve_template(template_id: str) -> Path:
    """Look up the template file by ``id``.

    Args:
        template_id: ``id`` field from one manifest entry.

    Returns:
        Absolute path to the template ``.py`` on disk.

    Raises:
        ValidationError: When no manifest entry matches ``template_id``
            or its filename does not exist.
    """
    for entry in list_templates():
        if entry["id"] == template_id:
            return _TEMPLATE_DIR / entry["filename"]
    raise ValidationError(f"unknown notebook template: {template_id!r}")


def create_from_template(
    *,
    notebooks_dir: Path,
    template_id: str,
    dest_path: str,
) -> Path:
    """Copy the chosen template into the workspace at ``dest_path``.

    Args:
        notebooks_dir: Resolved workspace root from settings.
        template_id: ``id`` from :func:`list_templates`.
        dest_path: Relative path under ``notebooks_dir``; must end
            in ``.py`` and not already exist.

    Returns:
        Absolute path of the newly created notebook.

    Raises:
        ValidationError: From the workspace resolver guards or when
            ``template_id`` is unknown.
    """
    template_path = _resolve_template(template_id)
    body = template_path.read_text()
    resolved = notebook_workspace_service.create_empty_notebook(
        notebooks_dir, dest_path
    )
    resolved.write_text(body)
    return resolved


__all__ = ["create_from_template", "list_templates"]
