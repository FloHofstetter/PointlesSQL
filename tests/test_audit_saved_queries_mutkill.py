"""Behaviour tests targeting surviving mutants in saved-audit-query CRUD.

These pin observable outputs of
:mod:`pointlessql.services.audit.saved_queries`: the slug derivation,
the SQL allow-list validator, the create / update / execute paths, the
paginated + full listings (including the starters-first ordering), the
serialised-dict shape, and the idempotent starter-row bootstrap.

The fixtures reuse the in-memory SQLite engine + seeded workspace wired
by ``tests/conftest.py`` through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import SavedAuditQuery
from pointlessql.services.audit import saved_queries as sq


def _factory() -> Any:
    return app.state.session_factory


def _seed_saved_queries(n: int) -> None:
    """Insert ``n`` extra non-starter ``saved_audit_queries`` rows."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as s:
        for i in range(n):
            s.add(
                SavedAuditQuery(
                    slug=f"seed-{i}-{uuid.uuid4().hex[:6]}",
                    title=f"seed {i}",
                    description=None,
                    sql_text="SELECT 1",
                    owner_id=1,
                    is_shared=True,
                    is_starter=False,
                    alert_threshold_count=None,
                    created_at=now,
                    updated_at=now,
                )
            )
        s.commit()


def _insert_query(
    *,
    slug: str,
    is_starter: bool,
    updated_at: datetime.datetime,
) -> None:
    """Insert one row with explicit ``is_starter`` + ``updated_at``."""
    with _factory()() as s:
        s.add(
            SavedAuditQuery(
                slug=slug,
                title=slug,
                description=None,
                sql_text="SELECT 1",
                owner_id=1,
                is_shared=True,
                is_starter=is_starter,
                alert_threshold_count=None,
                created_at=updated_at,
                updated_at=updated_at,
            )
        )
        s.commit()


def _create_query(sql_text: str, *, title: str = "run me") -> str:
    row = sq.create(
        _factory(),
        owner_id=1,
        title=title,
        description=None,
        sql_text=sql_text,
    )
    return row["slug"]


# ---------------------------------------------------------------------
# make_slug — sanitiser edge that is NOT covered by lower()/truncation
# ---------------------------------------------------------------------


def test_make_slug_strips_leading_and_trailing_hyphens() -> None:
    # Title that sanitises to ``-hello-world-`` before the edge strip.
    # ``.strip("-")`` removes the boundary hyphens; a ``.strip(None)``
    # mutant (whitespace-only) would leave them on the slug base.
    slug = sq.make_slug("!!hello world!!")
    base = slug.rpartition("-")[0]
    assert base == "hello-world"
    assert not base.startswith("-")
    assert not base.endswith("-")


# ---------------------------------------------------------------------
# validate_sql — separator, cleaning, parse-error message, return value
# ---------------------------------------------------------------------


def test_validate_sql_joins_multiple_disallowed_tables_with_comma_space() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("SELECT * FROM secret_payroll JOIN hush_hush ON 1=1")
    msg = str(exc.value)
    # ``", ".join`` keeps a single comma-space; an ``"XX, XX"`` mutant
    # would inject the literal token between the two table names.
    assert "hush_hush, secret_payroll" in msg


def test_validate_sql_only_semicolon_reports_empty_not_parse_error() -> None:
    # ``.rstrip(";")`` reduces ``";"`` to ``""`` → the empty-text guard
    # fires.  A ``.rstrip(None)`` mutant keeps the ``";"`` and routes to
    # the parse-error branch instead, changing the message.
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql(";")
    assert str(exc.value) == "SQL text must not be empty"


def test_validate_sql_empty_string_reports_empty_not_parse_error() -> None:
    # ``(sql_text or "")`` keeps the cleaned text empty; an
    # ``(sql_text or "XXXX")`` mutant would parse ``"XXXX"`` and raise a
    # different message.
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("")
    assert str(exc.value) == "SQL text must not be empty"


