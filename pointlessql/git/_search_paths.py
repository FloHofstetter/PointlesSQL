"""Discover yaml files inside synced workspace repositories.

Phase 51.2 — bridges the workspace-repos cache to the existing
yaml loaders without forcing each loader to know how to walk a
repo clone.  Loaders call :func:`discover_repo_yaml_files` with
their workspace and a glob pattern; the helper returns a stable-
ordered list of absolute paths (skipping repos that have never
synced).

The match is rooted at the repo's clone dir
(``<base_dir>/<workspace_id>/<slug>/``) and uses
:meth:`pathlib.Path.glob`.  Patterns are owner-defined in
``settings.workspace_repos.yaml_search_globs`` so an operator who
keeps yaml in non-standard locations can extend the discovery
without code changes.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from pointlessql.models.workspace._repos import WorkspaceRepo

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _safe_glob(root: Path, pattern: str) -> list[Path]:
    """Return ``root.glob(pattern)`` results, swallowing filesystem errors.

    A repo clone that disappeared between the DB lookup and the
    glob (admin deleted it from disk, container restarted with a
    detached volume, ...) should not poison the discovery for
    other repos.

    Args:
        root: Clone-dir to walk.
        pattern: Glob pattern (relative to *root*).

    Returns:
        Sorted list of absolute paths.  Empty when *root* is
        missing or the glob returns nothing.
    """
    if not root.exists():
        return []
    try:
        # ``Path.glob`` raises ValueError on patterns it can't compile;
        # we let those propagate (configuration error, deserves attention)
        # but guard against transient OSErrors during the walk.
        matches = sorted(root.glob(pattern))
    except OSError:
        return []
    return [match.resolve() for match in matches if match.is_file()]


def discover_repo_yaml_files(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    base_dir: Path,
    globs: Sequence[str],
) -> list[Path]:
    """Walk every successfully-synced repo and return matching yaml files.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace whose repos to scan.
        base_dir: Resolved
            ``settings.workspace_repos.base_dir``; the clone dir
            is at ``<base_dir>/<workspace_id>/<slug>/``.
        globs: Glob patterns relative to each clone dir.  Typical
            values: ``("pointlessql.yaml", "**/pointlessql.yaml")``.

    Returns:
        Stable-ordered list of absolute paths.  Sort key is
        ``(repo slug, glob pattern, glob match)`` so re-running
        the discovery against an unchanged repo always returns
        the same order — important for the loader's idempotent
        UPSERT pass.
    """
    seen: set[Path] = set()
    out: list[Path] = []
    with factory() as session:
        repos = (
            session.execute(
                select(WorkspaceRepo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .order_by(WorkspaceRepo.slug.asc())
            )
            .scalars()
            .all()
        )
        # Detach so the loop body is read-only against the row.  We
        # deliberately do not filter on ``last_synced_at IS NOT NULL``
        # — the post-pull loader hook runs *during* the sync (between
        # the pull and the persist of ``last_synced_at``), so the SQL
        # filter would skip the very repo we just synced.  The
        # ``_safe_glob`` step below already short-circuits when the
        # clone dir is missing.
        for repo in repos:
            session.expunge(repo)

    for repo in repos:
        clone_dir = (base_dir / str(repo.workspace_id) / repo.slug).resolve()
        for pattern in globs:
            for match in _safe_glob(clone_dir, pattern):
                if match in seen:
                    continue
                seen.add(match)
                out.append(match)
    return out
