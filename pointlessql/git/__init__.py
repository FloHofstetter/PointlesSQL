"""Git provider abstraction for workspace-backed repositories.

introduces the ability to back a workspace's
configuration with a git repository: clone on admin demand, pull
on webhook trigger or cron, surface yaml-bundles + notebooks +
dashboards + saved queries from the repo's filesystem layout.
This package isolates every git-touching primitive behind a
small :class:`GitProvider` protocol so the rest of the codebase
never imports ``subprocess`` or webhook-signature code directly.

Two concrete providers ship today:

* :class:`GenericGitProvider` — vanilla git over HTTPS or SSH.
  Clone/pull use ``git`` as a subprocess; webhook signature
  verification refuses every payload (generic provider has no
  shared-secret handshake).
* :class:`GitHubProvider` — same clone/pull as generic, plus
  HMAC-SHA-256 verification of GitHub's
  ``X-Hub-Signature-256`` and parsing of the push-event JSON.

Adding GitLab / Gitea later means dropping a third file in this
package and extending :func:`resolve_provider`; nothing in the
service layer needs to change.
"""

from __future__ import annotations

from pointlessql.git._errors import (
    WorkspaceRepoAuthFailed,
    WorkspaceRepoCloneFailed,
    WorkspaceRepoError,
    WorkspaceRepoUnknownProvider,
    WorkspaceRepoWebhookInvalid,
)
from pointlessql.git._generic import GenericGitProvider
from pointlessql.git._github import GitHubProvider
from pointlessql.git._provider import (
    CheckResult,
    CloneResult,
    GitProvider,
    PullResult,
    ResolvedSecret,
    WebhookEvent,
    WebhookVerification,
)
from pointlessql.git._resolver import KNOWN_PROVIDER_KINDS, resolve_provider
from pointlessql.git._search_paths import discover_repo_yaml_files

__all__ = [
    "CheckResult",
    "CloneResult",
    "GenericGitProvider",
    "GitHubProvider",
    "GitProvider",
    "KNOWN_PROVIDER_KINDS",
    "PullResult",
    "ResolvedSecret",
    "WebhookEvent",
    "WebhookVerification",
    "WorkspaceRepoAuthFailed",
    "WorkspaceRepoCloneFailed",
    "WorkspaceRepoError",
    "WorkspaceRepoUnknownProvider",
    "WorkspaceRepoWebhookInvalid",
    "discover_repo_yaml_files",
    "resolve_provider",
]
