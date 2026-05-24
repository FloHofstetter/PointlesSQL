"""GitHub provider — shares clone/pull with generic, adds webhook auth.

The clone / pull / check_auth surface is identical to
:class:`GenericGitProvider` (we still drive ``git`` as a
subprocess); the GitHub-specific pieces are:

* ``X-Hub-Signature-256`` HMAC verification of inbound webhooks.
* ``X-GitHub-Event`` parsing into a structured
  :class:`WebhookEvent`.

Why subclass rather than compose: the only state on either class
is the ``kind`` ClassVar, so subclassing keeps the dispatch table
in :func:`pointlessql.git.resolve_provider` flat without a wrapper
indirection.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Mapping
from typing import Any, ClassVar, cast

from pointlessql.git._generic import GenericGitProvider
from pointlessql.git._provider import WebhookEvent, WebhookVerification

logger = logging.getLogger(__name__)

SIGNATURE_HEADER = "X-Hub-Signature-256"
"""Header carrying the HMAC-SHA-256 hex of the body."""

EVENT_HEADER = "X-GitHub-Event"
"""Header carrying GitHub's event type (``push``, ``ping``, ...)."""


def _lower_keys(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a lowercase-keyed copy of *headers* for case-insensitive lookup."""
    return {k.lower(): v for k, v in headers.items()}


class GitHubProvider(GenericGitProvider):
    """Clone/pull as generic; HMAC-SHA-256 webhook verification on top."""

    kind: ClassVar[str] = "github"

    def verify_webhook_signature(
        self,
        body: bytes,
        headers: Mapping[str, str],
        webhook_secret: str,
    ) -> WebhookVerification:
        """Verify ``X-Hub-Signature-256`` against ``HMAC-SHA-256(secret, body)``.

        Constant-time comparison via :func:`hmac.compare_digest`.
        Missing header, missing prefix, malformed hex, and length
        mismatch all return ``verified=False`` with a specific
        diagnostic.

        Args:
            body: Raw request body (bytes).
            headers: Case-insensitive header view.
            webhook_secret: Repo's stored webhook secret.

        Returns:
            :class:`WebhookVerification` describing the outcome.
        """
        lower = _lower_keys(headers)
        provided = lower.get(SIGNATURE_HEADER.lower())
        if not provided:
            return WebhookVerification(
                verified=False,
                reason=f"missing {SIGNATURE_HEADER} header",
            )
        if not provided.startswith("sha256="):
            return WebhookVerification(
                verified=False,
                reason=f"{SIGNATURE_HEADER} must start with 'sha256='",
            )
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        provided_hex = provided.split("=", 1)[1]
        if not hmac.compare_digest(expected, provided_hex):
            return WebhookVerification(
                verified=False,
                reason="signature did not match",
            )
        return WebhookVerification(verified=True, reason="ok")

    def parse_webhook(
        self,
        body: bytes,
        headers: Mapping[str, str],
    ) -> WebhookEvent | None:
        """Parse a GitHub webhook payload into a :class:`WebhookEvent`.

        Recognised events: ``push`` (extracts ref + head sha) and
        ``ping`` (returns a :class:`WebhookEvent` with no ref/sha).
        Any other event returns a :class:`WebhookEvent` with the
        kind preserved but ref/sha left ``None``.

        Returns ``None`` only when the payload itself is opaque
        (not JSON, no event header).

        Args:
            body: Raw request body (bytes).
            headers: Case-insensitive header view.

        Returns:
            :class:`WebhookEvent` on success; ``None`` for opaque
            payloads.
        """
        lower = _lower_keys(headers)
        event_kind = lower.get(EVENT_HEADER.lower())
        if not event_kind:
            return None
        try:
            payload_raw: Any = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError, UnicodeDecodeError:
            return None
        if not isinstance(payload_raw, dict):
            return WebhookEvent(kind=event_kind, ref=None, branch=None, head_sha=None)
        payload = cast("dict[str, Any]", payload_raw)

        ref_raw: Any = payload.get("ref")
        ref = ref_raw if isinstance(ref_raw, str) else None
        branch: str | None = None
        if ref is not None and ref.startswith("refs/heads/"):
            branch = ref[len("refs/heads/") :]

        head_sha: str | None = None
        if event_kind == "push":
            after_raw: Any = payload.get("after")
            if isinstance(after_raw, str):
                head_sha = after_raw

        return WebhookEvent(kind=event_kind, ref=ref, branch=branch, head_sha=head_sha)
