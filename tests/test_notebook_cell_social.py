"""notebook_cell polymorphic plumbing + bulk-counts.

Coverage:

* Migration creates the ``notebook_cells`` table.
* ``notebook_cell`` kind is registered with the right capability flags.
* ``parse_ref`` accepts well-formed composite refs + rejects malformed.
* ``/api/social/notebook_cell/{ref}/comments`` round-trips.
* ``/api/social/notebook_cell/{ref}/follow`` round-trips.
* ``/api/social/notebook_cell/_bulk_counts`` aggregates correctly.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import inspect

from pointlessql.api.main import app
from pointlessql.api.social_routes._kind_dispatch import parse_ref
from pointlessql.exceptions import BadRequestError
from pointlessql.models.notebook import Notebook
from pointlessql.services.social import entity_registry


def _nb_cell_ref(nb_uuid: str | None = None, cell_uuid: str | None = None) -> str:
    """Build a well-formed ``notebook_cell`` ref."""
    return f"{nb_uuid or str(uuid.uuid4())}:{cell_uuid or str(uuid.uuid4())}"


def test_notebook_cells_table_present_after_migration() -> None:
    """The ``notebook_cells`` table exists with both supporting indexes."""
    factory = app.state.session_factory
    with factory() as session:
        insp = inspect(session.get_bind())
        assert "notebook_cells" in insp.get_table_names()
        ix_names = {i["name"] for i in insp.get_indexes("notebook_cells")}
        assert "ix_notebook_cells_live_ordinal" in ix_names
        assert "ix_notebook_cells_notebook_hash" in ix_names


def test_notebook_cell_kind_registered() -> None:
    """Registry exposes ``notebook_cell`` with cell-scope capabilities."""
    assert "notebook_cell" in entity_registry.all_kinds()
    spec = entity_registry.get("notebook_cell")
    assert spec.label == "Notebook cell"
    assert spec.audit_target_prefix == "notebook_cell"
    assert spec.supports_reviews is False
    assert spec.supports_endorsements is False
    assert spec.supports_readme is False
    assert spec.supports_issues is False
    assert spec.supports_stars is False
    assert spec.tab_keys == ("discussion", "followers")


def test_notebook_cell_url_builder_round_trips() -> None:
    """A well-formed composite ref builds the editor deep-link."""
    nb = str(uuid.uuid4())
    cell = str(uuid.uuid4())
    assert (
        entity_registry.url_for("notebook_cell", f"{nb}:{cell}")
        == f"/notebooks/uuid/{nb}?cell={cell}"
    )
    assert entity_registry.url_for("notebook_cell", "garbage") == "/notebooks"
    assert entity_registry.url_for("notebook_cell", "incomplete:") == "/notebooks"


def test_parse_ref_accepts_well_formed_composite() -> None:
    """The dispatcher accepts ``{uuid36}:{uuid36}``."""
    ref = _nb_cell_ref()
    assert parse_ref("notebook_cell", ref) == ref


@pytest.mark.parametrize(
    "bad_ref",
    [
        "abc",
        "abc:def",
        # Fixed UUID-format constants (not uuid4()) so parametrize ids are stable
        # across processes; otherwise pytest-xdist workers collect divergent ids.
        "11111111-1111-4111-8111-111111111111:short",
        "short:22222222-2222-4222-8222-222222222222",
        "33333333-3333-4333-8333-333333333333",  # missing colon entirely
    ],
)
def test_parse_ref_rejects_malformed(bad_ref: str) -> None:
    """Malformed composite refs raise 400 with the contract message."""
    # converted from HTTPException to BadRequestError.
    with pytest.raises(BadRequestError) as exc:
        parse_ref("notebook_cell", bad_ref)
    assert exc.value.status_code == 400
    assert "notebook_uuid" in exc.value.detail or "UUID" in exc.value.detail


@pytest.mark.asyncio
async def test_notebook_cell_comment_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic comment write/read for ``kind='notebook_cell'``."""
    ref = _nb_cell_ref()
    res = await admin_client.post(
        f"/api/social/notebook_cell/{ref}/comments",
        json={"body_md": "this cell broke for me"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["body_md"] == "this cell broke for me"

    list_res = await admin_client.get(f"/api/social/notebook_cell/{ref}/comments")
    assert list_res.status_code == 200, list_res.text
    listing = list_res.json()
    assert listing["entity_kind"] == "notebook_cell"
    assert listing["entity_ref"] == ref
    assert any(c["body_md"] == "this cell broke for me" for c in listing["comments"])


@pytest.mark.asyncio
async def test_notebook_cell_review_category_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """``category='review'`` is accepted on cell comments."""
    ref = _nb_cell_ref()
    res = await admin_client.post(
        f"/api/social/notebook_cell/{ref}/comments",
        json={"body_md": "✅ **Approved**\n\nLGTM", "category": "review"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["category"] == "review"
    assert payload["body_md"].startswith("✅ **Approved**")

    list_res = await admin_client.get(f"/api/social/notebook_cell/{ref}/comments")
    assert list_res.status_code == 200
    reviews = [c for c in list_res.json()["comments"] if c["category"] == "review"]
    assert len(reviews) >= 1


@pytest.mark.asyncio
async def test_notebook_cell_comment_as_agent_principal_ok(
    admin_client: httpx.AsyncClient,
) -> None:
    """``?as_agent=`` on the polymorphic POST.

    The polymorphic comment POST previously dropped ``as_agent``
    for non-DP kinds (silent ignore).  The speak-as-agent envelope
    is now widened to every kind, so cell-level review decisions
    authored via ``pql_review_cell`` carry the agent chip on the
    rendered review badge.
    """
    factory = app.state.session_factory
    principal_id: int
    from sqlalchemy import select

    from pointlessql.models.auth import User as _User

    with factory() as session:
        principal_id = int(
            session.execute(select(_User.id).where(_User.email == "test@test.com")).scalar_one()
        )

    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Cell Reviewer Bot",
            "principal_user_id": principal_id,
        },
    )
    assert create.status_code == 200, create.text
    slug = create.json()["slug"]

    ref = _nb_cell_ref()
    res = await admin_client.post(
        f"/api/social/notebook_cell/{ref}/comments?as_agent={slug}",
        json={
            "body_md": "review-decision: approved\n\nLGTM",
            "category": "review",
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["category"] == "review"
    assert payload["agent"] is not None
    assert payload["agent"]["slug"] == slug
    assert payload["author"]["user_id"] == principal_id


@pytest.mark.asyncio
async def test_notebook_cell_comment_as_agent_non_principal_rejected(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A different user cannot speak as another user's agent on a cell."""
    factory = app.state.session_factory
    from sqlalchemy import select

    from pointlessql.models.auth import User as _User

    with factory() as session:
        principal_id = int(
            session.execute(select(_User.id).where(_User.email == "test@test.com")).scalar_one()
        )
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Owner Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]

    ref = _nb_cell_ref()
    res = await non_admin_client.post(
        f"/api/social/notebook_cell/{ref}/comments?as_agent={slug}",
        json={"body_md": "trying to impersonate", "category": "review"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_notebook_cell_comment_unknown_agent_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown ``?as_agent=`` slug returns 404 on cell comments."""
    ref = _nb_cell_ref()
    res = await admin_client.post(
        f"/api/social/notebook_cell/{ref}/comments?as_agent=ghost-bot",
        json={"body_md": "no agent here", "category": "review"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_notebook_cell_follow_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic follow apply / count / unfollow for cells."""
    ref = _nb_cell_ref()
    res = await admin_client.post(f"/api/social/notebook_cell/{ref}/follow")
    assert res.status_code == 200, res.text

    count_res = await admin_client.get(f"/api/social/notebook_cell/{ref}/followers/count")
    assert count_res.status_code == 200
    assert count_res.json()["count"] >= 1
    assert count_res.json()["following"] is True

    drop_res = await admin_client.delete(f"/api/social/notebook_cell/{ref}/follow")
    assert drop_res.status_code == 200, drop_res.text


@pytest.mark.asyncio
async def test_bulk_counts_aggregates_for_one_notebook(
    admin_client: httpx.AsyncClient,
) -> None:
    """Bulk-counts collapses N cells × 3 axes into one round-trip."""
    factory = app.state.session_factory
    nb_uuid = str(uuid.uuid4())
    with factory() as session:
        session.add(
            Notebook(
                id=nb_uuid,
                workspace_id=1,
                file_path=f"bulk_{nb_uuid[:8]}.py",
            )
        )
        session.commit()

    cell_a = str(uuid.uuid4())
    cell_b = str(uuid.uuid4())
    ref_a = f"{nb_uuid}:{cell_a}"
    ref_b = f"{nb_uuid}:{cell_b}"

    # Seed: two comments on A, one on B, one follow on B.
    await admin_client.post(
        f"/api/social/notebook_cell/{ref_a}/comments",
        json={"body_md": "first thought"},
    )
    await admin_client.post(
        f"/api/social/notebook_cell/{ref_a}/comments",
        json={"body_md": "second thought"},
    )
    await admin_client.post(
        f"/api/social/notebook_cell/{ref_b}/comments",
        json={"body_md": "different cell"},
    )
    await admin_client.post(f"/api/social/notebook_cell/{ref_b}/follow")

    res = await admin_client.get(
        "/api/social/notebook_cell/_bulk_counts",
        params={"notebook_id": nb_uuid},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["notebook_id"] == nb_uuid
    counts = payload["counts"]
    assert counts[cell_a]["comments"] == 2
    assert counts[cell_a]["followers"] == 0
    assert counts[cell_b]["comments"] == 1
    assert counts[cell_b]["followers"] == 1


@pytest.mark.asyncio
async def test_bulk_counts_rejects_unknown_notebook(
    admin_client: httpx.AsyncClient,
) -> None:
    """Bulk-counts returns 404 when the notebook UUID is unknown."""
    res = await admin_client.get(
        "/api/social/notebook_cell/_bulk_counts",
        params={"notebook_id": str(uuid.uuid4())},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_bulk_counts_rejects_short_notebook_id(
    admin_client: httpx.AsyncClient,
) -> None:
    """Bulk-counts returns 400 when the UUID is malformed."""
    res = await admin_client.get(
        "/api/social/notebook_cell/_bulk_counts",
        params={"notebook_id": "abc"},
    )
    assert res.status_code == 400


def test_curated_cell_tags_vocabulary() -> None:
    """curated vocabulary stays focused (six tags)."""
    from pointlessql.services.notebook.cell_tags import CURATED_CELL_TAGS

    assert "etl" in CURATED_CELL_TAGS
    assert "draft" in CURATED_CELL_TAGS
    assert "prod" in CURATED_CELL_TAGS
    assert "wip" in CURATED_CELL_TAGS
    assert "verified" in CURATED_CELL_TAGS
    assert "broken" in CURATED_CELL_TAGS
    # ``parameters`` has its own dedicated UI flow.
    assert "parameters" not in CURATED_CELL_TAGS
