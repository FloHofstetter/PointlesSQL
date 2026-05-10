"""Parse + UPSERT dashboards and saved queries from a yaml file.

Mirrors :mod:`pointlessql.data_products._loader`'s shape:
parse-then-upsert, idempotent re-runs via slug-keyed lookup,
fail-loud on validation errors.  Per-row ``source`` and
``repo_yaml_path`` columns let the admin UI render repo-loaded
rows as read-only.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml
from sqlalchemy import select

from pointlessql.exceptions import ValidationError
from pointlessql.models.catalog import Dashboard, SavedQuery

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _read_yaml(yaml_path: Path) -> dict[str, Any]:
    """Read *yaml_path* and return a dict; fail loud on syntax errors."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"yaml not found at {yaml_path!s}")
    with yaml_path.open("r", encoding="utf-8") as fh:
        try:
            raw: Any = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ValidationError(f"yaml syntax error in {yaml_path!s}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValidationError(
            f"yaml top level must be a mapping, got {type(raw).__name__}"
        )
    return cast("dict[str, Any]", raw)


def _now() -> datetime.datetime:
    """Return ``utcnow()`` (timezone-aware)."""
    return datetime.datetime.now(datetime.UTC)


def _source_label(yaml_path: Path) -> str:
    """Build a ``source`` discriminator from the yaml path.

    Format: ``repo:<grandparent-name>`` so the resolved label
    encodes the workspace's repo slug when the yaml lives at
    ``<base_dir>/<workspace_id>/<slug>/.../pointlessql.yaml``.
    Outside the canonical layout the parent directory is used as
    a best-effort hint; the row is still distinguishable from
    UI-created ones.
    """
    parts = yaml_path.resolve().parts
    if len(parts) >= 3:
        candidate = parts[-3]
        # The canonical layout uses ``<base_dir>/<ws_id>/<slug>``
        # — heuristic: if the parent of the yaml's directory is a
        # numeric workspace_id, the directory itself is the slug.
        if len(parts) >= 4 and parts[-3].isdigit():
            candidate = parts[-2]
        return f"repo:{candidate}"
    return "repo:unknown"


def _validate_dashboard_entry(entry: dict[str, Any], yaml_path: Path) -> dict[str, Any]:
    """Coerce one ``dashboards:`` entry into a typed dict.

    Args:
        entry: Raw mapping from the yaml.
        yaml_path: The originating file (used in error messages).

    Returns:
        Validated dict ready for UPSERT.

    Raises:
        ValidationError: Required field missing or type-mismatched.
    """
    slug = entry.get("slug")
    title = entry.get("title")
    notebook_path = entry.get("notebook_path")
    description = entry.get("description")
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError(f"dashboard entry in {yaml_path!s} requires a non-empty 'slug'")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError(
            f"dashboard {slug!r} in {yaml_path!s} requires a non-empty 'title'"
        )
    if not isinstance(notebook_path, str) or not notebook_path.strip():
        raise ValidationError(
            f"dashboard {slug!r} in {yaml_path!s} requires a 'notebook_path'"
        )
    if description is not None and not isinstance(description, str):
        raise ValidationError(
            f"dashboard {slug!r} in {yaml_path!s} 'description' must be a string"
        )
    return {
        "slug": slug.strip(),
        "title": title.strip(),
        "notebook_path": notebook_path.strip(),
        "description": description,
    }


def _validate_saved_query_entry(entry: dict[str, Any], yaml_path: Path) -> dict[str, Any]:
    """Coerce one ``saved_queries:`` entry into a typed dict."""
    slug = entry.get("slug")
    title = entry.get("title")
    sql_text = entry.get("sql_text")
    description = entry.get("description")
    is_shared = entry.get("is_shared", False)
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError(
            f"saved query entry in {yaml_path!s} requires a non-empty 'slug'"
        )
    if not isinstance(title, str) or not title.strip():
        raise ValidationError(
            f"saved query {slug!r} in {yaml_path!s} requires a non-empty 'title'"
        )
    if not isinstance(sql_text, str) or not sql_text.strip():
        raise ValidationError(
            f"saved query {slug!r} in {yaml_path!s} requires 'sql_text'"
        )
    if description is not None and not isinstance(description, str):
        raise ValidationError(
            f"saved query {slug!r} in {yaml_path!s} 'description' must be a string"
        )
    if not isinstance(is_shared, bool):
        raise ValidationError(
            f"saved query {slug!r} in {yaml_path!s} 'is_shared' must be a bool"
        )
    return {
        "slug": slug.strip(),
        "title": title.strip(),
        "sql_text": sql_text,
        "description": description,
        "is_shared": is_shared,
    }


