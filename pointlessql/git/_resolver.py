"""Map ``provider_kind`` discriminators to provider singletons.

The set of valid kinds lives in :data:`KNOWN_PROVIDER_KINDS` —
every place that wants to validate user input (admin route create
form, plugin tool arg-parser) imports and checks against this
tuple rather than typing the strings inline.

Adding a new provider: drop a new module next to :mod:`_generic`,
add the kind here, register the instance below.
"""

from __future__ import annotations

from pointlessql.git._errors import WorkspaceRepoUnknownProvider
from pointlessql.git._generic import GenericGitProvider
from pointlessql.git._github import GitHubProvider
from pointlessql.git._provider import GitProvider

#: Allowed values for ``WorkspaceRepo.provider_kind``.
KNOWN_PROVIDER_KINDS: tuple[str, ...] = ("generic", "github")

_GENERIC = GenericGitProvider()
_GITHUB = GitHubProvider()

_REGISTRY: dict[str, GitProvider] = {
    GenericGitProvider.kind: _GENERIC,
    GitHubProvider.kind: _GITHUB,
}


def resolve_provider(kind: str) -> GitProvider:
    """Return the provider singleton for *kind*.

    Args:
        kind: Discriminator from ``WorkspaceRepo.provider_kind``.

    Returns:
        :class:`GitProvider` instance.  Stateless — every call for
        the same *kind* returns the same singleton, safe to share
        across requests.

    Raises:
        WorkspaceRepoUnknownProvider: *kind* not in
            :data:`KNOWN_PROVIDER_KINDS`.
    """
    try:
        return _REGISTRY[kind]
    except KeyError as exc:
        raise WorkspaceRepoUnknownProvider(
            f"unknown provider_kind {kind!r}; expected one of {KNOWN_PROVIDER_KINDS}"
        ) from exc
