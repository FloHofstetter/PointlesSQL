"""Tests — per-notebook Delta-branch bindings."""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Base, Notebook
from pointlessql.services.notebook import (
    branch_bindings as notebook_branch_bindings_service,
)


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    """In-memory SQLite session factory with the schema applied."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _seed_notebook(factory: sessionmaker) -> str:  # type: ignore[type-arg]
    """Insert one ``notebooks`` row and return its UUID."""
    nb_id = str(uuid.uuid4())
    with factory() as s:
        s.add(Notebook(id=nb_id, workspace_id=1, file_path="n.py"))
        s.commit()
    return nb_id


# -- service ------------------------------------------------------------------


def test_bind_branch_supersedes_prior(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Each ``bind_branch`` call supersedes the previous one."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        first = notebook_branch_bindings_service.bind_branch(
            session, notebook_id=nb_id, branch_name="exp1"
        )
        first_id = first.id
        session.commit()
        second = notebook_branch_bindings_service.bind_branch(
            session, notebook_id=nb_id, branch_name="exp2"
        )
        session.commit()
        # Re-load first to see superseded_at
        session.expire_all()
        from pointlessql.models import NotebookBranchBinding

        first_reloaded = session.get(NotebookBranchBinding, first_id)
        assert first_reloaded is not None
        assert first_reloaded.superseded_at is not None
        assert second.superseded_at is None


def test_bind_branch_rejects_bad_name(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Branch names with spaces / unsupported chars raise."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_branch_bindings_service.bind_branch(
                session, notebook_id=nb_id, branch_name="bad name!"
            )


def test_bind_branch_unknown_notebook_raises(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """Unknown notebook surfaces as ValidationError."""
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_branch_bindings_service.bind_branch(
                session,
                notebook_id="00000000-0000-0000-0000-000000000000",
                branch_name="exp1",
            )


def test_promote_records_lifecycle(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Promote sets promoted_at + supersedes the row."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        promoted = notebook_branch_bindings_service.promote_binding(
            session, notebook_id=nb_id, promoted_by_user_id=None
        )
        assert promoted.promoted_at is not None
        assert promoted.superseded_at is not None
        session.commit()


def test_promote_without_binding_raises(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Promoting when no current binding exists raises."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        with pytest.raises(ValidationError):
            notebook_branch_bindings_service.promote_binding(session, notebook_id=nb_id)


def test_discard_idempotent(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """Second discard returns None (no row left)."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        first = notebook_branch_bindings_service.discard_binding(session, notebook_id=nb_id)
        assert first is not None
        session.commit()
        second = notebook_branch_bindings_service.discard_binding(session, notebook_id=nb_id)
        assert second is None


