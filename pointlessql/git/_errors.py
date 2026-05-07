"""Error family for the workspace-repos primitives.

Mirrors :class:`DataProductError` in spirit: hard, domain-named
exceptions raised when a clone, pull, auth attempt, or webhook
verification fails.  Subclasses derive from
:class:`WorkspaceRepoError` (which itself inherits from
:class:`PointlessSQLError`) so the centralised RFC 9457 handler
picks them up automatically.
"""

from __future__ import annotations

from typing import Any

from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import PointlessSQLError


class WorkspaceRepoError(PointlessSQLError):
    """Base class for every workspace-repo failure.

    Defaults to 500 ``workspace_repo_error`` for the unclassified
    case.  Concrete subclasses override to a specific status code
    and machine-readable code so callers and dashboards can filter
    on the failure mode.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.WORKSPACE_REPO_ERROR


class WorkspaceRepoCloneFailed(WorkspaceRepoError):
    """Raised when ``git clone`` or ``git pull`` exits non-zero.

    Carries the captured stderr so the admin UI can surface the
    upstream's diagnostic instead of forcing the operator to dig
    through container logs.

    Attributes:
        status_code: Always 502.
        error_code: Always
            ``ErrorCode.WORKSPACE_REPO_CLONE_FAILED``.

    Args:
        url: Sanitised clone URL (no embedded credentials).
        returncode: ``git`` exit code.
        stderr: Captured stderr (truncated by the subprocess
            helper).
    """

    status_code: int = 502
    error_code: ErrorCode = ErrorCode.WORKSPACE_REPO_CLONE_FAILED

    def __init__(self, url: str, returncode: int, stderr: str) -> None:
        self.url = url
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"git operation against {url} failed with exit code "
            f"{returncode}: {stderr.strip()[:500]}"
        )

    def extension_members(self) -> dict[str, Any] | None:
        """Surface url + returncode + stderr triple as RFC 9457 extras."""
        return {
            "url": self.url,
            "returncode": self.returncode,
            "stderr": self.stderr,
        }


class WorkspaceRepoAuthFailed(WorkspaceRepoError):
    """Raised when the resolved secret was rejected by the upstream.

    Usually surfaces as a 128 / 401-equivalent exit code from git
    plus a recognisable stderr ("Permission denied (publickey)",
    "Authentication failed for ...").  The clone helper distinguishes
    this from a generic clone failure to give admins a clearer hint
    that the credential needs updating.
    """

    status_code: int = 401
    error_code: ErrorCode = ErrorCode.WORKSPACE_REPO_AUTH_FAILED


class WorkspaceRepoUnknownProvider(WorkspaceRepoError):
    """Raised when ``provider_kind`` does not match any registered impl.

    Surfaced at create-time and at sync-time.  Surface-area lives in
    :func:`pointlessql.git.resolve_provider` — every other call site
    receives an already-resolved :class:`GitProvider` instance.
    """

    status_code: int = 400
    error_code: ErrorCode = ErrorCode.WORKSPACE_REPO_UNKNOWN_PROVIDER


class WorkspaceRepoWebhookInvalid(WorkspaceRepoError):
    """Raised by the webhook receiver when signature verification fails.

    Distinct from :class:`AuthenticationError` because the webhook
    surface is un-authenticated by the project's middleware — the
    signature *is* the auth, so a separate code makes the failure
    mode legible in dashboards and audit rows.
    """

    status_code: int = 401
    error_code: ErrorCode = ErrorCode.WORKSPACE_REPO_WEBHOOK_INVALID
