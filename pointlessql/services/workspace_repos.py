"""CRUD + sync orchestration for git-backed workspace repositories.

This module wraps:

* :class:`pointlessql.git.GitProvider` (clone / pull / webhook
  verify).
* :func:`pointlessql.services.secrets.encrypt_value` /
  :func:`decrypt_value` (Fernet master key).
* :class:`pointlessql.models.WorkspaceRepo` /
  :class:`WorkspaceRepoSecret` (cache rows).

into a small public surface:

* :func:`create_repo` — register a new repo + optional first
  secret.  Returns the row.  Webhook secret revealed once (caller
  prints it to the admin).
* :func:`add_secret` — add or rotate a secret.  Plaintext
  encrypted before insert; the same ``(repo, kind)`` pair UPSERTs.
* :func:`rotate_webhook_secret` — generate a fresh webhook secret
  and return the plaintext exactly once.
* :func:`delete_repo` — cascade-deletes secrets, removes clone
  dir, drops the row.
* :func:`sync_repo` — clone-or-pull driver.  Stamps audit row +
  CloudEvent on every outcome.
* :func:`list_repos_for_workspace` — read-side helper for routes
  + plugin tools.
* :func:`list_repos_due_for_sync` — cron-loop helper.

The 51.2 yaml-loader integration adds a hook in :func:`sync_repo`
that re-runs :func:`load_contracts_for_workspace` etc. after every
successful pull; the loader-side import is deferred to avoid the
circular dependency at this sprint's import time.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from sqlalchemy import select

from pointlessql.git import (
    KNOWN_PROVIDER_KINDS,
    ResolvedSecret,
    WorkspaceRepoCloneFailed,
    WorkspaceRepoUnknownProvider,
    resolve_provider,
)
from pointlessql.models.workspace_repos import (
    WORKSPACE_REPO_SECRET_KINDS,
    WorkspaceRepo,
    WorkspaceRepoSecret,
)
from pointlessql.services.secrets import decrypt_value, encrypt_value

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

WEBHOOK_SECRET_BYTES = 32
"""Token length for the inbound-webhook shared secret."""


SyncTrigger = Literal["manual", "webhook", "cron"]


@dataclass(slots=True)
class CreateRepoResult:
    """What :func:`create_repo` returns.

    Attributes:
        repo: Persisted :class:`WorkspaceRepo` row.
        webhook_secret_plaintext: Generated webhook secret in
            cleartext.  Reveal once; subsequent reads return the
            stored value (which was already shown).
    """

    repo: WorkspaceRepo
    webhook_secret_plaintext: str


@dataclass(slots=True)
class SyncOutcome:
    """Structured result of one :func:`sync_repo` invocation.

    Attributes:
        repo_id: Primary key of the synced row.
        slug: Repo slug at sync time.
        ok: ``True`` when the clone or pull completed cleanly.
        head_sha: ``HEAD`` hex after the operation.  ``None`` on
            failure.
        changed: ``True`` when the head moved (or the clone was
            fresh).  ``False`` on a no-op pull.
        trigger: How the sync was initiated.
        error: Diagnostic when ``ok=False``.  ``None`` otherwise.
        operation: ``clone`` for a fresh checkout, ``pull`` for an
            update.  ``None`` on failure before either ran.
        loaded_data_products: Count of data-product yaml files the
            post-sync loader hook UPSERTed.  Always ``0`` until
            Sprint 51.2 wires the loader call.
        loaded_conventions: Same shape, conventions yaml.  ``0``
            until 51.2.
        extra: Open-ended dict of additional metadata returned by
            the post-pull hook.  Used by 51.2 + 51.3 to surface
            loader-specific counts without bloating the typed
            attributes here.
    """

    repo_id: int
    slug: str
    ok: bool
    head_sha: str | None = None
    changed: bool = False
    trigger: SyncTrigger = "manual"
    error: str | None = None
    operation: Literal["clone", "pull"] | None = None
    loaded_data_products: int = 0
    loaded_conventions: int = 0
    extra: dict[str, Any] = field(default_factory=dict[str, Any])


def _now() -> datetime.datetime:
    """Return ``utcnow()`` (timezone-aware)."""
    return datetime.datetime.now(datetime.UTC)


def _generate_webhook_secret() -> str:
    """Return a fresh URL-safe webhook secret."""
    return secrets.token_urlsafe(WEBHOOK_SECRET_BYTES)


def _resolve_clone_dir(base_dir: Path, workspace_id: int, slug: str) -> Path:
    """Compute the on-disk clone path for *(workspace, slug)*.

    Args:
        base_dir: Resolved ``settings.workspace_repos.base_dir``.
        workspace_id: Workspace owning the repo.
        slug: Repo slug.

    Returns:
        Absolute path; not created.
    """
    return (base_dir / str(workspace_id) / slug).resolve()


def create_repo(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    slug: str,
    url: str,
    default_branch: str = "main",
    provider_kind: str = "generic",
    created_by_user_id: int | None = None,
    initial_secret_kind: str | None = None,
    initial_secret_plaintext: str | None = None,
) -> CreateRepoResult:
    """Register a new workspace repo + optional first secret.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace owning the repo.
        slug: Short identifier unique within the workspace.
        url: Full clone URL.
        default_branch: Branch to track.
        provider_kind: Discriminator picked from
            :data:`pointlessql.models.WORKSPACE_REPO_PROVIDER_KINDS`.
        created_by_user_id: User registering the repo (loose link).
        initial_secret_kind: When provided, create a first secret.
            One of :data:`WORKSPACE_REPO_SECRET_KINDS`.
        initial_secret_plaintext: Plaintext for the first secret.
            Required when ``initial_secret_kind`` is set.

    Returns:
        :class:`CreateRepoResult` carrying the persisted row and
        the freshly-generated webhook secret in cleartext (reveal
        once).

    Raises:
        WorkspaceRepoUnknownProvider: ``provider_kind`` not known.
        ValueError: ``initial_secret_kind`` invalid, or one of
            ``initial_secret_kind``/``initial_secret_plaintext``
            set without the other.
    """
    if provider_kind not in KNOWN_PROVIDER_KINDS:
        raise WorkspaceRepoUnknownProvider(
            f"unknown provider_kind {provider_kind!r}; expected one of "
            f"{KNOWN_PROVIDER_KINDS}"
        )
    if (initial_secret_kind is None) != (initial_secret_plaintext is None):
        raise ValueError(
            "initial_secret_kind and initial_secret_plaintext must be set together"
        )
    if initial_secret_kind is not None and initial_secret_kind not in WORKSPACE_REPO_SECRET_KINDS:
        raise ValueError(
            f"unknown secret kind {initial_secret_kind!r}; expected one of "
            f"{WORKSPACE_REPO_SECRET_KINDS}"
        )

    webhook_secret = _generate_webhook_secret()
    timestamp = _now()
    encrypted_initial = (
        encrypt_value(initial_secret_plaintext, session_factory=factory)
        if initial_secret_plaintext is not None
        else None
    )

    with factory() as session:
        row = WorkspaceRepo(
            workspace_id=workspace_id,
            slug=slug,
            url=url,
            default_branch=default_branch,
            provider_kind=provider_kind,
            sync_state="idle",
            webhook_secret=webhook_secret,
            created_by_user_id=created_by_user_id,
            created_at=timestamp,
        )
        session.add(row)
        session.flush()  # assign PK before adding the secret

        if initial_secret_kind is not None and encrypted_initial is not None:
            session.add(
                WorkspaceRepoSecret(
                    workspace_repo_id=row.id,
                    kind=initial_secret_kind,
                    encrypted_value=encrypted_initial,
                    created_at=timestamp,
                )
            )

        session.commit()
        session.refresh(row)

    return CreateRepoResult(repo=row, webhook_secret_plaintext=webhook_secret)


def add_secret(
    factory: sessionmaker[Session],
    *,
    repo_id: int,
    kind: str,
    plaintext: str,
) -> WorkspaceRepoSecret:
    """Add a secret of *kind* to *repo_id*, or rotate the existing one.

    Args:
        factory: SQLAlchemy session factory.
        repo_id: ``WorkspaceRepo.id``.
        kind: One of :data:`WORKSPACE_REPO_SECRET_KINDS`.
        plaintext: Cleartext credential.  Encrypted via the
            install master key before write.

    Returns:
        The persisted row (after commit + refresh).

    Raises:
        ValueError: ``kind`` not recognised.
    """
    if kind not in WORKSPACE_REPO_SECRET_KINDS:
        raise ValueError(
            f"unknown secret kind {kind!r}; expected one of {WORKSPACE_REPO_SECRET_KINDS}"
        )

    encrypted = encrypt_value(plaintext, session_factory=factory)
    timestamp = _now()

    with factory() as session:
        existing = session.execute(
            select(WorkspaceRepoSecret).where(
                WorkspaceRepoSecret.workspace_repo_id == repo_id,
                WorkspaceRepoSecret.kind == kind,
            )
        ).scalar_one_or_none()
        if existing is None:
            row = WorkspaceRepoSecret(
                workspace_repo_id=repo_id,
                kind=kind,
                encrypted_value=encrypted,
                created_at=timestamp,
            )
            session.add(row)
        else:
            existing.encrypted_value = encrypted
            existing.rotated_at = timestamp
            row = existing
        session.commit()
        session.refresh(row)
        return row


def rotate_webhook_secret(
    factory: sessionmaker[Session],
    *,
    repo_id: int,
) -> str:
    """Generate a fresh webhook secret and return cleartext.

    Args:
        factory: SQLAlchemy session factory.
        repo_id: ``WorkspaceRepo.id``.

    Returns:
        New cleartext webhook secret.  Reveal once; subsequent
        verification uses the stored value (which is also the
        cleartext — Fernet would prevent constant-time HMAC
        comparison if we encrypted).

    Raises:
        ValueError: Repo not found.
    """
    new_secret = _generate_webhook_secret()
    with factory() as session:
        row = session.get(WorkspaceRepo, repo_id)
        if row is None:
            raise ValueError(f"workspace_repo {repo_id} not found")
        row.webhook_secret = new_secret
        session.commit()
    return new_secret


def delete_repo(
    factory: sessionmaker[Session],
    *,
    repo_id: int,
    base_dir: Path,
) -> bool:
    """Delete *repo_id* + cascade secrets + remove the clone dir.

    Args:
        factory: SQLAlchemy session factory.
        repo_id: ``WorkspaceRepo.id``.
        base_dir: Resolved ``settings.workspace_repos.base_dir``.
            Used to locate the clone dir; removed if it exists.

    Returns:
        ``True`` when a row was deleted; ``False`` when no row
        existed for *repo_id*.
    """
    with factory() as session:
        row = session.get(WorkspaceRepo, repo_id)
        if row is None:
            return False
        clone_dir = _resolve_clone_dir(base_dir, row.workspace_id, row.slug)
        # cascade via the FK
        session.delete(row)
        session.commit()
    if clone_dir.exists():
        shutil.rmtree(clone_dir, ignore_errors=True)
    return True


def list_repos_for_workspace(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
) -> list[WorkspaceRepo]:
    """Return every repo registered to *workspace_id*, oldest first."""
    with factory() as session:
        rows = (
            session.execute(
                select(WorkspaceRepo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .order_by(WorkspaceRepo.id.asc())
            )
            .scalars()
            .all()
        )
        # Detach so callers outside the session can read attributes
        for row in rows:
            session.expunge(row)
        return list(rows)


def list_repos_due_for_sync(
    factory: sessionmaker[Session],
    *,
    cutoff: datetime.datetime,
) -> list[WorkspaceRepo]:
    """Return repos whose ``last_synced_at`` is older than *cutoff*.

    Used by the cron loop in 51.4.  Repos that have never synced
    are also returned.

    Args:
        factory: SQLAlchemy session factory.
        cutoff: ``utcnow() - interval``.

    Returns:
        Stable-ordered list (oldest sync first, then never-synced).
    """
    with factory() as session:
        rows = (
            session.execute(
                select(WorkspaceRepo)
                .where(
                    (WorkspaceRepo.last_synced_at.is_(None))
                    | (WorkspaceRepo.last_synced_at < cutoff)
                )
                .order_by(
                    WorkspaceRepo.last_synced_at.asc().nullsfirst(),
                    WorkspaceRepo.id.asc(),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            session.expunge(row)
        return list(rows)


def _pick_secret_for_provider(
    secrets_rows: list[WorkspaceRepoSecret],
    *,
    factory: sessionmaker[Session],
) -> ResolvedSecret | None:
    """Return the highest-priority decrypted secret, or ``None``.

    Priority order: ``oauth_token`` (refreshed in 51.6), then
    ``https_token``, then ``deploy_key``.  Higher-priority secrets
    win because:

    * oauth tokens are short-lived and intentionally rotated;
      using the deploy key when an OAuth token is also present
      would be a regression.
    * https tokens are simpler to rotate than ssh deploy keys
      (just paste a new PAT) so admins typically prefer them
      where both exist.

    Args:
        secrets_rows: All secrets attached to the repo.
        factory: SQLAlchemy session factory used to fetch the
            master key for decrypt.

    Returns:
        :class:`ResolvedSecret` or ``None`` when the repo has no
        secrets configured (public clone path).
    """
    by_kind = {secret.kind: secret for secret in secrets_rows}
    for kind in ("oauth_token", "https_token", "deploy_key"):
        row = by_kind.get(kind)
        if row is not None:
            decrypted = decrypt_value(row.encrypted_value, session_factory=factory)
            # The kind literal is constrained by WORKSPACE_REPO_SECRET_KINDS but
            # mypy/pyright cannot prove it from the tuple lookup; cast via the
            # ResolvedSecret constructor's typing.
            return ResolvedSecret(kind=kind, value=decrypted)  # type: ignore[arg-type]
    return None


def build_post_pull_loader_hook(
    factory: sessionmaker[Session],
    *,
    settings: object | None = None,
) -> Any:
    """Return a post-pull hook that re-runs the workspace yaml loaders.

    The hook signature matches :func:`sync_repo`'s ``on_post_pull``
    contract: ``(workspace_id, slug, head_sha) -> dict``.  After a
    successful clone or pull the hook re-runs the workspace-scoped
    loaders for data products and conventions; counts of UPSERTed
    contracts are returned in a dict that ``sync_repo`` merges into
    :class:`SyncOutcome.extra` (and surfaces on
    ``loaded_data_products`` / ``loaded_conventions`` typed
    attributes).

    Loader errors are swallowed inside ``sync_repo`` already — the
    hook itself prefers to surface a structured ``error`` field
    rather than raise so the sync is recorded as ``ok=True`` even
    when one yaml is malformed (the loader stamps a row in the
    DataProductYamlInvalid path on its own).

    Args:
        factory: SQLAlchemy session factory.
        settings: Optional :class:`Settings` override.  Default
            builds a fresh ``Settings()``.

    Returns:
        Callable suitable for ``sync_repo(on_post_pull=...)``.
    """
    # Local imports keep workspace_repos.py free of yaml/loader
    # transitive deps for callers that just want CRUD.
    from pointlessql.conventions import load_conventions_for_workspace
    from pointlessql.data_products import load_contracts_for_workspace

    def _hook(workspace_id: int, slug: str, head_sha: str | None) -> dict[str, Any]:
        del slug, head_sha  # Not used today; future hooks may correlate.
        out: dict[str, Any] = {}
        try:
            contracts = load_contracts_for_workspace(
                factory, workspace_id=workspace_id, settings=settings
            )
            out["loaded_data_products"] = len(contracts)
        except Exception as exc:  # noqa: BLE001 — loader errors stamp via the loader
            # bare-broad-ok: loader already raises a domain error and the
            # sync log records the diagnostic; we don't want a single bad
            # yaml to mark the sync itself as failed.
            out["data_products_loader_error"] = repr(exc)

        try:
            load_conventions_for_workspace(factory, workspace_id=workspace_id)
            # The conventions loader is a config singleton — there is no
            # "row count" to report, just whether it ran.
            out["loaded_conventions"] = 1
        except Exception as exc:  # noqa: BLE001 — same reasoning
            # bare-broad-ok: see data-products branch above.
            out["conventions_loader_error"] = repr(exc)
        return out

    return _hook


async def sync_repo(
    factory: sessionmaker[Session],
    *,
    repo_id: int,
    base_dir: Path,
    trigger: SyncTrigger = "manual",
    actor_user_id: int | None = None,
    on_post_pull: Any = None,
) -> SyncOutcome:
    """Clone-or-pull *repo_id*, persist state transitions, return outcome.

    The function is idempotent — re-runs against an already-synced
    repo do a fast pull (no-op when the head is unchanged) without
    touching the disk image.

    Args:
        factory: SQLAlchemy session factory.
        repo_id: ``WorkspaceRepo.id``.
        base_dir: Resolved ``settings.workspace_repos.base_dir``.
        trigger: How the sync was initiated.  Audited for
            attribution.
        actor_user_id: Triggering user (loose link).
        on_post_pull: Optional callback invoked after a successful
            clone/pull.  Receives ``(workspace_id, repo_slug,
            head_sha)`` and may mutate ``SyncOutcome`` via its
            return value (a dict merged into ``extra``).  51.2
            uses this hook to drive the loader-reload pass without
            adding a hard dependency this sprint.

    Returns:
        :class:`SyncOutcome`.

    Raises:
        ValueError: Repo not found.
    """
    timestamp = _now()
    with factory() as session:
        repo = session.get(WorkspaceRepo, repo_id)
        if repo is None:
            raise ValueError(f"workspace_repo {repo_id} not found")
        repo.sync_state = "syncing"
        session.commit()
        session.refresh(repo)
        slug = repo.slug
        url = repo.url
        branch = repo.default_branch
        provider_kind = repo.provider_kind
        workspace_id = repo.workspace_id
        secrets_rows = list(
            session.execute(
                select(WorkspaceRepoSecret).where(
                    WorkspaceRepoSecret.workspace_repo_id == repo_id
                )
            ).scalars()
        )
        for secret_row in secrets_rows:
            session.expunge(secret_row)

    provider = resolve_provider(provider_kind)
    secret = _pick_secret_for_provider(secrets_rows, factory=factory)
    target = _resolve_clone_dir(base_dir, workspace_id, slug)

    operation: Literal["clone", "pull"]
    head_sha: str | None = None
    changed = False
    error: str | None = None
    ok = True

    try:
        if (target / ".git").exists():
            operation = "pull"
            pull_result = await provider.pull(target, branch=branch, secret=secret)
            head_sha = pull_result.head_sha
            changed = pull_result.changed
        else:
            # Make sure no stale half-clone or rogue file blocks the clone.
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            operation = "clone"
            clone_result = await provider.clone(
                url, target, branch=branch, secret=secret
            )
            head_sha = clone_result.head_sha
            changed = True
    except WorkspaceRepoCloneFailed as exc:
        ok = False
        error = exc.detail
        # Fall through to the persist block; we still want the row to record
        # the failure so the admin UI can render it.
        operation = "clone" if not (target / ".git").exists() else "pull"
    except Exception as exc:  # noqa: BLE001 — capture any unexpected fault
        ok = False
        error = f"{type(exc).__name__}: {exc}"
        operation = "clone" if not (target / ".git").exists() else "pull"
        logger.exception("workspace_repo %s sync raised", repo_id)

    extra: dict[str, Any] = {}
    if ok and on_post_pull is not None:
        try:
            hook_result = on_post_pull(workspace_id, slug, head_sha)
            if asyncio.iscoroutine(hook_result):
                hook_result = await hook_result
            if isinstance(hook_result, dict):
                extra.update(cast("dict[str, Any]", hook_result))
        except Exception:  # noqa: BLE001 — loader errors must not poison the sync
            logger.exception("post-pull hook for workspace_repo %s failed", repo_id)
            extra["post_pull_hook_error"] = True

    finished_at = _now()
    with factory() as session:
        row = session.get(WorkspaceRepo, repo_id)
        if row is not None:
            if ok:
                row.sync_state = "ok"
                row.last_synced_at = finished_at
                row.last_synced_sha = head_sha
                row.last_sync_error = None
            else:
                row.sync_state = "error"
                row.last_sync_error = error
            session.commit()

    outcome = SyncOutcome(
        repo_id=repo_id,
        slug=slug,
        ok=ok,
        head_sha=head_sha,
        changed=changed,
        trigger=trigger,
        error=error,
        operation=operation,
        loaded_data_products=int(extra.get("loaded_data_products", 0)),
        loaded_conventions=int(extra.get("loaded_conventions", 0)),
        extra=extra,
    )
    del actor_user_id, timestamp  # captured into audit-log row by the route layer
    return outcome
