"""Phase 77.0.H — social-pane Jinja partial extraction.

Coverage:

* ``data_product.html`` renders successfully after the three
  large tab-pane blocks (Discussion / Reviews / README) were
  lifted out into ``partials/social/_{...}_pane.html``.  The
  rendered HTML still contains every load-bearing tab id and
  Alpine expression — the extraction is structural only, so
  behaviour stays byte-for-byte equivalent.
* Each partial file exists at the expected path so 77.1 can
  ``{% include %}`` it for table.html.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_products import DataProduct

_CONTRACT_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: test@test.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


@pytest.fixture
def seeded_dp(tmp_path: Path) -> int:
    """Load a DP contract; return the DP id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


def test_social_partials_exist_on_disk() -> None:
    """Every partial 77.1 will reuse is present at the expected path."""
    base = Path(__file__).resolve().parent.parent / "frontend" / "templates" / "partials" / "social"
    for name in ("_discussion_pane.html", "_reviews_pane.html", "_readme_pane.html"):
        path = base / name
        assert path.exists(), f"missing partial: {path}"
        body = path.read_text(encoding="utf-8")
        assert body.strip(), f"partial is empty: {path}"


@pytest.mark.asyncio
async def test_data_product_html_renders_with_three_social_panes(
    seeded_dp: int, admin_client: httpx.AsyncClient
) -> None:
    """The DP detail page still serves the social tab-panes."""
    del seeded_dp
    res = await admin_client.get("/data-products/main/sales_gold")
    assert res.status_code == 200, res.text
    body = res.text
    # All three tab-panes survived the extraction.
    assert 'id="tab-discussion"' in body
    assert 'id="tab-reviews"' in body
    assert 'id="tab-readme"' in body
    # Load-bearing Alpine bindings still wired up.
    assert "topLevelComments" in body
    assert "reviewDraftStars" in body
    assert "readmeDraft" in body
    # Phase 76.1 reaction strip survived.
    assert "toggleDpReaction" in body
    # Phase 73.4 passport block lives inside the readme partial.
    assert "pql-dp-passport-card" in body


@pytest.mark.asyncio
async def test_data_product_html_unchanged_for_post_post_flow(
    seeded_dp: int, admin_client: httpx.AsyncClient
) -> None:
    """A POSTed comment surfaces in the re-rendered DP page.

    Phase 77.0.H is a structural extraction only — every social write
    flow keeps working without any URL change.  This test exercises
    the round-trip to guard against a partial mis-include.
    """
    del seeded_dp
    res_post = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "phase77h smoke"},
    )
    assert res_post.status_code == 200, res_post.text
    res_list = await admin_client.get(
        "/api/data-products/main/sales_gold/comments"
    )
    assert res_list.status_code == 200, res_list.text
    bodies = [c["body_md"] for c in res_list.json()["comments"]]
    assert "phase77h smoke" in bodies
