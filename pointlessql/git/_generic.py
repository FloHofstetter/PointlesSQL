"""Generic git provider — vanilla SSH / HTTPS, no signed webhooks.

Used as the fallback for any repo whose provider_kind is not a
known specialised host.  Clone and pull invoke ``git`` directly;
auth is wired through either ``GIT_SSH_COMMAND`` (deploy keys) or
URL-rewriting for HTTPS bearer tokens.

Webhook signature verification deliberately rejects every payload
— there is no shared-secret handshake on plain git, so a
GenericGitProvider repo cannot accept inbound webhooks.  Operators
who need webhook auto-pull should pick a specialised provider
(``github`` today; ``gitlab``/``gitea`` later).
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar

from pointlessql.git._errors import (
    WorkspaceRepoAuthFailed,
    WorkspaceRepoCloneFailed,
)
from pointlessql.git._provider import (
    CheckResult,
    CloneResult,
    PullResult,
    ResolvedSecret,
    WebhookEvent,
    WebhookVerification,
)
from pointlessql.git._subprocess import GitRunResult, run_git

logger = logging.getLogger(__name__)


_AUTH_FAIL_HINTS = (
    "permission denied",
    "authentication failed",
    "could not read username",
    "fatal: authentication",
)
"""Lowercased substrings in stderr that indicate auth refusal.

