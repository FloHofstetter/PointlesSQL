"""Tests for the domain exception hierarchy."""

from __future__ import annotations

import pytest

from pointlessql.exceptions import (
    AuthenticationError,
    AuthorizationError,
    CatalogNotFoundError,
    CatalogUnavailableError,
    EngineError,
    PointlessSQLError,
    ValidationError,
)


class TestHierarchy:
    @pytest.mark.parametrize(
        "exc_cls",
        [
            CatalogUnavailableError,
            CatalogNotFoundError,
            AuthenticationError,
            AuthorizationError,
            EngineError,
            ValidationError,
        ],
    )
    def test_all_inherit_from_base(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, PointlessSQLError)

    def test_validation_error_is_value_error(self) -> None:
        assert issubclass(ValidationError, ValueError)

    def test_authorization_error_not_value_error(self) -> None:
        assert not issubclass(AuthorizationError, ValueError)


class TestAttributes:
    def test_base_attributes(self) -> None:
        exc = CatalogUnavailableError("server down")
        assert exc.status_code == 502
        assert exc.error_code == "catalog_unavailable"
        assert exc.detail == "server down"
        assert str(exc) == "server down"

    def test_not_found_attributes(self) -> None:
        exc = CatalogNotFoundError("table x not found")
        assert exc.status_code == 404
        assert exc.error_code == "catalog_not_found"

    def test_authentication_attributes(self) -> None:
        exc = AuthenticationError("token expired")
        assert exc.status_code == 401
        assert exc.error_code == "authentication_error"

    def test_authorization_attributes(self) -> None:
        exc = AuthorizationError("alice", "SELECT", "table", "cat.sch.tbl")
        assert exc.status_code == 403
        assert exc.error_code == "authorization_error"
        assert exc.principal == "alice"
        assert exc.privilege == "SELECT"
        assert exc.securable_type == "table"
        assert exc.full_name == "cat.sch.tbl"
        assert "alice lacks SELECT" in str(exc)

    def test_engine_error_attributes(self) -> None:
        exc = EngineError("read failed")
        assert exc.status_code == 500
        assert exc.error_code == "engine_error"

    def test_validation_error_attributes(self) -> None:
        exc = ValidationError("bad name")
        assert exc.status_code == 422
        assert exc.error_code == "validation_error"


class TestCatchability:
    def test_catch_base_catches_all(self) -> None:
        with pytest.raises(PointlessSQLError):
            raise CatalogUnavailableError("down")

    def test_catch_value_error_catches_validation(self) -> None:
        with pytest.raises(ValueError):
            raise ValidationError("bad input")

    def test_authorization_backward_compat(self) -> None:
        from pointlessql.services.authorization import AccessDenied

        assert AccessDenied is AuthorizationError
