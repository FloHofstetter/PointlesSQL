"""GitProvider protocol + result dataclasses.

Each :class:`GitProvider` implementation owns one wire format /
authentication style (vanilla git, GitHub HMAC webhooks, etc.).
The protocol is deliberately small — five operations, all returning
plain frozen dataclasses — so future GitLab / Gitea adapters drop
in without touching the service layer that consumes them.

The dataclasses use ``slots=True`` to avoid the per-instance
``__dict__`` overhead and ``frozen=True`` so caller code can stash
them in lookup tables without worrying about mutation.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol


@dataclass(frozen=True, slots=True)
class ResolvedSecret:
    """One auth credential paired with the kind that named it.

    Attributes:
        kind: Discriminator — ``deploy_key`` (PEM-encoded SSH
            private key), ``https_token`` (PAT-style bearer), or
            ``oauth_token`` (short-lived GitHub-App installation
            token).
        value: Decrypted plaintext secret.  Callers must treat as
            sensitive — never log, never echo into stderr capture.
    """

    kind: Literal["deploy_key", "https_token", "oauth_token"]
    value: str


@dataclass(frozen=True, slots=True)
class CloneResult:
    """Outcome of a successful clone.

    Attributes:
        target: Absolute path of the working tree the clone landed
            at.
        head_sha: 40-character lowercase hex of ``HEAD`` after the
            clone.
        stdout_tail: Last ~4 KiB of git stdout (for audit log
            attachment).
    """

    target: Path
    head_sha: str
    stdout_tail: str


@dataclass(frozen=True, slots=True)
class PullResult:
    """Outcome of a successful pull.

    Attributes:
        target: Absolute path of the working tree.
        head_sha: 40-character lowercase hex of ``HEAD`` after the
            pull.
        changed: Whether the head moved from the previous tip
            (``True`` after a non-trivial pull, ``False`` on a
            no-op).
        stdout_tail: Last ~4 KiB of git stdout.
    """

    target: Path
    head_sha: str
    changed: bool
    stdout_tail: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Outcome of a credential check (``git ls-remote``).

    Attributes:
        ok: ``True`` when the upstream answered without an auth
            failure.
        message: Diagnostic message; populated on both success and
            failure so admins can see what the upstream said.
    """

    ok: bool
    message: str


@dataclass(frozen=True, slots=True)
class WebhookVerification:
    """Outcome of an inbound webhook signature check.

    Attributes:
        verified: ``True`` only when the signature passes a
            constant-time HMAC comparison.
        reason: Human-readable diagnostic.  Populated on both
            success and failure.
    """

    verified: bool
    reason: str


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """Parsed inbound webhook payload.

    Attributes:
        kind: Provider-specific event name.  GitHub uses ``push``,
            ``ping``, ``installation``, etc.
        ref: Full git ref the event names — ``refs/heads/main`` for
            pushes to ``main``.  ``None`` when the event has no
            associated ref (a ``ping`` for example).
        branch: Just the short branch name parsed out of ``ref``.
            ``None`` when no ref was present.
        head_sha: New ``HEAD`` after the push.  ``None`` when the
            event is not a push.
    """

    kind: str
    ref: str | None
    branch: str | None
    head_sha: str | None


class GitProvider(Protocol):
    """Pluggable git surface — clone, pull, check_auth, webhooks.

    Implementations are stateless — every call carries the URL,
    target directory, and resolved secret.  This makes them safe to
    cache in a module-level singleton (see
    :func:`pointlessql.git.resolve_provider`) and trivial to test.

    Class attributes:
        kind: Discriminator stored on
            :class:`pointlessql.models.WorkspaceRepo.provider_kind`.
            Must match one of :data:`KNOWN_PROVIDER_KINDS`.
    """

    kind: ClassVar[str]

    async def clone(
        self,
        url: str,
        target: Path,
        *,
        branch: str,
        secret: ResolvedSecret | None,
    ) -> CloneResult:
        """Clone *url* into *target*.

        Implementations must fail loud when the target already
        exists (the service layer pre-checks this; an existing
        clone calls :meth:`pull` instead).

        Args:
            url: Full git URL.  Provider-specific.
            target: Absolute filesystem path to clone into.
            branch: Branch to track.
            secret: Auth credential, or ``None`` for public repos.

        Returns:
            :class:`CloneResult` on success.  Implementations
            raise :class:`WorkspaceRepoCloneFailed` (or
            :class:`WorkspaceRepoAuthFailed` for credential
            issues) when ``git`` exits non-zero — see the
            concrete impls in :mod:`pointlessql.git._generic`.
        """
        ...

    async def pull(
        self,
        target: Path,
        *,
        branch: str,
        secret: ResolvedSecret | None,
    ) -> PullResult:
        """Fast-forward *target* against its upstream.

        Implementations must reject targets that are not git
        working trees (``.git/`` missing) so a stale base
        directory never silently masks a broken clone.

        Args:
            target: Absolute path to the existing working tree.
            branch: Branch to update.
            secret: Auth credential, or ``None`` for public repos.

        Returns:
            :class:`PullResult` on success.  Same failure modes as
            :meth:`clone`.
        """
        ...

    async def check_auth(
        self,
        url: str,
        secret: ResolvedSecret | None,
    ) -> CheckResult:
        """Probe *url* with ``git ls-remote`` to validate creds.

        Used by the admin UI's "Test connection" button before
        committing the secret.

        Args:
            url: Full git URL.
            secret: Auth credential to probe with.

        Returns:
            :class:`CheckResult` always — never raises for
            credential failure (the caller wants the diagnostic
            text either way).
        """
        ...

    def verify_webhook_signature(
        self,
        body: bytes,
        headers: Mapping[str, str],
        webhook_secret: str,
    ) -> WebhookVerification:
        """Verify an inbound webhook payload.

        The default :class:`GenericGitProvider` rejects every
        payload (no shared-secret handshake exists for plain git).
        :class:`GitHubProvider` reads ``X-Hub-Signature-256`` and
        compares against ``HMAC-SHA-256(webhook_secret, body)``
        in constant time.

        Args:
            body: Raw request body (bytes).
            headers: Case-insensitive view of request headers.
            webhook_secret: Shared secret previously stored on the
                repo row.

        Returns:
            :class:`WebhookVerification` describing the outcome.
        """
        ...

    def parse_webhook(
        self,
        body: bytes,
        headers: Mapping[str, str],
    ) -> WebhookEvent | None:
        """Parse an inbound webhook payload into a structured event.

        Returns ``None`` for payloads the provider does not
        recognise (e.g. a ``ping`` from GitHub the receiver should
        accept but not act upon — though it returns a well-formed
        :class:`WebhookEvent` with ``kind="ping"`` rather than
        ``None``).  ``None`` is reserved for the truly opaque case.

        Args:
            body: Raw request body (bytes).
            headers: Case-insensitive view of request headers.

        Returns:
            :class:`WebhookEvent` on success; ``None`` when the
            provider cannot make sense of the payload.
        """
        ...
