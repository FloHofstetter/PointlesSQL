"""GitProvider implementations.

Generic provider clone+pull is exercised against a real ``git``
binary using a tmp bare repository (no network calls); GitHub
provider's HMAC verification + push-event parsing are pure
in-memory tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pointlessql.git import (
    KNOWN_PROVIDER_KINDS,
    GenericGitProvider,
    GitHubProvider,
    WebhookEvent,
    WorkspaceRepoCloneFailed,
    WorkspaceRepoUnknownProvider,
    resolve_provider,
)


def _git_available() -> bool:
    return shutil.which("git") is not None


pytestmark = pytest.mark.skipif(not _git_available(), reason="git binary not available")


def _git(*args: str, cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd is not None else None,
        check=True,
        capture_output=True,
        env={
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
            "LANG": "C",
            "HOME": str(Path.home()),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )


def _make_bare_repo(tmp_path: Path) -> Path:
    """Build a tmp bare repo seeded with one initial commit on ``main``."""
    seed = tmp_path / "seed"
    seed.mkdir()
    _git("init", "--initial-branch=main", cwd=seed)
    _git("config", "user.email", "test@example.com", cwd=seed)
    _git("config", "user.name", "Test", cwd=seed)
    (seed / "README.md").write_text("hello\n")
    _git("add", "README.md", cwd=seed)
    _git("commit", "-m", "initial", cwd=seed)

    bare = tmp_path / "bare.git"
    _git("clone", "--bare", str(seed), str(bare))
    return bare


def _commit_more(seed: Path) -> None:
    (seed / "second.txt").write_text("two\n")
    _git("add", "second.txt", cwd=seed)
    _git("commit", "-m", "second", cwd=seed)


def test_generic_clone_then_pull_against_local_bare(tmp_path):  # type: ignore[no-untyped-def]
    bare = _make_bare_repo(tmp_path)
    provider = GenericGitProvider()

    target = tmp_path / "clone"
    clone_result = asyncio.run(provider.clone(f"file://{bare}", target, branch="main", secret=None))
    assert clone_result.target == target
    assert (target / "README.md").exists()
    assert len(clone_result.head_sha) == 40

    # Push another commit through the seed/bare upstream.
    seed_clone = tmp_path / "seed-clone"
    _git("clone", str(bare), str(seed_clone))
    _git("config", "user.email", "test@example.com", cwd=seed_clone)
    _git("config", "user.name", "Test", cwd=seed_clone)
    _commit_more(seed_clone)
    _git("push", "origin", "main", cwd=seed_clone)

    pull_result = asyncio.run(provider.pull(target, branch="main", secret=None))
    assert pull_result.changed is True
    assert pull_result.head_sha != clone_result.head_sha
    assert (target / "second.txt").exists()


def test_generic_pull_no_op_when_upstream_unchanged(tmp_path):  # type: ignore[no-untyped-def]
    bare = _make_bare_repo(tmp_path)
    provider = GenericGitProvider()
    target = tmp_path / "clone"
    asyncio.run(provider.clone(f"file://{bare}", target, branch="main", secret=None))
    pull_result = asyncio.run(provider.pull(target, branch="main", secret=None))
    assert pull_result.changed is False


def test_generic_clone_fails_on_missing_upstream(tmp_path):  # type: ignore[no-untyped-def]
    provider = GenericGitProvider()
    target = tmp_path / "clone"
    bogus = tmp_path / "does-not-exist"
    with pytest.raises(WorkspaceRepoCloneFailed):
        asyncio.run(provider.clone(f"file://{bogus}", target, branch="main", secret=None))
    assert not target.exists()


def test_generic_clone_refuses_existing_target(tmp_path):  # type: ignore[no-untyped-def]
    bare = _make_bare_repo(tmp_path)
    provider = GenericGitProvider()
    target = tmp_path / "clone"
    target.mkdir()
    with pytest.raises(WorkspaceRepoCloneFailed):
        asyncio.run(provider.clone(f"file://{bare}", target, branch="main", secret=None))


def test_generic_check_auth_returns_diagnostic(tmp_path):  # type: ignore[no-untyped-def]
    bare = _make_bare_repo(tmp_path)
    provider = GenericGitProvider()
    result = asyncio.run(provider.check_auth(f"file://{bare}", secret=None))
    assert result.ok is True


def test_resolve_provider_known_kinds():  # type: ignore[no-untyped-def]
    assert resolve_provider("generic").kind == "generic"
    assert resolve_provider("github").kind == "github"


def test_resolve_provider_unknown_kind_raises():  # type: ignore[no-untyped-def]
    with pytest.raises(WorkspaceRepoUnknownProvider):
        resolve_provider("gitlab")


def test_known_provider_kinds_constant_is_stable():  # type: ignore[no-untyped-def]
    # Documenting the contract — adding a provider must update this tuple.
    assert KNOWN_PROVIDER_KINDS == ("generic", "github")


def test_github_webhook_signature_verifies_valid_payload():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    secret = "shhh"
    body = b'{"ref": "refs/heads/main", "after": "deadbeef"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    out = provider.verify_webhook_signature(
        body, headers={"X-Hub-Signature-256": sig}, webhook_secret=secret
    )
    assert out.verified is True


def test_github_webhook_signature_rejects_mutated_body():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    secret = "shhh"
    body = b'{"ref": "refs/heads/main", "after": "deadbeef"}'
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    mutated_body = body.replace(b"deadbeef", b"feedface")
    out = provider.verify_webhook_signature(
        mutated_body, headers={"X-Hub-Signature-256": sig}, webhook_secret=secret
    )
    assert out.verified is False
    assert "match" in out.reason


def test_github_webhook_signature_rejects_missing_header():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    out = provider.verify_webhook_signature(b"{}", headers={}, webhook_secret="shhh")
    assert out.verified is False
    assert "missing" in out.reason.lower()


def test_github_webhook_signature_rejects_missing_prefix():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    out = provider.verify_webhook_signature(
        b"{}",
        headers={"X-Hub-Signature-256": "deadbeef"},
        webhook_secret="shhh",
    )
    assert out.verified is False


def test_github_parse_push_event_extracts_ref_and_sha():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    body = json.dumps({"ref": "refs/heads/main", "after": "abc123def456" + "0" * 28}).encode()
    event = provider.parse_webhook(body, headers={"X-GitHub-Event": "push"})
    assert isinstance(event, WebhookEvent)
    assert event.kind == "push"
    assert event.ref == "refs/heads/main"
    assert event.branch == "main"
    assert event.head_sha is not None
    assert event.head_sha.startswith("abc123def456")


def test_github_parse_ping_event():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    event = provider.parse_webhook(b"{}", headers={"X-GitHub-Event": "ping"})
    assert isinstance(event, WebhookEvent)
    assert event.kind == "ping"
    assert event.ref is None
    assert event.head_sha is None


def test_github_parse_returns_none_when_event_header_missing():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    assert provider.parse_webhook(b"{}", headers={}) is None


def test_github_parse_returns_none_for_invalid_json():  # type: ignore[no-untyped-def]
    provider = GitHubProvider()
    assert provider.parse_webhook(b"<not json>", headers={"X-GitHub-Event": "push"}) is None


# Hide unused imports flagged by pyright in strict mode without affecting runtime.
_ = sys
