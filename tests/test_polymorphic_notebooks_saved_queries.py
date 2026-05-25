"""notebook + saved_query entity-kind registration.

Coverage:

* Migration creates the ``notebooks`` table.
* Both kinds are registered with the expected ``supports_*`` flags
  + URL builders.
* ``#notebook:<uuid>`` + ``#query:<slug>`` citations resolve.
* The audit-target builder emits the generic ``notebook:`` and
  ``saved_query:`` prefixes (locked decision #9).
* The polymorphic dispatcher accepts well-formed refs + rejects
  malformed ones for both kinds.
* Polymorphic comment + endorsement round-trip works for both
  kinds.
* The notebook detail page exposes the Social toolbar button +
  the offcanvas drawer.
* The saved-query detail page renders the 5-tab nav strip and
  socialTabs(kind='saved_query') x-data.
"""

from __future__ import annotations

import pathlib
import uuid

import httpx
import pytest
from sqlalchemy import inspect

from pointlessql.api.main import app
from pointlessql.api.social_routes._kind_dispatch import parse_ref
from pointlessql.models.notebook import Notebook
from pointlessql.services.social import entity_registry
from pointlessql.services.social.citations import resolve_citations

_TEMPLATES_ROOT = pathlib.Path("/home/flo/git/PointlesSQL/frontend/templates")


def test_notebooks_table_present_after_migration() -> None:
    """The ``notebooks`` table exists with the path UNIQUE."""
    factory = app.state.session_factory
    with factory() as session:
        insp = inspect(session.get_bind())
        assert "notebooks" in insp.get_table_names()
        uqs = {u["name"] for u in insp.get_unique_constraints("notebooks")}
        assert "uq_notebooks_path_per_workspace" in uqs


def test_notebook_orm_round_trip() -> None:
    """Insert + read-back works with a 36-char UUID id."""
    factory = app.state.session_factory
    nb_id = str(uuid.uuid4())
    with factory() as session:
        nb = Notebook(id=nb_id, workspace_id=1, file_path="seed/round-trip.py")
        session.add(nb)
        session.commit()
        echo = session.get(Notebook, nb_id)
        assert echo is not None
        assert echo.workspace_id == 1
        assert str(echo.file_path) == "seed/round-trip.py"


def test_notebook_kind_is_registered() -> None:
    """The registry exposes ``notebook`` after 77.6."""
    assert "notebook" in entity_registry.all_kinds()
    spec = entity_registry.get("notebook")
    assert spec.label == "Notebook"
    assert spec.audit_target_prefix == "notebook"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False
    assert spec.tab_keys == (
        "discussion",
        "endorsements",
        "followers",
        "readme",
    )


def test_saved_query_kind_is_registered() -> None:
    """The registry exposes ``saved_query`` after 77.6."""
    assert "saved_query" in entity_registry.all_kinds()
    spec = entity_registry.get("saved_query")
    assert spec.label == "Saved query"
    assert spec.audit_target_prefix == "saved_query"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False


def test_notebook_url_builder() -> None:
    """A 36-char UUID builds a ``/notebooks/uuid/{uuid}`` URL."""
    nb_uuid = str(uuid.uuid4())
    assert entity_registry.url_for("notebook", nb_uuid) == f"/notebooks/uuid/{nb_uuid}"
    assert entity_registry.url_for("notebook", "not-a-uuid") == "/notebooks"


def test_saved_query_url_builder() -> None:
    """A slug builds a ``/audit/queries/{slug}`` URL."""
    assert entity_registry.url_for("saved_query", "slow-tables") == "/audit/queries/slow-tables"
    assert entity_registry.url_for("saved_query", "") == "/audit/queries"


def test_audit_targets_use_generic_kind_prefixes() -> None:
    """Both kinds use the generic ``{kind}:`` audit-log prefix."""
    nb_uuid = str(uuid.uuid4())
    assert (
        entity_registry.audit_target("notebook", nb_uuid, suffix="tab-discussion")
        == f"notebook:{nb_uuid}#tab-discussion"
    )
    assert (
        entity_registry.audit_target("saved_query", "slow-tables", suffix="tab-readme")
        == "saved_query:slow-tables#tab-readme"
    )


