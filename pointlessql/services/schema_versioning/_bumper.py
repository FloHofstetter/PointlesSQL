"""Propose the next semver given current + diff."""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

from pointlessql.services.schema_versioning._diff import SchemaDiff


def propose_bump(current_semver: str, diff: SchemaDiff) -> tuple[str, str]:
    """Return ``(next_semver, change_kind)`` for the diff.

    Args:
        current_semver: Current ``MAJOR.MINOR.PATCH`` value on the port.
        diff: Classified :class:`SchemaDiff`.

    Returns:
        ``(next_semver, change_kind)`` where ``change_kind`` is one of
        ``major`` / ``minor`` / ``patch`` / ``none``.  When the diff
        is no-op the helper returns ``(current_semver, "none")``.
    """
    if diff.change_kind == "none":
        return current_semver, "none"
    try:
        version = Version(current_semver)
    except InvalidVersion:
        version = Version("0.1.0")
    major, minor, patch = _release_triple(version)
    if diff.change_kind == "major":
        major += 1
        minor = 0
        patch = 0
    elif diff.change_kind == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}", diff.change_kind


def _release_triple(version: Version) -> tuple[int, int, int]:
    """Return (major, minor, patch) from a packaging Version."""
    release = list(version.release) + [0, 0, 0]
    return int(release[0]), int(release[1]), int(release[2])