Tested in stderr-lower; any match upgrades a generic clone failure
to :class:`WorkspaceRepoAuthFailed` so the admin UI can hint at
the credential rather than the network.
"""


def _raise_for_failure(url: str, result: GitRunResult) -> None:
    """Raise the right exception for a failed git invocation.

    Inspects ``result.stderr`` for known authentication-failure
    hints; matches upgrade a generic
    :class:`WorkspaceRepoCloneFailed` to
    :class:`WorkspaceRepoAuthFailed` so the admin UI can hint at
    the credential rather than the network.

    Args:
        url: Sanitised URL for the diagnostic message.
        result: The failing :class:`GitRunResult`.

    Raises:
        WorkspaceRepoAuthFailed: stderr matched an auth-fail hint.
        WorkspaceRepoCloneFailed: anything else.
    """
    stderr_lc = result.stderr.lower()
    for hint in _AUTH_FAIL_HINTS:
        if hint in stderr_lc:
            raise WorkspaceRepoAuthFailed(
                f"authentication refused for {url}: {result.stderr.strip()[:300]}"
            )
    raise WorkspaceRepoCloneFailed(url, result.returncode, result.stderr)


class _SshKeyFile:
    """Context manager owning a temp file with a deploy-key on disk.

    git's ``GIT_SSH_COMMAND`` mechanism wants a file path to the
    private key — there is no env-var way to pass the key bytes
    directly.  The temp file is created with mode ``0600``, lives
    only for the duration of the surrounding ``async with``, and is
    unlinked even on exception.
    """

    def __init__(self, key_pem: str) -> None:
        self.key_pem = key_pem
        self._path: Path | None = None

    def __enter__(self) -> Path:
        fd, name = tempfile.mkstemp(prefix="pointlessql-deploy-", suffix=".key")
        try:
            os.write(fd, self.key_pem.encode("utf-8"))
            if not self.key_pem.endswith("\n"):
                os.write(fd, b"\n")
        finally:
            os.close(fd)
        # Owner read/write, nothing for group/other — git's strict mode insists.
        os.chmod(name, stat.S_IRUSR | stat.S_IWUSR)
        self._path = Path(name)
        return self._path

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._path is not None:
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass


def _env_for_secret(secret: ResolvedSecret | None, key_path: Path | None) -> dict[str, str]:
    """Build the env additions needed to pass *secret* to git."""
    env: dict[str, str] = {}
    if secret is None:
        return env
    if secret.kind == "deploy_key" and key_path is not None:
        # ``-i <key>`` plus ``IdentitiesOnly=yes`` keeps ssh from trying any
        # key in the agent or default ``~/.ssh/id_*`` — important when the
        # PointlesSQL daemon's home dir might carry an unrelated identity.
        # ``StrictHostKeyChecking=accept-new`` lands new hosts in the known
        # hosts file rather than refusing them outright; admins who want
        # stricter behaviour can pre-seed ``known_hosts`` and flip this back
        # via env in a future settings field.
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {key_path} "
            f"-o IdentitiesOnly=yes "
            f"-o StrictHostKeyChecking=accept-new "
            f"-o BatchMode=yes"
        )
    return env


def _rewrite_https_url(url: str, secret: ResolvedSecret) -> str:
    """Inject *secret* into an https URL as a bearer in the userinfo slot.

    Used for ``https_token`` and ``oauth_token`` kinds.  GitHub
    accepts ``https://<token>@github.com/owner/repo.git``; GitLab
    and Gitea accept the same shape.  The userinfo segment is
    URL-safe because the token itself is base64-ish ASCII.
    """
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest:
        # Caller already embedded credentials; leave as-is and trust them.
        return url
    return f"{scheme}://x-access-token:{secret.value}@{rest}"


class GenericGitProvider:
    """Vanilla git over HTTPS or SSH.

    Stateless — every call carries its own URL, target, branch, and
    secret.  Safe to share a single instance across the whole
    process; see :func:`pointlessql.git.resolve_provider`.
    """

    kind: ClassVar[str] = "generic"

    async def clone(
        self,
        url: str,
        target: Path,
        *,
        branch: str,
        secret: ResolvedSecret | None,
    ) -> CloneResult:
        """Clone *url* into *target* on *branch*.

        Args:
            url: Full git URL.
            target: Absolute clone destination.  Parent directory
                must exist; the clone itself creates *target*.
            branch: Branch to track.
            secret: Optional auth credential.

        Returns:
            :class:`CloneResult` on success.  Failures escape via
            :class:`WorkspaceRepoCloneFailed` (or its sibling
            :class:`WorkspaceRepoAuthFailed`, raised by
            :func:`_raise_for_failure` when stderr looks like an
            auth refusal).

        Raises:
            WorkspaceRepoCloneFailed: ``git`` exited non-zero, the
                target already existed, or a half-clone left
                behind a partial tree.
        """
        if target.exists():
            raise WorkspaceRepoCloneFailed(
                url, -1, f"clone target already exists: {target!s}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)

        clone_url = url
        env_secret_path: Path | None = None
        ssh_ctx: _SshKeyFile | None = None
        if secret is not None and secret.kind == "deploy_key":
            ssh_ctx = _SshKeyFile(secret.value)
            env_secret_path = ssh_ctx.__enter__()
        if secret is not None and secret.kind in ("https_token", "oauth_token"):
            clone_url = _rewrite_https_url(url, secret)

        try:
            result = await run_git(
                [
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    branch,
                    clone_url,
                    str(target),
                ],
                env=_env_for_secret(secret, env_secret_path),
                timeout_seconds=300.0,
            )
        finally:
            if ssh_ctx is not None:
                ssh_ctx.__exit__(None, None, None)

        if result.returncode != 0 or result.timed_out:
            # Best-effort cleanup so a half-clone doesn't block the next try.
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            _raise_for_failure(url, result)

        head_sha = await self._head_sha(target)
        return CloneResult(target=target, head_sha=head_sha, stdout_tail=result.stdout)

    async def pull(
        self,
        target: Path,
        *,
        branch: str,
        secret: ResolvedSecret | None,
    ) -> PullResult:
        """Fast-forward *target* against its tracked upstream.

        Implementation: ``git fetch origin <branch>`` followed by
        ``git reset --hard origin/<branch>``.  We deliberately use
        a hard reset rather than ``git pull --ff-only`` because the
        working tree is read-only from PointlesSQL's perspective —
        any local change is by definition unwanted state to discard.

        Args:
            target: Existing working tree.
            branch: Branch to update.
            secret: Optional auth credential.

        Returns:
            :class:`PullResult` on success.  Failures escape via
            :class:`WorkspaceRepoCloneFailed` (or its sibling
            :class:`WorkspaceRepoAuthFailed`, raised by
            :func:`_raise_for_failure` when stderr looks like an
            auth refusal).

        Raises:
            WorkspaceRepoCloneFailed: ``git`` exited non-zero, or
                *target* is missing the ``.git`` directory and is
                therefore not a working tree.
        """
        if not (target / ".git").exists():
            raise WorkspaceRepoCloneFailed(
                str(target), -1, f"not a git working tree: {target!s}"
            )

        env_secret_path: Path | None = None
        ssh_ctx: _SshKeyFile | None = None
        if secret is not None and secret.kind == "deploy_key":
            ssh_ctx = _SshKeyFile(secret.value)
            env_secret_path = ssh_ctx.__enter__()

        prev_sha = await self._head_sha(target)
        try:
            fetch_result = await run_git(
                ["fetch", "--depth", "1", "origin", branch],
                cwd=target,
                env=_env_for_secret(secret, env_secret_path),
                timeout_seconds=120.0,
            )
            if fetch_result.returncode != 0 or fetch_result.timed_out:
                _raise_for_failure(str(target), fetch_result)
            reset_result = await run_git(
                ["reset", "--hard", f"origin/{branch}"],
                cwd=target,
                timeout_seconds=60.0,
            )
            if reset_result.returncode != 0:
                raise WorkspaceRepoCloneFailed(
                    str(target), reset_result.returncode, reset_result.stderr
                )
        finally:
            if ssh_ctx is not None:
                ssh_ctx.__exit__(None, None, None)

        new_sha = await self._head_sha(target)
        return PullResult(
            target=target,
            head_sha=new_sha,
            changed=new_sha != prev_sha,
            stdout_tail=(fetch_result.stdout + reset_result.stdout)[-4096:],
        )

    async def check_auth(
        self,
        url: str,
        secret: ResolvedSecret | None,
    ) -> CheckResult:
        """Probe *url* with ``git ls-remote --heads``.

        Never raises — returns :class:`CheckResult` so the admin UI
        can render the diagnostic on both success and failure.
        """
        probe_url = url
        env_secret_path: Path | None = None
        ssh_ctx: _SshKeyFile | None = None
        if secret is not None and secret.kind == "deploy_key":
            ssh_ctx = _SshKeyFile(secret.value)
            env_secret_path = ssh_ctx.__enter__()
        if secret is not None and secret.kind in ("https_token", "oauth_token"):
            probe_url = _rewrite_https_url(url, secret)

        try:
            result = await run_git(
                ["ls-remote", "--heads", probe_url],
                env=_env_for_secret(secret, env_secret_path),
                timeout_seconds=30.0,
            )
        finally:
            if ssh_ctx is not None:
                ssh_ctx.__exit__(None, None, None)

        if result.returncode == 0:
            return CheckResult(ok=True, message=result.stdout.strip()[:300] or "ok")
        return CheckResult(ok=False, message=result.stderr.strip()[:300] or "git failed")

    def verify_webhook_signature(
        self,
        body: bytes,
        headers: Mapping[str, str],
        webhook_secret: str,
    ) -> WebhookVerification:
        """Return an unverified result — generic provider has no webhook handshake."""
        del body, headers, webhook_secret
        return WebhookVerification(
            verified=False,
            reason="generic provider does not verify signatures",
        )

    def parse_webhook(
        self,
        body: bytes,
        headers: Mapping[str, str],
    ) -> WebhookEvent | None:
        """Return ``None`` — generic provider does not parse webhook payloads."""
        del body, headers
        return None

    async def _head_sha(self, target: Path) -> str:
        """Read ``HEAD`` of *target* via ``git rev-parse HEAD``."""
        result = await run_git(
            ["rev-parse", "HEAD"],
            cwd=target,
            timeout_seconds=15.0,
        )
        if result.returncode != 0:
            raise WorkspaceRepoCloneFailed(
                str(target), result.returncode, result.stderr
            )
        return result.stdout.strip()