def test_validate_sql_rejects_leading_semicolon_garbage() -> None:
    # ``.rstrip(";")`` leaves the leading ``;`` so the text fails to
    # parse.  An ``lstrip(";")`` mutant would strip the leading ``;``
    # and the SELECT would validate cleanly — observably different.
    with pytest.raises(ValidationError):
        sq.validate_sql(";SELECT id FROM audit_log")


def test_validate_sql_trailing_token_preserved_not_stripped() -> None:
    # ``.rstrip(";")`` leaves the trailing ``X`` token; an
    # ``.rstrip("X;")`` mutant strips it, truncating the predicate to
    # ``col = `` which no longer parses.
    assert sq.validate_sql("SELECT col FROM audit_log WHERE col = X") == {"audit_log"}


def test_validate_sql_parse_error_message_prefix() -> None:
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("SELECT FROM WHERE")
    # ``ValidationError(None)`` mutant would render ``"None"``.
    assert str(exc.value).startswith("Could not parse SQL")


# ---------------------------------------------------------------------
# serialize — exact key set (key-rename mutants)
# ---------------------------------------------------------------------


def test_serialize_has_exact_expected_keys() -> None:
    now = datetime.datetime(2024, 1, 2, 3, 4, 5, tzinfo=datetime.UTC)
    row = SavedAuditQuery(
        id=7,
        slug="s",
        title="t",
        description="d",
        sql_text="SELECT 1",
        owner_id=3,
        is_shared=True,
        is_starter=False,
        alert_threshold_count=2,
        created_at=now,
        updated_at=now,
    )
    out = sq.serialize(row)
    # Key-rename mutants (id→ID/XXidXX, created_at→CREATED_AT, …) all
    # change this exact key set.
    assert set(out.keys()) == {
        "id",
        "slug",
        "title",
        "description",
        "sql_text",
        "owner_id",
        "is_shared",
        "is_starter",
        "alert_threshold_count",
        "created_at",
        "updated_at",
    }
    assert out["id"] == 7
    assert out["created_at"] == now.isoformat()
    assert out["updated_at"] == now.isoformat()


# ---------------------------------------------------------------------
# create — flags, title cleaning, slug source, length cap
# ---------------------------------------------------------------------


def test_create_sets_shared_true_and_starter_false() -> None:
    result = sq.create(
        _factory(),
        owner_id=9,
        title="Flags",
        description=None,
        sql_text="SELECT * FROM audit_log",
    )
    # ``is_shared=None`` / ``is_starter=None`` mutants flip these.
    assert result["is_shared"] is True
    assert result["is_starter"] is False
    assert result["owner_id"] == 9


def test_create_empty_title_raises_validation() -> None:
    # ``(title or "").strip()`` keeps an empty title empty so the guard
    # fires; an ``(title or "XXXX")`` mutant would sneak past it.
    with pytest.raises(ValidationError) as exc:
        sq.create(
            _factory(),
            owner_id=1,
            title="",
            description=None,
            sql_text="SELECT * FROM audit_log",
        )
    assert str(exc.value) == "Title must not be empty"


def test_create_slug_is_derived_from_title() -> None:
    result = sq.create(
        _factory(),
        owner_id=1,
        title="Distinctive Title",
        description=None,
        sql_text="SELECT * FROM audit_log",
    )
    base = result["slug"].rpartition("-")[0]
    # ``make_slug(None)`` mutant would fall back to ``audit-query``.
    assert base == "distinctive-title"


def test_create_truncates_title_to_two_hundred_chars() -> None:
    long_title = "a" * 201
    result = sq.create(
        _factory(),
        owner_id=1,
        title=long_title,
        description=None,
        sql_text="SELECT * FROM audit_log",
    )
    # ``clean_title[:200]`` caps the stored title; a ``[:201]`` mutant
    # would keep all 201 characters.
    assert len(result["title"]) == 200