def load_dashboards_from_yaml(
    yaml_path: Path,
    *,
    factory: sessionmaker[Session],
    workspace_id: int,
    owner_user_id: int,
) -> int:
    """Parse ``dashboards:`` from *yaml_path* and UPSERT cache rows.

    Args:
        yaml_path: The yaml file to read.
        factory: SQLAlchemy session factory.
        workspace_id: Workspace owning the rows.
        owner_user_id: ``users.id`` to record as the row owner.
            Loader callers usually pass the admin/system user id;
            the row's ``source`` discriminator carries the
            git-canonical attribution separately.

    Returns:
        Count of rows inserted or updated.

    Raises:
        ValidationError: yaml block shape or per-entry fields
            invalid (missing slug/title, wrong types, ...).
    """
    raw = _read_yaml(yaml_path)
    raw_entries: Any = raw.get("dashboards") or []
    if not isinstance(raw_entries, list):
        raise ValidationError(
            f"'dashboards:' in {yaml_path!s} must be a list, "
            f"got {type(raw_entries).__name__}"
        )
    entries_typed = cast("list[Any]", raw_entries)
    source = _source_label(yaml_path)
    timestamp = _now()
    yaml_str = str(yaml_path.resolve())
    written = 0

    with factory() as session:
        for raw_entry in entries_typed:
            if not isinstance(raw_entry, dict):
                raise ValidationError(
                    f"dashboard entry in {yaml_path!s} must be a mapping"
                )
            data = _validate_dashboard_entry(cast("dict[str, Any]", raw_entry), yaml_path)
            existing = session.execute(
                select(Dashboard).where(Dashboard.slug == data["slug"])
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Dashboard(
                        workspace_id=workspace_id,
                        slug=data["slug"],
                        title=data["title"],
                        description=data["description"],
                        notebook_path=data["notebook_path"],
                        owner_id=owner_user_id,
                        created_at=timestamp,
                        updated_at=timestamp,
                        source=source,
                        repo_yaml_path=yaml_str,
                    )
                )
            else:
                existing.title = data["title"]
                existing.description = data["description"]
                existing.notebook_path = data["notebook_path"]
                existing.updated_at = timestamp
                existing.source = source
                existing.repo_yaml_path = yaml_str
            written += 1
        session.commit()
    return written


def load_saved_queries_from_yaml(
    yaml_path: Path,
    *,
    factory: sessionmaker[Session],
    workspace_id: int,
    owner_user_id: int,
) -> int:
    """Parse ``saved_queries:`` from *yaml_path* and UPSERT cache rows.

    Args:
        yaml_path: The yaml file to read.
        factory: SQLAlchemy session factory.
        workspace_id: Workspace owning the rows.
        owner_user_id: ``users.id`` to record as the row owner.

    Returns:
        Count of rows inserted or updated.

    Raises:
        ValidationError: yaml block shape or per-entry fields
            invalid (missing slug/title/sql_text, wrong types,
            ...).
    """
    raw = _read_yaml(yaml_path)
    raw_entries: Any = raw.get("saved_queries") or []
    if not isinstance(raw_entries, list):
        raise ValidationError(
            f"'saved_queries:' in {yaml_path!s} must be a list, "
            f"got {type(raw_entries).__name__}"
        )
    entries_typed = cast("list[Any]", raw_entries)
    source = _source_label(yaml_path)
    timestamp = _now()
    yaml_str = str(yaml_path.resolve())
    written = 0

    with factory() as session:
        for raw_entry in entries_typed:
            if not isinstance(raw_entry, dict):
                raise ValidationError(
                    f"saved_query entry in {yaml_path!s} must be a mapping"
                )
            data = _validate_saved_query_entry(cast("dict[str, Any]", raw_entry), yaml_path)
            existing = session.execute(
                select(SavedQuery).where(SavedQuery.slug == data["slug"])
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    SavedQuery(
                        workspace_id=workspace_id,
                        slug=data["slug"],
                        title=data["title"],
                        description=data["description"],
                        sql_text=data["sql_text"],
                        owner_id=owner_user_id,
                        is_shared=data["is_shared"],
                        created_at=timestamp,
                        updated_at=timestamp,
                        source=source,
                        repo_yaml_path=yaml_str,
                    )
                )
            else:
                existing.title = data["title"]
                existing.description = data["description"]
                existing.sql_text = data["sql_text"]
                existing.is_shared = data["is_shared"]
                existing.updated_at = timestamp
                existing.source = source
                existing.repo_yaml_path = yaml_str
            written += 1
        session.commit()
    return written


def _discover_repo_yaml(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
) -> list[Path]:
    """Reuse the existing helper for repo yaml discovery."""
    from pointlessql.config import Settings
    from pointlessql.git import discover_repo_yaml_files

    settings = Settings()
    return discover_repo_yaml_files(
        factory,
        workspace_id=workspace_id,
        base_dir=Path(settings.workspace_repos.base_dir),
        globs=tuple(settings.workspace_repos.yaml_search_globs),
    )


def load_dashboards_for_workspace(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_user_id: int,
) -> int:
    """Walk every repo's ``pointlessql.yaml`` and load dashboards.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace owning the rows.
        owner_user_id: User id stamped on new rows as ``owner_id``.

    Returns:
        Total rows UPSERTed across all discovered yamls.
    """
    total = 0
    for path in _discover_repo_yaml(factory, workspace_id=workspace_id):
        total += load_dashboards_from_yaml(
            path,
            factory=factory,
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
        )
    return total


def load_saved_queries_for_workspace(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_user_id: int,
) -> int:
    """Walk every repo's ``pointlessql.yaml`` and load saved queries.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace owning the rows.
        owner_user_id: User id stamped on new rows as ``owner_id``.

    Returns:
        Total rows UPSERTed across all discovered yamls.
    """
    total = 0
    for path in _discover_repo_yaml(factory, workspace_id=workspace_id):
        total += load_saved_queries_from_yaml(
            path,
            factory=factory,
            workspace_id=workspace_id,
            owner_user_id=owner_user_id,
        )
    return total
