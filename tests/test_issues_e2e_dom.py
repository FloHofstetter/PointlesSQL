"""issues UI smoke (DOM + template source assertions).

Coverage:

* ``GET /issues`` renders the global index template + chip filters.
* ``GET /issues/{id}`` renders the detail template with the sidebar.
* The ``_issues_pane.html`` partial is referenced from table.html,
  model.html, branch_detail.html, and data_product.html.
* ``socialTabs(kind='issue')`` is the wrapping x-data on the issue
  detail page.
* The ``#issue:42`` citation regex round-trips through
  :func:`resolve_citations`.
* The polymorphic dispatcher accepts ``kind='issue'`` numeric refs
  and rejects malformed ones.
"""

from __future__ import annotations

import datetime
import pathlib
import uuid

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.api.social_routes._kind_dispatch import parse_ref
from pointlessql.models.social._issue import Issue
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social.citations import resolve_citations

_TEMPLATES_ROOT = pathlib.Path("/home/flo/git/PointlesSQL/frontend/templates")


def _seed_issue() -> int:
    """Insert one Issue row + its anchor, return the issue id."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        anchor = SocialTarget(
            workspace_id=1,
            entity_kind="issue",
            entity_ref=f"_pending_{uuid.uuid4().hex}",
        )
        parent = SocialTarget(workspace_id=1, entity_kind="table", entity_ref="main.sales.orders")
        session.add_all([anchor, parent])
        session.flush()
        issue = Issue(
            workspace_id=1,
            social_target_id=int(anchor.id),
            parent_social_target_id=int(parent.id),
            title="DOM smoke seed",
            body_md="seed body",
            state="open",
            opened_by_user_id=1,
            opened_at=now,
        )
        session.add(issue)
        session.flush()
        anchor.entity_ref = str(issue.id)
        session.commit()
        return int(issue.id)


@pytest.mark.asyncio
async def test_issues_index_page_renders_chip_filters(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/issues`` renders the index template with the chip row."""
    import pathlib

    res = await admin_client.get("/issues")
    assert res.status_code == 200, res.text
    body = res.text
    assert "Issues" in body
    assert "Open" in body and "Closed" in body
    assert "issuesIndex()" in body
    issues_js = pathlib.Path("frontend/js/pages/issues_index.js").read_text()
    assert "/api/issues" in issues_js


@pytest.mark.asyncio
async def test_issue_detail_page_renders_sidebar(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/issues/{id}`` renders the detail template with the sidebar."""
    issue_id = _seed_issue()
    res = await admin_client.get(f"/issues/{issue_id}")
    assert res.status_code == 200, res.text
    body = res.text
    assert "issueDetail" in body
    assert "Reopen" in body or "Close as completed" in body
    assert 'pqlStarToggle({kind: "issue"' in body
    assert 'socialTabs({kind: "issue"' in body


def test_issues_pane_partial_is_referenced_from_detail_pages() -> None:
    """Every Issues-enabled detail page includes the partial (directly or via a sub-partial)."""
    import re

    include_re = re.compile(r'include\s+"([^"]+)"')

    def references_issues_pane(relpath: str, depth: int = 0) -> bool:
        if depth > 4:
            return False
        path = _TEMPLATES_ROOT / relpath
        if not path.is_file():
            return False
        body = path.read_text()
        if "_issues_pane.html" in body:
            return True
        return any(references_issues_pane(inc, depth + 1) for inc in include_re.findall(body))

    for relpath in (
        "pages/table.html",
        "pages/model.html",
        "pages/branch_detail.html",
        "pages/data_product.html",
    ):
        assert references_issues_pane(relpath), (
            f"missing _issues_pane include reachable from {relpath}"
        )


def test_issues_pane_partial_exposes_issues_pane_factory() -> None:
    """The partial registers ``issuesPane`` on ``window``.

    Factory lives in frontend/js/partials/issues_pane.js; bootstrap.js
    attaches it on window.  The partial only carries the x-data
    invocation.
    """
    import pathlib

    body = (_TEMPLATES_ROOT / "partials/social/_issues_pane.html").read_text()
    assert "x-data='issuesPane({kind: kind, ref: ref})'" in body
    bootstrap = pathlib.Path("frontend/js/bootstrap.js").read_text()
    assert "window.issuesPane = issuesPane" in bootstrap


def test_issue_citation_resolves_through_registry() -> None:
    """``#issue:42`` renders as a markdown anchor."""
    body = "see #issue:42 for context"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    assert "[#issue:42](/issues/42)" in out


def test_parse_ref_accepts_numeric_issue_id() -> None:
    """The polymorphic dispatcher accepts an integer-id string."""
    assert parse_ref("issue", "42") == "42"


def test_parse_ref_rejects_non_numeric_issue_id() -> None:
    """A non-numeric ref raises 400 with the contract message."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("issue", "abc")
    assert exc.value.status_code == 400
    assert "numeric issue id" in exc.value.detail