# ---------------------------------------------------------------------
# list_all — starters-first then most-recent ordering
# ---------------------------------------------------------------------


def test_list_all_orders_starters_before_newer_non_starters() -> None:
    base = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    # Starter is OLDER than the non-starter; starters-first must still
    # win.  Dropping the ``desc(is_starter)`` key would surface the
    # newer non-starter first.
    _insert_query(slug="starter-old", is_starter=True, updated_at=base)
    _insert_query(
        slug="user-new",
        is_starter=False,
        updated_at=base + datetime.timedelta(days=5),
    )
    rows = sq.list_all(_factory())
    assert rows[0]["slug"] == "starter-old"


# ---------------------------------------------------------------------
# list_paginated — ordering on the paginated path
# ---------------------------------------------------------------------


def test_list_paginated_orders_starters_before_newer_non_starters() -> None:
    base = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    _insert_query(slug="p-starter-old", is_starter=True, updated_at=base)
    _insert_query(
        slug="p-user-new",
        is_starter=False,
        updated_at=base + datetime.timedelta(days=5),
    )
    rows, _total = sq.list_paginated(_factory(), offset=0, limit=50)
    assert rows[0]["slug"] == "p-starter-old"


def test_list_orderings_tiebreak_by_updated_at_desc() -> None:
    """Within one ``is_starter`` tier, rows sort by ``updated_at`` descending.

    Pins the *secondary* ``desc(updated_at)`` ORDER BY key on both listing
    paths. The three rows share ``is_starter`` (so the primary key cannot
    disambiguate them) and are inserted out of date order, so dropping or
    nulling the secondary key — ``order_by(desc(is_starter), None)`` /
    ``desc(None)`` / the key removed — surfaces them in insertion order
    instead of newest-first.
    """
    base = datetime.datetime(2024, 1, 1, tzinfo=datetime.UTC)
    _insert_query(slug="tb-oldest", is_starter=False, updated_at=base)
    _insert_query(slug="tb-newest", is_starter=False, updated_at=base + datetime.timedelta(days=10))
    _insert_query(slug="tb-middle", is_starter=False, updated_at=base + datetime.timedelta(days=5))
    expected = ["tb-newest", "tb-middle", "tb-oldest"]

    def _relative_order(slugs: list[str]) -> list[str]:
        return [s for s in slugs if s in set(expected)]

    assert _relative_order([r["slug"] for r in sq.list_all(_factory())]) == expected
    page, _total = sq.list_paginated(_factory(), offset=0, limit=50)
    assert _relative_order([r["slug"] for r in page]) == expected


# ---------------------------------------------------------------------
# execute — row-cap boundary semantics
# ---------------------------------------------------------------------


def test_execute_zero_cap_means_no_truncation() -> None:
    _seed_saved_queries(3)
    slug = _create_query("SELECT id FROM saved_audit_queries")
    # ``row_cap > 0`` keeps ``row_cap=0`` in the "no cap" lane; a
    # ``row_cap >= 0`` mutant would slice to ``[:0]`` → empty + truncated.
    result = sq.execute(_factory(), slug, row_cap=0)
    assert result is not None
    assert result["truncated"] is False
    assert result["row_count"] >= 4  # 3 seeds + the query itself


def test_execute_cap_of_one_truncates_to_single_row() -> None:
    _seed_saved_queries(3)
    slug = _create_query("SELECT id FROM saved_audit_queries")
    # ``row_cap > 0`` applies the cap at 1; a ``row_cap > 1`` mutant
    # would treat 1 as "no cap" and return every row.
    result = sq.execute(_factory(), slug, row_cap=1)
    assert result is not None
    assert result["truncated"] is True
    assert result["row_count"] == 1


# ---------------------------------------------------------------------
# update — guard inversions, message, persisted values, lookup
# ---------------------------------------------------------------------


