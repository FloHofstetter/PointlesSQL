"""Tests for ``PointlessSQLError.not_found`` + ``BadRequestError``.

The classmethod composes a uniformly-formatted message from optional
``where``/``alternatives``/``hint`` pieces; the subclass is the
single 400-shape for semantic-but-not-schema rejects.  Coverage
matrix below maps each branch of the helper to one explicit test so
future edits can't regress the format silently — downstream code in
route packages relies on the exact phrasing for human readability.
"""

from __future__ import annotations

import pytest

from pointlessql.exceptions import (
    BadRequestError,
    CatalogNotFoundError,
    PointlessSQLError,
    ResourceNotFoundError,
)
from pointlessql.types import ErrorCode


class TestNotFoundHelper:
    def test_bare_what(self) -> None:
        exc = PointlessSQLError.not_found(what="Catalog 'foo'")
        assert str(exc) == "Catalog 'foo' not found."
        assert exc.detail == "Catalog 'foo' not found."

    def test_what_plus_where(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Catalog 'foo'", where="in workspace 'default'"
        )
        assert str(exc) == "Catalog 'foo' not found in workspace 'default'."

    def test_alternatives_under_five(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Topic 'x'", alternatives=["b", "a", "c"]
        )
        # Alternatives are sorted for deterministic output.
        assert str(exc) == "Topic 'x' not found. Available: a, b, c."

    def test_alternatives_over_five_truncates(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Topic 'x'", alternatives=list("ghijfedcba")  # 10 items
        )
        # First 5 sorted entries + tail counter.
        assert str(exc) == "Topic 'x' not found. Available: a, b, c, d, e (+5 more)."

    def test_hint_only(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Catalog 'foo'", hint="Run `pql catalog ls`."
        )
        assert str(exc) == "Catalog 'foo' not found. Run `pql catalog ls`."

    def test_alternatives_plus_hint(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Topic 'x'",
            alternatives=["a", "b"],
            hint="See /topics.",
        )
        assert str(exc) == "Topic 'x' not found. Available: a, b. See /topics."

    def test_full_combination(self) -> None:
        exc = PointlessSQLError.not_found(
            what="Catalog 'foo'",
            where="in workspace 'default'",
            alternatives=["bar", "baz"],
            hint="Run `pql catalog ls`.",
        )
        assert str(exc) == (
            "Catalog 'foo' not found in workspace 'default'. "
            "Available: bar, baz. Run `pql catalog ls`."
        )

    def test_subclass_dispatch_resource(self) -> None:
        exc = ResourceNotFoundError.not_found(what="Run 42")
        assert isinstance(exc, ResourceNotFoundError)
        assert exc.status_code == 404
        assert exc.error_code == ErrorCode.RESOURCE_NOT_FOUND

    def test_subclass_dispatch_catalog(self) -> None:
        exc = CatalogNotFoundError.not_found(
            what="Schema 'main.bronze'", hint="Check with `pql schema ls main`."
        )
        assert isinstance(exc, CatalogNotFoundError)
        assert exc.status_code == 404
        assert exc.error_code == ErrorCode.CATALOG_NOT_FOUND


class TestBadRequestError:
    def test_class_attributes(self) -> None:
        assert BadRequestError.status_code == 400
        assert BadRequestError.error_code == ErrorCode.BAD_REQUEST

    def test_instance_inherits_base(self) -> None:
        exc = BadRequestError("webhook_url is required")
        assert isinstance(exc, PointlessSQLError)
        assert exc.detail == "webhook_url is required"
        assert exc.status_code == 400
        assert exc.error_code == "bad_request"

    def test_not_value_error(self) -> None:
        # ValidationError keeps the ValueError mixin for the 422
        # path; BadRequestError is a deliberate 400 that should not
        # be caught by legacy ``except ValueError`` guards.
        assert not issubclass(BadRequestError, ValueError)

    def test_raises_through_central_handler(self) -> None:
        # Sanity: the exception subclasses PointlessSQLError so the
        # global ``@app.exception_handler(PointlessSQLError)`` in
        # ``api/error_handlers.py`` automatically wraps it in RFC
        # 9457 problem+json without any new handler registration.
        with pytest.raises(PointlessSQLError):
            raise BadRequestError("nope")
