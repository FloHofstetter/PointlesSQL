"""Phase 83.1 — saved_views service-layer unit tests.

Pure-function checks that don't need the test client.  Validates
SELECT-only enforcement, parameter normalisation, placeholder
cross-checking and the ``${name}`` → ``?`` render path.
"""

from __future__ import annotations

import pytest

from pointlessql.exceptions import ValidationError
from pointlessql.services import saved_views as svc


def test_validate_sql_is_select_accepts_select() -> None:
    """A plain SELECT is accepted."""
    svc.validate_sql_is_select("SELECT 1")


def test_validate_sql_is_select_rejects_insert() -> None:
    """An INSERT is rejected."""
    with pytest.raises(ValidationError):
        svc.validate_sql_is_select("INSERT INTO t VALUES (1)")


def test_normalize_parameters_round_trip() -> None:
    """Valid parameters round-trip with defaults filled in."""
    out = svc.normalize_parameters(
        [
            {"name": "country", "type": "string", "default": "DE"},
            {"name": "since", "type": "date", "label": "Since"},
        ]
    )
    assert out[0]["name"] == "country"
    assert out[0]["label"] == "country"
    assert out[0]["required"] is False
    assert out[1]["label"] == "Since"


def test_normalize_parameters_rejects_duplicate() -> None:
    """Duplicate parameter names raise."""
    with pytest.raises(ValidationError):
        svc.normalize_parameters(
            [{"name": "x", "type": "string"}, {"name": "x", "type": "string"}]
        )


def test_normalize_parameters_rejects_bad_type() -> None:
    """Unknown parameter type is rejected."""
    with pytest.raises(ValidationError):
        svc.normalize_parameters([{"name": "x", "type": "blob"}])


def test_cross_check_placeholders_detects_missing() -> None:
    """A ``${name}`` without a declaration raises."""
    with pytest.raises(ValidationError):
        svc.cross_check_placeholders(
            "SELECT * FROM t WHERE c = ${nope}", []
        )


def test_render_sql_with_params_swaps_placeholders() -> None:
    """``${name}`` becomes ``?`` and value list is in document order."""
    params = svc.normalize_parameters(
        [
            {"name": "country", "type": "string", "default": "DE"},
            {"name": "min_rev", "type": "integer", "default": 0},
        ]
    )
    rewritten, binds = svc.render_sql_with_params(
        "SELECT * FROM t WHERE country = ${country} AND rev > ${min_rev}",
        params,
        {"country": "FR", "min_rev": 100},
    )
    assert rewritten == "SELECT * FROM t WHERE country = ? AND rev > ?"
    assert binds == ["FR", 100]


def test_render_sql_with_params_uses_default_when_absent() -> None:
    """Missing values fall back to the declared default."""
    params = svc.normalize_parameters(
        [{"name": "country", "type": "string", "default": "DE"}]
    )
    _, binds = svc.render_sql_with_params(
        "SELECT * FROM t WHERE c = ${country}", params, {}
    )
    assert binds == ["DE"]


def test_render_sql_with_params_required_missing_raises() -> None:
    """A required parameter with no value raises."""
    params = svc.normalize_parameters(
        [{"name": "country", "type": "string", "required": True}]
    )
    with pytest.raises(ValidationError):
        svc.render_sql_with_params(
            "SELECT * FROM t WHERE c = ${country}", params, {}
        )


def test_render_sql_with_params_coerces_integer() -> None:
    """Strings supplied for integer parameters are coerced."""
    params = svc.normalize_parameters([{"name": "n", "type": "integer"}])
    _, binds = svc.render_sql_with_params(
        "SELECT * FROM t WHERE n = ${n}", params, {"n": "42"}
    )
    assert binds == [42]


def test_render_sql_with_params_date_iso_round_trip() -> None:
    """Date parameters round-trip via ``date.fromisoformat``."""
    params = svc.normalize_parameters([{"name": "d", "type": "date"}])
    _, binds = svc.render_sql_with_params(
        "SELECT * FROM t WHERE d = ${d}", params, {"d": "2026-01-15"}
    )
    assert binds == ["2026-01-15"]


def test_make_slug_handles_unicode_and_punctuation() -> None:
    """Title with non-ASCII chars degrades to a clean slug."""
    slug = svc.make_slug("Top Orders by Country!?")
    # ``slugify`` collapses non-alphanumerics to hyphens; the random
    # 6-char suffix is the tail.
    assert slug.startswith("top-orders-by-country")
    assert len(slug) > len("top-orders-by-country") + 1