def _make_editable() -> str:
    row = sq.create(
        _factory(),
        owner_id=1,
        title="editable",
        description="orig desc",
        sql_text="SELECT * FROM audit_log",
        alert_threshold_count=3,
    )
    return row["slug"]


def test_update_applies_new_title() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, title="brand new title")
    assert out is not None
    # ``if title is not None`` gate + ``clean = title.strip()`` +
    # ``row.title = clean[:200]`` all participate in this write.
    assert out["title"] == "brand new title"


def test_update_empty_title_raises_with_message() -> None:
    slug = _make_editable()
    with pytest.raises(ValidationError) as exc:
        sq.update(_factory(), slug, title="   ")
    # ``if not clean`` guard + the exact message string.
    assert str(exc.value) == "Title must not be empty"


def test_update_title_truncated_to_two_hundred() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, title="b" * 201)
    assert out is not None
    # ``clean[:200]`` cap vs a ``[:201]`` mutant.
    assert len(out["title"]) == 200


def test_update_applies_new_description() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, description="  refreshed  ")
    assert out is not None
    # ``if description is not None`` gate + ``.strip() or None`` write;
    # ``= None`` / ``and None`` mutants would drop the value.
    assert out["description"] == "refreshed"


def test_update_empty_description_clears_to_none() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, description="   ")
    assert out is not None
    # ``description.strip() or None`` → empty string clears to None.
    assert out["description"] is None


def test_update_applies_new_sql_text() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, sql_text="  SELECT id FROM users  ")
    assert out is not None
    # ``if sql_text is not None`` gate + ``validate_sql(sql_text)`` +
    # ``row.sql_text = sql_text.strip()``.
    assert out["sql_text"] == "SELECT id FROM users"


def test_update_invalid_sql_rejected() -> None:
    slug = _make_editable()
    with pytest.raises(ValidationError):
        sq.update(_factory(), slug, sql_text="SELECT * FROM forbidden_table")


def test_update_default_sentinel_leaves_threshold_unchanged() -> None:
    slug = _make_editable()
    # No ``alert_threshold_count`` passed → sentinel path must be a
    # no-op.  A ``!= "__unchanged__"`` → ``==`` (or altered-sentinel)
    # mutant would enter the branch and crash on ``int("__unchanged__")``.
    out = sq.update(_factory(), slug, title="renamed only")
    assert out is not None
    assert out["alert_threshold_count"] == 3


def test_update_sets_integer_threshold() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, alert_threshold_count=11)
    assert out is not None
    # ``int(alert_threshold_count) if ... is not None else None`` write;
    # ``= None`` / ``int(None)`` / inverted-``is not None`` mutants break it.
    assert out["alert_threshold_count"] == 11


def test_update_clears_threshold_with_none() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, alert_threshold_count=None)
    assert out is not None
    assert out["alert_threshold_count"] is None


def test_update_existing_row_returns_serialised_dict() -> None:
    slug = _make_editable()
    out = sq.update(_factory(), slug, title="still here")
    # ``row = session.scalar(...)`` / ``session.refresh(row)`` /
    # ``serialize(row)`` mutants (None substitutions) would lose the row.
    assert out is not None
    assert out["slug"] == slug
    assert out["title"] == "still here"
    assert out["updated_at"] is not None


def test_update_unknown_slug_returns_none() -> None:
    _make_editable()
    # Only one (non-starter) row exists; a wrong slug must miss it.
    # ``.where(slug == slug)`` mutants (where(None) / slug != slug /
    # row=None / inverted ``row is None`` guard) change this.
    assert sq.update(_factory(), "no-such-slug", title="x") is None


def test_update_starter_row_refuses() -> None:
    sq.bootstrap_starter_rows(_factory())
    with _factory()() as s:
        starter = s.scalar(select(SavedAuditQuery).where(SavedAuditQuery.is_starter.is_(True)))
        assert starter is not None
        starter_slug = starter.slug
    # ``row.is_starter`` guard: starter rows refuse mutation → None.
    assert sq.update(_factory(), starter_slug, title="hijack") is None


