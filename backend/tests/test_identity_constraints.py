"""
Database constraint tests for the identity models.

Isolation strategy: each test runs inside a transaction that is rolled
back at teardown by the db_session fixture. The alembic migration is
applied once per session by db_engine. The dev database is never touched.
"""

from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.identity import AuthSession, GitHubAccount, Profile, User

_FUTURE = datetime(2040, 1, 1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(github_user_id: int, github_login: str = "testuser", email: str | None = None) -> User:
    return User(github_user_id=github_user_id, github_login=github_login, email=email)


def _profile(user_id, slug: str, status: str = "PRIVATE") -> Profile:
    return Profile(user_id=user_id, slug=slug, status=status)


def _auth_session(user_id, token_hash: str) -> AuthSession:
    return AuthSession(user_id=user_id, token_hash=token_hash, expires_at=_FUTURE)


# ---------------------------------------------------------------------------
# Migration sanity
# ---------------------------------------------------------------------------


def test_migration_creates_expected_tables(db_engine):
    from sqlalchemy import inspect

    inspector = inspect(db_engine)
    table_names = inspector.get_table_names()
    for expected in ("users", "github_accounts", "profiles", "auth_sessions"):
        assert expected in table_names, f"Table '{expected}' missing after migration"


# ---------------------------------------------------------------------------
# Unique constraints
# ---------------------------------------------------------------------------


def test_user_github_user_id_unique(db_session):
    db_session.add(_user(10001))
    db_session.flush()

    db_session.add(_user(10001, github_login="other"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_profile_slug_unique(db_session):
    u1 = _user(20001)
    u2 = _user(20002)
    db_session.add_all([u1, u2])
    db_session.flush()

    db_session.add(_profile(u1.id, "alice"))
    db_session.flush()

    db_session.add(_profile(u2.id, "alice"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_auth_session_token_hash_unique(db_session):
    u = _user(30001)
    db_session.add(u)
    db_session.flush()

    db_session.add(_auth_session(u.id, "a" * 64))
    db_session.flush()

    db_session.add(_auth_session(u.id, "a" * 64))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# 1:1 profile per user
# ---------------------------------------------------------------------------


def test_profile_one_per_user(db_session):
    u = _user(40001)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "user-one"))
    db_session.flush()

    db_session.add(_profile(u.id, "user-one-duplicate"))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# Profile status CHECK
# ---------------------------------------------------------------------------


def test_profile_status_invalid_rejected(db_session):
    u = _user(50001)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "status-bad", status="ACTIVE"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_profile_status_private_accepted(db_session):
    u = _user(50002)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "status-ok-priv", status="PRIVATE"))
    db_session.flush()  # must not raise


def test_profile_status_published_accepted(db_session):
    u = _user(50003)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "status-ok-pub", status="PUBLISHED"))
    db_session.flush()  # must not raise


# ---------------------------------------------------------------------------
# email nullable and non-unique
# ---------------------------------------------------------------------------


def test_email_nullable(db_session):
    u = _user(60001, email=None)
    db_session.add(u)
    db_session.flush()  # must not raise


def test_email_allows_duplicates(db_session):
    u1 = _user(60002, github_login="dup1", email="shared@example.com")
    u2 = _user(60003, github_login="dup2", email="shared@example.com")
    db_session.add_all([u1, u2])
    db_session.flush()  # must not raise


# ---------------------------------------------------------------------------
# Profile slug format CHECK — boundary tests
# ---------------------------------------------------------------------------


def test_slug_length_2_rejected(db_session):
    u = _user(70001)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "ab"))  # 2 chars — below minimum
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_slug_length_3_accepted(db_session):
    u = _user(70002)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "abc"))  # 3 chars — minimum
    db_session.flush()  # must not raise


def test_slug_length_39_accepted(db_session):
    u = _user(70003)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "a" * 39))  # 39 chars — maximum
    db_session.flush()  # must not raise


def test_slug_length_40_rejected(db_session):
    from sqlalchemy.exc import DatabaseError

    u = _user(70004)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "a" * 40))  # 40 chars — above maximum
    # VARCHAR(39) raises DataError (truncation) before the CHECK constraint fires;
    # DatabaseError covers both DataError and IntegrityError.
    with pytest.raises(DatabaseError):
        db_session.flush()


def test_slug_leading_hyphen_rejected(db_session):
    u = _user(70005)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "-abc"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_slug_trailing_hyphen_rejected(db_session):
    u = _user(70006)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "abc-"))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_slug_uppercase_rejected(db_session):
    u = _user(70007)
    db_session.add(u)
    db_session.flush()

    db_session.add(_profile(u.id, "Alice"))
    with pytest.raises(IntegrityError):
        db_session.flush()


# ---------------------------------------------------------------------------
# ON DELETE CASCADE
# ---------------------------------------------------------------------------


def test_cascade_delete_user_removes_dependents(db_session):
    """
    Deletes a user via raw SQL (bypassing ORM cascade) to verify the DB-level
    ON DELETE CASCADE on github_accounts, profiles, and auth_sessions.
    """
    u = _user(80001, github_login="cascade-user")
    db_session.add(u)
    db_session.flush()

    profile = _profile(u.id, "cascade-user")
    auth_s = _auth_session(u.id, "b" * 64)
    gh_acc = GitHubAccount(user_id=u.id)
    db_session.add_all([profile, auth_s, gh_acc])
    db_session.flush()

    user_id_str = str(u.id)

    # Raw SQL DELETE — bypasses ORM cascade, tests DB-level constraint
    db_session.execute(
        text("DELETE FROM users WHERE id = CAST(:id AS UUID)"),
        {"id": user_id_str},
    )

    for table, col in (
        ("profiles", "user_id"),
        ("auth_sessions", "user_id"),
        ("github_accounts", "user_id"),
    ):
        count = db_session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {col} = CAST(:id AS UUID)"),  # noqa: S608
            {"id": user_id_str},
        ).scalar()
        assert count == 0, f"Expected {table} rows to be CASCADE-deleted, found {count}"
