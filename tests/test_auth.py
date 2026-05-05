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


class TestJwtKeyRotation:
    """Sprint-46 grace-window fallback to a previous signing key."""

    _OLD_KEY = "previous-test-secret-key-32-bytes"
    _NEW_KEY = "rotated-test-secret-key-32-bytes!"

    def test_previous_key_verifies_token_after_rotation(self):
        """Token signed with the old key verifies under the new+previous combo."""
        legacy = auth.create_jwt(7, "a@b.com", False, self._OLD_KEY)
        payload = auth.verify_jwt(legacy, self._NEW_KEY, previous_key=self._OLD_KEY)
        assert payload is not None
        assert payload["sub"] == "7"

    def test_new_key_still_verifies_fresh_tokens(self):
        """Tokens signed with the primary key keep working during rotation."""
        fresh = auth.create_jwt(8, "b@b.com", True, self._NEW_KEY)
        payload = auth.verify_jwt(fresh, self._NEW_KEY, previous_key=self._OLD_KEY)
        assert payload is not None
        assert payload["sub"] == "8"
        assert payload["is_admin"] is True

    def test_rotation_rejects_unknown_key(self):
        """A token signed with a third key still fails both current and previous."""
        foreign = auth.create_jwt(9, "c@b.com", False, "some-other-32-byte-key-here!!!!!")
        assert auth.verify_jwt(foreign, self._NEW_KEY, previous_key=self._OLD_KEY) is None

    def test_without_previous_key_old_tokens_fail(self):
        """Without the grace window, a changed primary key invalidates old tokens."""
        legacy = auth.create_jwt(10, "d@b.com", False, self._OLD_KEY)
        assert auth.verify_jwt(legacy, self._NEW_KEY) is None

    def test_previous_key_does_not_bypass_expiry(self):
        """Expired tokens signed with the previous key still fail."""
        expired = auth.create_jwt(11, "e@b.com", False, self._OLD_KEY, expiry_hours=0)
        assert auth.verify_jwt(expired, self._NEW_KEY, previous_key=self._OLD_KEY) is None

    def test_get_current_user_threads_previous_key(self, db_factory):
        """``get_current_user`` forwards ``previous_key`` into ``verify_jwt``."""
        user = auth.register(db_factory, "r@b.com", "Rotator", "pass1234")
        assert user is not None
        legacy = auth.create_jwt(user.id, user.email, user.is_admin, self._OLD_KEY)
        info = auth.get_current_user(db_factory, legacy, self._NEW_KEY, previous_key=self._OLD_KEY)
        assert info is not None
        assert info["email"] == "r@b.com"


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
