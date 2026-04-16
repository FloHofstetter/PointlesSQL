"""Unit tests for the auth service."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pointlessql.models import Base, User
from pointlessql.services import auth


@pytest.fixture
def db_factory():
    """Create an in-memory SQLite database with the users table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


SECRET = "test-secret-key-for-unit-tests!!"  # 32+ bytes to suppress PyJWT warning


class TestPasswordHashing:
    """Password hash and verify round-trip."""

    def test_hash_and_verify(self):
        hashed = auth.hash_password("s3cret!")
        assert auth.verify_password("s3cret!", hashed)

    def test_wrong_password(self):
        hashed = auth.hash_password("correct")
        assert not auth.verify_password("wrong", hashed)

    def test_corrupt_hash(self):
        assert not auth.verify_password("anything", "not-a-hash")


class TestJWT:
    """JWT creation and verification."""

    def test_create_and_verify(self):
        token = auth.create_jwt(1, "a@b.com", True, SECRET)
        payload = auth.verify_jwt(token, SECRET)
        assert payload is not None
        assert payload["sub"] == "1"
        assert payload["email"] == "a@b.com"
        assert payload["is_admin"] is True

    def test_wrong_secret(self):
        token = auth.create_jwt(1, "a@b.com", False, SECRET)
        assert auth.verify_jwt(token, "wrong-secret") is None

    def test_expired_token(self):
        token = auth.create_jwt(1, "a@b.com", False, SECRET, expiry_hours=0)
        assert auth.verify_jwt(token, SECRET) is None

    def test_garbage_token(self):
        assert auth.verify_jwt("not.a.jwt", SECRET) is None


class TestRegister:
    """User registration."""

    def test_first_user_is_admin(self, db_factory):
        user = auth.register(db_factory, "admin@test.com", "Admin", "pass123")
        assert user is not None
        assert user.is_admin is True

    def test_second_user_is_not_admin(self, db_factory):
        auth.register(db_factory, "first@test.com", "First", "pass123")
        user = auth.register(db_factory, "second@test.com", "Second", "pass456")
        assert user is not None
        assert user.is_admin is False

    def test_duplicate_email_returns_none(self, db_factory):
        auth.register(db_factory, "dup@test.com", "One", "pass123")
        result = auth.register(db_factory, "dup@test.com", "Two", "pass456")
        assert result is None

    def test_email_normalized(self, db_factory):
        user = auth.register(db_factory, "  USER@Test.COM  ", "User", "pass123")
        assert user is not None
        assert user.email == "user@test.com"


class TestLogin:
    """Login and token generation."""

    def test_successful_login(self, db_factory):
        auth.register(db_factory, "user@test.com", "User", "pass123")
        token = auth.login(db_factory, "user@test.com", "pass123", SECRET)
        assert token is not None
        payload = auth.verify_jwt(token, SECRET)
        assert payload is not None
        assert payload["email"] == "user@test.com"

    def test_wrong_password_returns_none(self, db_factory):
        auth.register(db_factory, "user@test.com", "User", "pass123")
        assert auth.login(db_factory, "user@test.com", "wrong", SECRET) is None

    def test_nonexistent_user_returns_none(self, db_factory):
        assert auth.login(db_factory, "nobody@test.com", "pass", SECRET) is None


class TestGetCurrentUser:
    """Token-to-user resolution."""

    def test_valid_token(self, db_factory):
        auth.register(db_factory, "user@test.com", "The User", "pass123")
        token = auth.login(db_factory, "user@test.com", "pass123", SECRET)
        assert token is not None

        info = auth.get_current_user(db_factory, token, SECRET)
        assert info is not None
        assert info["email"] == "user@test.com"
        assert info["display_name"] == "The User"

    def test_invalid_token(self, db_factory):
        assert auth.get_current_user(db_factory, "bad-token", SECRET) is None

    def test_deleted_user(self, db_factory):
        user = auth.register(db_factory, "gone@test.com", "Gone", "pass123")
        token = auth.login(db_factory, "gone@test.com", "pass123", SECRET)
        assert token is not None

        # Delete the user from the DB.
        with db_factory() as session:
            row = session.query(User).filter(User.id == user.id).first()
            session.delete(row)
            session.commit()

        assert auth.get_current_user(db_factory, token, SECRET) is None
