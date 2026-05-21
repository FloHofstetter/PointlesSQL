"""API + service tests for Phase 98.B — notebook tags + template gallery."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.services.notebook import tags as notebook_tags_service
from pointlessql.services.notebook import templates as notebook_templates_service


@pytest.fixture
def workspace_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``settings.jupyter.notebooks_dir`` at an isolated tmp directory."""
    root = tmp_path / "notebooks"
    root.mkdir()
    monkeypatch.setattr(app.state.settings.jupyter, "notebooks_dir", root)
    return root


# -- service: tag normalisation -----------------------------------------------


def test_normalize_lowercases_and_strips() -> None:
    """Trims surrounding whitespace and lower-cases the tag."""
    assert notebook_tags_service._normalize("  ETL  ") == "etl"


def test_normalize_rejects_empty() -> None:
    """Empty / whitespace-only tags raise."""
    with pytest.raises(ValidationError):
        notebook_tags_service._normalize("   ")


def test_normalize_rejects_punctuation() -> None:
    """Tags outside ``[a-z0-9_-]`` raise."""
    with pytest.raises(ValidationError):
        notebook_tags_service._normalize("not allowed!")


# -- service: template gallery ------------------------------------------------


def test_list_templates_returns_curated_entries() -> None:
    """Manifest entries pointing at existing files surface."""
    out = notebook_templates_service.list_templates()
    ids = {row["id"] for row in out}
    assert "blank" in ids
    assert "sql_exploration" in ids
    assert "etl_pipeline" in ids
    assert "ml_quickstart" in ids


def test_create_from_template_writes_starter_body(
    workspace_dir: Path,
) -> None:
    """Copy the chosen template into the workspace at the dest path."""
    out = notebook_templates_service.create_from_template(
        notebooks_dir=workspace_dir,
        template_id="blank",
        dest_path="welcome.py",
    )
    assert out.exists()
    body = out.read_text()
    assert "# %%" in body


def test_create_from_template_rejects_unknown(workspace_dir: Path) -> None:
    """Unknown template_id raises ValidationError."""
    with pytest.raises(ValidationError):
        notebook_templates_service.create_from_template(
            notebooks_dir=workspace_dir,
            template_id="does-not-exist",
            dest_path="nope.py",
        )


# -- REST: GET /api/notebooks/templates --------------------------------------


async def test_api_list_templates(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Gallery endpoint returns the four shipped templates."""
    resp = await admin_client.get("/api/notebooks/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["templates"], list)
    ids = {row["id"] for row in data["templates"]}
    assert {"blank", "sql_exploration", "etl_pipeline", "ml_quickstart"} <= ids


async def test_api_create_from_template(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """POST creates the notebook + 201 envelope."""
    resp = await admin_client.post(
        "/api/notebooks/from-template",
        json={"template_id": "sql_exploration", "path": "explore.py"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json() == {"path": "explore.py"}
    assert (workspace_dir / "explore.py").is_file()
    body = (workspace_dir / "explore.py").read_text()
    assert "%sql" in body


async def test_api_create_from_template_rejects_unknown_id(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown template_id surfaces as a 422 validation error."""
    resp = await admin_client.post(
        "/api/notebooks/from-template",
        json={"template_id": "nope", "path": "foo.py"},
    )
    assert resp.status_code == 422


# -- REST: tag CRUD -----------------------------------------------------------


async def test_api_tag_crud_roundtrip(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Create → list → add tag → list (1 row) → delete → list (0 rows)."""
    await admin_client.post("/api/notebooks/create", json={"path": "n1.py"})

    listed = await admin_client.get("/api/notebooks/tags", params={"path": "n1.py"})
    assert listed.status_code == 200
    assert listed.json()["tags"] == []
    assert "etl" in listed.json()["curated"]

    added = await admin_client.post(
        "/api/notebooks/tags", json={"path": "n1.py", "tag": "ETL"}
    )
    assert added.status_code == 200
    assert added.json()["tag"] == "etl"

    after_add = await admin_client.get(
        "/api/notebooks/tags", params={"path": "n1.py"}
    )
    tags = [row["tag"] for row in after_add.json()["tags"]]
    assert tags == ["etl"]

    # idempotent re-add → still one row
    again = await admin_client.post(
        "/api/notebooks/tags", json={"path": "n1.py", "tag": "etl"}
    )
    assert again.status_code == 200
    after_again = await admin_client.get(
        "/api/notebooks/tags", params={"path": "n1.py"}
    )
    assert len([row["tag"] for row in after_again.json()["tags"]]) == 1

    deleted = await admin_client.request(
        "DELETE",
        "/api/notebooks/tags",
        json={"path": "n1.py", "tag": "etl"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["removed"] is True

    final = await admin_client.get("/api/notebooks/tags", params={"path": "n1.py"})
    assert final.json()["tags"] == []


async def test_api_tag_rejects_bad_chars(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Punctuation in tags surfaces as 422."""
    await admin_client.post("/api/notebooks/create", json={"path": "n2.py"})
    resp = await admin_client.post(
        "/api/notebooks/tags",
        json={"path": "n2.py", "tag": "bad tag!"},
    )
    assert resp.status_code == 422


async def test_api_tag_removes_returns_false_when_missing(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Removing a never-attached tag returns ``removed: false``."""
    await admin_client.post("/api/notebooks/create", json={"path": "n3.py"})
    resp = await admin_client.request(
        "DELETE",
        "/api/notebooks/tags",
        json={"path": "n3.py", "tag": "ghost"},
    )
    assert resp.status_code == 200
    assert resp.json()["removed"] is False


async def test_api_tag_requires_auth(
    workspace_dir: Path, anonymous_client: httpx.AsyncClient
) -> None:
    """Anonymous callers hit the auth gate."""
    resp = await anonymous_client.get(
        "/api/notebooks/tags", params={"path": "anything.py"}
    )
    assert resp.status_code in (401, 403)


async def test_api_tags_bulk_returns_per_path_map(
    workspace_dir: Path, admin_client: httpx.AsyncClient
) -> None:
    """Bulk endpoint indexes tags by relative path so the workspace tree."""
    await admin_client.post("/api/notebooks/create", json={"path": "a.py"})
    await admin_client.post("/api/notebooks/create", json={"path": "b.py"})
    await admin_client.post(
        "/api/notebooks/tags", json={"path": "a.py", "tag": "etl"}
    )
    await admin_client.post(
        "/api/notebooks/tags", json={"path": "a.py", "tag": "prod"}
    )
    await admin_client.post(
        "/api/notebooks/tags", json={"path": "b.py", "tag": "draft"}
    )

    resp = await admin_client.get("/api/notebooks/tags/bulk")
    assert resp.status_code == 200
    body = resp.json()
    assert "etl" in body["curated"]
    assert sorted(body["tags"]["a.py"]) == ["etl", "prod"]
    assert body["tags"]["b.py"] == ["draft"]


async def test_api_tags_bulk_requires_auth(
    workspace_dir: Path, anonymous_client: httpx.AsyncClient
) -> None:
    """Anonymous callers hit the auth gate on the bulk endpoint too."""
    resp = await anonymous_client.get("/api/notebooks/tags/bulk")
    assert resp.status_code in (401, 403)
