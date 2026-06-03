"""Unit tests for the canvas file-IO sandbox resolver.

The pure shape check lives with the blocks; this covers the enforcing
layer — feature gates and the ``resolve()`` + ``is_relative_to`` containment
that defeats symlink / normalisation escapes a string check cannot see.
"""

from __future__ import annotations

import pytest

from pointlessql.config import get_settings
from pointlessql.exceptions import ValidationError
from pointlessql.services.dp_canvas._file_sandbox import (
    resolve_sandbox_path,
    rewrite_file_sentinels,
)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("POINTLESSQL_CANVAS_FILE_ROOT", str(root))
    monkeypatch.setenv("POINTLESSQL_CANVAS_FILE_ALLOW_OUTPUT", "true")
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def test_resolves_inside_root(sandbox) -> None:
    resolved = resolve_sandbox_path("sub/a.csv", for_write=False)
    assert resolved.startswith(str(sandbox.resolve()))
    assert resolved.endswith("sub/a.csv")


def test_symlink_escape_is_rejected(sandbox, tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.txt"
    secret.write_text("TOPSECRET")
    link = sandbox / "link.txt"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not supported on this platform")
    with pytest.raises(ValidationError, match="escapes"):
        resolve_sandbox_path("link.txt", for_write=False)


def test_disabled_when_root_unset(monkeypatch) -> None:
    monkeypatch.delenv("POINTLESSQL_CANVAS_FILE_ROOT", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValidationError, match="disabled"):
            resolve_sandbox_path("a.csv", for_write=False)
    finally:
        get_settings.cache_clear()


def test_write_denied_unless_allow_output(tmp_path, monkeypatch) -> None:
    root = tmp_path / "root2"
    root.mkdir()
    monkeypatch.setenv("POINTLESSQL_CANVAS_FILE_ROOT", str(root))
    monkeypatch.setenv("POINTLESSQL_CANVAS_FILE_ALLOW_OUTPUT", "false")
    get_settings.cache_clear()
    try:
        # reads are fine …
        assert resolve_sandbox_path("a.csv", for_write=False)
        # … writes are denied by default.
        with pytest.raises(ValidationError, match="output is disabled"):
            resolve_sandbox_path("a.csv", for_write=True)
    finally:
        get_settings.cache_clear()


def test_rewrite_sentinels_noop_without_tokens() -> None:
    # No sentinel → returned unchanged and settings are never consulted.
    sql = "SELECT * FROM some_cte WHERE x > 1"
    assert rewrite_file_sentinels(sql) == sql


def test_rewrite_sentinels_resolves_each(sandbox) -> None:
    sql = "SELECT * FROM read_csv_auto('@@CANVAS_FILE:bronze/a.csv@@')"
    rewritten = rewrite_file_sentinels(sql)
    assert "@@CANVAS_FILE" not in rewritten
    assert str((sandbox / "bronze" / "a.csv").resolve()) in rewritten