def test_get_current_binding_returns_active(
    factory: sessionmaker,  # type: ignore[type-arg]
) -> None:
    """``get_current_binding`` returns the active row and ``None`` after discard."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        envelope = notebook_branch_bindings_service.get_current_binding(session, notebook_id=nb_id)
        assert envelope is not None
        assert envelope["branch_name"] == "exp"
        notebook_branch_bindings_service.discard_binding(session, notebook_id=nb_id)
        session.commit()
        assert (
            notebook_branch_bindings_service.get_current_binding(session, notebook_id=nb_id) is None
        )


def test_list_bindings_history(factory: sessionmaker) -> None:  # type: ignore[type-arg]
    """``list_bindings`` returns historical rows newest first."""
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="a")
        session.commit()
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="b")
        session.commit()
        rows = notebook_branch_bindings_service.list_bindings(session, notebook_id=nb_id)
        names = [r["branch_name"] for r in rows]
        assert names[0] == "b" and names[1] == "a"


# -- REST ---------------------------------------------------------------------


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at a tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


async def test_api_branch_lifecycle(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """bind → get → promote round-trip via REST."""
    await admin_client.post("/api/notebooks/create", json={"path": "x.py"})
    none = await admin_client.get("/api/notebooks/branch", params={"path": "x.py"})
    assert none.json()["current"] is None

    bound = await admin_client.post(
        "/api/notebooks/branch",
        json={"path": "x.py", "branch_name": "exp1"},
    )
    assert bound.status_code == 201
    assert bound.json()["branch_name"] == "exp1"
    assert bound.json()["is_current"] is True

    got = await admin_client.get("/api/notebooks/branch", params={"path": "x.py"})
    assert got.json()["current"]["branch_name"] == "exp1"

    promoted = await admin_client.post("/api/notebooks/branch/promote", json={"path": "x.py"})
    assert promoted.status_code == 200
    assert promoted.json()["promoted_at"] is not None

    after = await admin_client.get("/api/notebooks/branch", params={"path": "x.py"})
    assert after.json()["current"] is None


async def test_api_branch_history(workspace_dir: Path, admin_client: httpx.AsyncClient) -> None:
    """History endpoint surfaces every binding."""
    await admin_client.post("/api/notebooks/create", json={"path": "h.py"})
    for name in ("a", "b", "c"):
        await admin_client.post(
            "/api/notebooks/branch",
            json={"path": "h.py", "branch_name": name},
        )
    listed = await admin_client.get("/api/notebooks/branch/history", params={"path": "h.py"})
    assert len(listed.json()["bindings"]) == 3


async def test_api_branch_rejects_bad_name(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Invalid branch name surfaces as 422."""
    await admin_client.post("/api/notebooks/create", json={"path": "x.py"})
    resp = await admin_client.post(
        "/api/notebooks/branch",
        json={"path": "x.py", "branch_name": "bad name!"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# promote-reviewer webhook gate
# ---------------------------------------------------------------------------


def _captured_webhook(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status_code: int = 200,
    body: str = "",
    raise_exc: Exception | None = None,
) -> dict[str, object]:
    """Patch ``httpx.post`` inside ``branch_bindings`` to capture calls."""
    captured: dict[str, object] = {}

    def fake_post(
        url: str,
        *,
        content: bytes,
        headers: dict[str, str],
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        if raise_exc is not None:
            raise raise_exc
        return httpx.Response(status_code, content=body.encode("utf-8"))

    import httpx as _httpx_mod

    monkeypatch.setattr(_httpx_mod, "post", fake_post)
    return captured


def test_promote_webhook_unset_skips_gate(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL`` → no HTTP call."""
    monkeypatch.delenv("POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL", raising=False)
    captured = _captured_webhook(monkeypatch)
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        notebook_branch_bindings_service.promote_binding(session, notebook_id=nb_id)
        session.commit()
    assert captured == {}


def test_promote_webhook_happy_path_with_signature(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """200 response → promote proceeds; HMAC header present when secret set."""
    monkeypatch.setenv(
        "POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL",
        "https://shoreguard.test/approvals/ingest",
    )
    monkeypatch.setenv("POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET", "s3cret")
    captured = _captured_webhook(monkeypatch, status_code=200)

    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(
            session,
            notebook_id=nb_id,
            branch_name="exp",
            base_revision_uuid="rev-123",
        )
        session.commit()
        promoted = notebook_branch_bindings_service.promote_binding(
            session,
            notebook_id=nb_id,
            promoted_by_user_id=7,
            promoted_by_user_email="reviewer@example.com",
        )
        assert promoted.promoted_at is not None
        session.commit()
    assert captured["url"] == "https://shoreguard.test/approvals/ingest"
    import json as _json

    body = _json.loads(captured["content"])  # type: ignore[arg-type]
    assert body["notebook_id"] == nb_id
    assert body["branch_name"] == "exp"
    assert body["base_revision_uuid"] == "rev-123"
    assert body["promoted_by_user_id"] == 7
    assert body["promoted_by_user_email"] == "reviewer@example.com"
    assert "promote_intent_at" in body
    headers = captured["headers"]  # type: ignore[assignment]
    assert isinstance(headers, dict)
    sig = headers["x-pointlessql-signature"]
    assert sig.startswith("sha256=")
    # Re-compute HMAC over the same body and assert match.
    import hashlib
    import hmac

    expected = hmac.new(
        b"s3cret",
        captured["content"],
        hashlib.sha256,  # type: ignore[arg-type]
    ).hexdigest()
    assert sig == f"sha256={expected}"


def test_promote_webhook_omits_signature_without_secret(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No secret env var → no ``x-pointlessql-signature`` header."""
    monkeypatch.setenv(
        "POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL",
        "https://reviewer.test/intake",
    )
    monkeypatch.delenv("POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET", raising=False)
    captured = _captured_webhook(monkeypatch, status_code=200)
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        notebook_branch_bindings_service.promote_binding(session, notebook_id=nb_id)
        session.commit()
    headers = captured["headers"]  # type: ignore[assignment]
    assert isinstance(headers, dict)
    assert "x-pointlessql-signature" not in headers


def test_promote_webhook_denial_blocks_promote(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-2xx response → ValidationError; promoted_at stays None."""
    monkeypatch.setenv(
        "POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL",
        "https://reviewer.test/intake",
    )
    monkeypatch.delenv("POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_SECRET", raising=False)
    _captured_webhook(monkeypatch, status_code=403, body="policy denied")
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        with pytest.raises(ValidationError) as exc:
            notebook_branch_bindings_service.promote_binding(session, notebook_id=nb_id)
        assert "denied by reviewer" in str(exc.value)
        assert "policy denied" in str(exc.value)
        session.rollback()
        current = notebook_branch_bindings_service.get_current_binding(session, notebook_id=nb_id)
        assert current is not None
        assert current["promoted_at"] is None


def test_promote_webhook_network_failure_denies_by_default(
    factory: sessionmaker,  # type: ignore[type-arg]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transport error → gate stays closed (deny-by-default)."""
    monkeypatch.setenv(
        "POINTLESSQL_BRANCH_PROMOTE_WEBHOOK_URL",
        "https://reviewer.test/intake",
    )
    _captured_webhook(monkeypatch, raise_exc=RuntimeError("connection refused"))
    nb_id = _seed_notebook(factory)
    with factory() as session:
        notebook_branch_bindings_service.bind_branch(session, notebook_id=nb_id, branch_name="exp")
        session.commit()
        with pytest.raises(ValidationError) as exc:
            notebook_branch_bindings_service.promote_binding(session, notebook_id=nb_id)
        assert "webhook unreachable" in str(exc.value)
        session.rollback()