def test_update_persists_to_db_not_just_returns() -> None:
    slug = _make_editable()
    sq.update(_factory(), slug, title="persisted")
    with _factory()() as s:
        row = s.scalar(select(SavedAuditQuery).where(SavedAuditQuery.slug == slug))
        assert row is not None
        # Guards the ``row.title = None`` / refresh mutants by reading
        # the committed value back independently.
        assert row.title == "persisted"
        assert row.updated_at is not None


# ---------------------------------------------------------------------
# bootstrap_starter_rows — idempotency, count, descriptions, flags
# ---------------------------------------------------------------------


def test_bootstrap_inserts_all_starter_rows() -> None:
    inserted = sq.bootstrap_starter_rows(_factory())
    # ``inserted += 1`` per row; ``= 1`` / ``-= 1`` / ``+= 2`` mutants
    # would not yield the true count.
    with _factory()() as s:
        actual = len(list(s.scalars(select(SavedAuditQuery))))
    assert inserted == actual
    assert inserted >= 5


def test_bootstrap_continues_past_preexisting_starter() -> None:
    # Pre-seed the SECOND starter spec so the loop hits an existing row
    # in the middle.  ``continue`` keeps seeding the rest; a ``break``
    # mutant would stop and skip every later spec.
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as s:
        s.add(
            SavedAuditQuery(
                slug="rollbacks-last-quarter",
                title="preexisting",
                description=None,
                sql_text="SELECT 1",
                owner_id=None,
                is_shared=True,
                is_starter=True,
                alert_threshold_count=None,
                created_at=now,
                updated_at=now,
            )
        )
        s.commit()
    inserted = sq.bootstrap_starter_rows(_factory())
    # 5 specs total, 1 already present → 4 new.
    assert inserted == 4
    with _factory()() as s:
        slugs = {r.slug for r in s.scalars(select(SavedAuditQuery))}
    # A later spec (3rd in the list) must have been inserted.
    assert "cost-gate-denials-this-week" in slugs


def test_bootstrap_idempotent_second_call_inserts_nothing() -> None:
    first = sq.bootstrap_starter_rows(_factory())
    second = sq.bootstrap_starter_rows(_factory())
    assert first >= 5
    assert second == 0


def test_bootstrap_rows_carry_description_title_and_flags() -> None:
    sq.bootstrap_starter_rows(_factory())
    with _factory()() as s:
        row = s.scalar(select(SavedAuditQuery).where(SavedAuditQuery.slug == "pii-writes-last-90d"))
        assert row is not None
        # ``description=None`` / ``spec.get(<wrong key>)`` mutants would
        # null the description; the starter spec ships a real one.
        assert row.description is not None
        assert row.description != ""
        # ``title=str(None)`` mutant would store the literal "None".
        assert row.title == "PII writes — last 90 days"
        # ``is_shared=None`` / ``is_shared=False`` mutants flip this.
        assert row.is_shared is True
        assert row.is_starter is True


# ---------------------------------------------------------------------
# validate_sql — the unnamed-table-node scan must not short-circuit
# ---------------------------------------------------------------------


def test_validate_sql_unnamed_table_node_does_not_skip_later_tables() -> None:
    # A table-valued function (``json_each(...)``) parses to a ``Table``
    # node whose ``.name`` is empty, and it sorts BEFORE the real table
    # in ``find_all`` order.  ``if not name: continue`` skips just that
    # node and keeps scanning, so the forbidden ``secret_table`` still
    # reaches the allow-list check and is rejected.  A ``break`` mutant
    # would abandon the scan at the empty node, never see the forbidden
    # table, and let the query validate clean.
    with pytest.raises(ValidationError) as exc:
        sq.validate_sql("SELECT * FROM json_each(payload) JOIN secret_table ON 1=1")
    assert "secret_table" in str(exc.value)