def test_notebook_citation_resolves() -> None:
    """``#notebook:<uuid>`` renders as a markdown anchor."""
    nb_uuid = str(uuid.uuid4())
    body = f"see #notebook:{nb_uuid} for context"
    out = resolve_citations(body, app.state.session_factory, 1)
    short = nb_uuid[:8]
    assert f"[#notebook:{short}](/notebooks/uuid/{nb_uuid})" in out


def test_saved_query_citation_resolves() -> None:
    """``#query:slug`` renders as a markdown anchor."""
    body = "see #query:slow-tables for context"
    out = resolve_citations(body, app.state.session_factory, 1)
    assert "[#slow-tables](/audit/queries/slow-tables)" in out


def test_parse_ref_accepts_notebook_uuid() -> None:
    """The polymorphic dispatcher accepts a canonical UUID."""
    nb_uuid = str(uuid.uuid4())
    assert parse_ref("notebook", nb_uuid) == nb_uuid


def test_parse_ref_rejects_short_notebook_ref() -> None:
    """Non-UUID refs raise 400 with the contract message."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("notebook", "abc")
    assert exc.value.status_code == 400
    assert "36-char UUID" in exc.value.detail


def test_parse_ref_accepts_saved_query_slug() -> None:
    """The polymorphic dispatcher accepts a slug."""
    assert parse_ref("saved_query", "slow-tables") == "slow-tables"


def test_parse_ref_rejects_saved_query_with_slash() -> None:
    """Refs with a forward-slash raise 400."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("saved_query", "bad/slash")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_notebook_comment_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic comment write/read for ``kind='notebook'``."""
    nb_uuid = str(uuid.uuid4())
    res = await admin_client.post(
        f"/api/social/notebook/{nb_uuid}/comments",
        json={"body_md": "notebook comment OK"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["body_md"] == "notebook comment OK"


@pytest.mark.asyncio
async def test_saved_query_endorsement_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic endorsement apply for ``kind='saved_query'``."""
    res = await admin_client.post(
        "/api/social/saved_query/slow-tables/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res.status_code == 200, res.text


def test_notebook_editor_template_carries_drawer_marker() -> None:
    """Editor template + its partials wire the right-edge social tabs.

    Phase 86 split the editor template into page-scoped partials; the
    Phase-77.6 social drawer originally lived in its own
    ``social_drawer.html`` partial.  Sprint 113.2 collapsed that
    surface (plus the Chat drawer and Variables Inspector) into one
    unified tabbed right-edge drawer at
    ``_partials/notebook_editor/right_drawer.html`` — Discussion,
    Endorsements, Followers and README are now 4 of the 6 tabs there.
    This test asserts the social scope still wires up.
    """
    import pathlib

    parts = [
        (_TEMPLATES_ROOT / "pages/notebook_editor.html").read_text(),
        (_TEMPLATES_ROOT / "pages/_partials/notebook_editor/right_drawer.html").read_text(),
    ]
    body = "\n".join(parts)
    assert "pql-right-drawer" in body
    assert "socialTabs({" in body
    assert 'kind: "notebook"' in body
    bootstrap = pathlib.Path("frontend/js/bootstrap.js").read_text()
    assert "window.notebookDiscussion = notebookDiscussion" in bootstrap
    assert "window.notebookReadme = notebookReadme" in bootstrap


def test_saved_query_template_has_five_tab_nav_strip() -> None:
    """``saved_audit_query_detail.html`` carries the 5-tab nav strip."""
    body = (_TEMPLATES_ROOT / "pages/saved_audit_query_detail.html").read_text()
    for marker in (
        'data-pql-tab-key="overview"',
        'data-pql-tab-key="discussion"',
        'data-pql-tab-key="endorsements"',
        'data-pql-tab-key="followers"',
        'data-pql-tab-key="readme"',
    ):
        assert marker in body, f"saved_audit_query_detail missing {marker}"
    assert 'kind: "saved_query"' in body
    assert 'pqlStarToggle({kind: "saved_query"' in body
