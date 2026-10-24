"""
Auth flow tests: slug generation, service layer, and HTTP endpoints.

DB-dependent tests (class TestServiceDB, TestSessionLifecycle, TestCallbackHTTP,
TestMeHTTP, TestLogoutHTTP) are skipped automatically when PostgreSQL is not
available (they depend on db_session which depends on db_engine).
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.identity.github_client import GitHubOAuthClient
from app.identity.service import (
    _find_user_by_github_id,
    _generate_base_slug,
    _slug_with_random_suffix,
    create_session,
    delete_session,
    get_or_create_user,
    get_session_user,
    get_user_profile,
    hash_token,
    update_user_fields,
)
from app.models.identity import AuthSession
from tests.conftest import HTTPS_BASE_URL

# ---------------------------------------------------------------------------
# Slug generation — no DB, no network
# ---------------------------------------------------------------------------


class TestGenerateBaseSlug:
    def test_lowercase_passthrough(self):
        assert _generate_base_slug("alice") == "alice"

    def test_uppercased_normalized(self):
        assert _generate_base_slug("Alice") == "alice"

    def test_dots_become_hyphens(self):
        assert _generate_base_slug("alice.wonder") == "alice-wonder"

    def test_multi_hyphens_collapsed(self):
        assert _generate_base_slug("alice---bob") == "alice-bob"

    def test_leading_trailing_hyphens_stripped(self):
        slug = _generate_base_slug("-alice-")
        assert not slug.startswith("-") and not slug.endswith("-")

    def test_reserved_word_gets_suffix(self):
        assert _generate_base_slug("admin") == "admin-0"

    def test_reserved_word_me(self):
        slug = _generate_base_slug("me")
        assert slug not in {"me"}
        assert slug.startswith("me")

    def test_short_slug_padded_to_min(self):
        slug = _generate_base_slug("ab")
        assert len(slug) >= 3

    def test_long_slug_truncated_to_max(self):
        slug = _generate_base_slug("a" * 60)
        assert len(slug) <= 39

    def test_slug_does_not_end_with_hyphen_after_truncation(self):
        slug = _generate_base_slug("a" * 38 + "-b")
        assert not slug.endswith("-")


class TestSlugWithRandomSuffix:
    def test_length_within_limit(self):
        base = "a" * 39
        assert len(_slug_with_random_suffix(base)) <= 39

    def test_suffix_appended(self):
        slug = _slug_with_random_suffix("alice")
        assert slug.startswith("alice-")
        assert len(slug) > len("alice")

    def test_randomness(self):
        slugs = {_slug_with_random_suffix("alice") for _ in range(20)}
        assert len(slugs) > 1


class TestHashToken:
    def test_deterministic(self):
        assert hash_token("foo") == hash_token("foo")

    def test_different_inputs_differ(self):
        assert hash_token("foo") != hash_token("bar")

    def test_sha256_length(self):
        assert len(hash_token("x")) == 64


# ---------------------------------------------------------------------------
# Service — DB tests
# ---------------------------------------------------------------------------


class TestGetOrCreateUser:
    def test_new_user_is_created(self, db_session):
        user, is_new = get_or_create_user(db_session, 1001, "alice", "alice@example.com")
        assert is_new is True
        assert user.github_user_id == 1001
        assert user.github_login == "alice"
        assert user.email == "alice@example.com"

    def test_new_user_has_profile(self, db_session):
        user, _ = get_or_create_user(db_session, 1002, "alice2", None)
        profile = get_user_profile(db_session, user.id)
        assert profile is not None
        assert len(profile.slug) >= 3
        assert profile.status == "PRIVATE"

    def test_new_user_has_github_account(self, db_session):
        user, _ = get_or_create_user(db_session, 1003, "alice3", None)
        assert user.github_account is not None

    def test_null_email_allowed(self, db_session):
        user, is_new = get_or_create_user(db_session, 1004, "alice4", None)
        assert is_new is True
        assert user.email is None

    def test_race_condition_returns_existing_user(self, db_session):
        """
        Calling get_or_create_user twice with the same github_user_id exercises the
        IntegrityError branch: the second flush violates the UNIQUE constraint on
        github_user_id, the SAVEPOINT is rolled back, _find_user_by_github_id finds
        the previously flushed user, and (user, False) is returned.
        """
        user1, is_new1 = get_or_create_user(db_session, 2001, "bob", "bob@example.com")
        assert is_new1 is True

        user2, is_new2 = get_or_create_user(db_session, 2001, "bob", "bob@example.com")
        assert is_new2 is False
        assert user2.id == user1.id

    def test_slug_conflict_triggers_retry(self, db_session):
        """
        Two different github users with the same login produce a slug conflict on
        attempt 0. The second call retries with a random suffix and succeeds.
        """
        user1, _ = get_or_create_user(db_session, 3001, "carol", None)
        user2, is_new = get_or_create_user(db_session, 3002, "carol", None)
        assert is_new is True
        assert user2.id != user1.id
        # slugs must differ
        p1 = get_user_profile(db_session, user1.id)
        p2 = get_user_profile(db_session, user2.id)
        assert p1 is not None and p2 is not None
        assert p1.slug != p2.slug


class TestUpdateUserFields:
    def test_login_and_email_updated(self, db_session):
        user, _ = get_or_create_user(db_session, 4001, "dave", "dave@example.com")
        update_user_fields(db_session, user, "dave-renamed", "new@example.com")
        assert user.github_login == "dave-renamed"
        assert user.email == "new@example.com"

    def test_profile_slug_unchanged_after_update(self, db_session):
        user, _ = get_or_create_user(db_session, 4002, "eve", None)
        profile_before = get_user_profile(db_session, user.id)
        assert profile_before is not None
        slug_before = profile_before.slug

        update_user_fields(db_session, user, "eve-renamed", None)

        profile_after = get_user_profile(db_session, user.id)
        assert profile_after is not None
        assert profile_after.slug == slug_before


class TestSessionLifecycle:
    def test_create_returns_raw_token(self, db_session):
        user, _ = get_or_create_user(db_session, 5001, "frank", None)
        token = create_session(db_session, user.id)
        assert isinstance(token, str) and len(token) > 20

    def test_get_session_user_valid_token(self, db_session):
        user, _ = get_or_create_user(db_session, 5002, "grace", None)
        token = create_session(db_session, user.id)
        found = get_session_user(db_session, token)
        assert found is not None
        assert found.id == user.id

    def test_get_session_user_wrong_token(self, db_session):
        assert get_session_user(db_session, "notarealtoken") is None

    def test_get_session_user_expired(self, db_session):
        user, _ = get_or_create_user(db_session, 5003, "heidi", None)
        token = create_session(db_session, user.id)

        # Manually expire the session
        token_hash = hash_token(token)
        from sqlalchemy import select
        session_row = db_session.execute(
            select(AuthSession).where(AuthSession.token_hash == token_hash)
        ).scalar_one()
        session_row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
        db_session.flush()

        assert get_session_user(db_session, token) is None

    def test_delete_session(self, db_session):
        user, _ = get_or_create_user(db_session, 5004, "ivan", None)
        token = create_session(db_session, user.id)
        delete_session(db_session, token)
        assert get_session_user(db_session, token) is None

    def test_delete_nonexistent_session_is_noop(self, db_session):
        delete_session(db_session, "ghost_token")  # must not raise


# ---------------------------------------------------------------------------
# HTTP endpoints — no DB (login only)
# ---------------------------------------------------------------------------


@pytest.fixture
def bare_client():
    """TestClient with real app but no DB or GitHub overrides."""
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app, base_url=HTTPS_BASE_URL, follow_redirects=False)


class TestLoginEndpoint:
    def test_redirects_to_github(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/login")
        assert resp.status_code == 302
        location = resp.headers["location"]
        assert "github.com/login/oauth/authorize" in location

    def test_redirect_contains_client_id(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/login")
        assert "client_id=" in resp.headers["location"]

    def test_state_cookie_is_set(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/login")
        assert "oauth_state" in resp.cookies

    def test_state_cookie_is_httponly(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/login")
        raw = resp.headers.get("set-cookie", "")
        assert "HttpOnly" in raw or "httponly" in raw.lower()


# ---------------------------------------------------------------------------
# HTTP endpoints — with DB + GitHub mock (auth_client fixture)
# ---------------------------------------------------------------------------


class TestCallbackEndpoint:
    def test_access_denied_returns_400(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/callback?error=access_denied")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "ACCESS_DENIED"

    def test_missing_state_returns_400(self, bare_client):
        resp = bare_client.get("/api/v1/auth/github/callback?code=abc")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"]["code"] == "INVALID_STATE"

    def test_state_mismatch_returns_400(self, bare_client):
        bare_client.cookies.set("oauth_state", "correct_state")
        resp = bare_client.get("/api/v1/auth/github/callback?code=abc&state=wrong")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "INVALID_STATE"

    def test_github_code_error_returns_400(self, db_session):
        """bad_verification_code from GitHub → OAUTH_CODE_INVALID (400)."""
        from fastapi.testclient import TestClient

        from app.dependencies import get_db
        from app.identity.github_client import get_github_client
        from app.main import app
        from tests.conftest import make_github_transport

        transport = make_github_transport(code_error="bad_verification_code")
        mock_client = GitHubOAuthClient(httpx.Client(transport=transport))

        app.dependency_overrides[get_db] = lambda: (yield db_session)
        app.dependency_overrides[get_github_client] = lambda: (yield mock_client)

        try:
            with TestClient(app, base_url=HTTPS_BASE_URL, follow_redirects=False) as client:
                # Set cookie directly on client to avoid per-request cookies= deprecation
                client.cookies.set("oauth_state", "s")
                resp = client.get("/api/v1/auth/github/callback?code=bad&state=s")
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "OAUTH_CODE_INVALID"

    def test_success_redirects_to_frontend(self, auth_client):
        # Login sets oauth_state cookie in the client jar; callback reads from jar.
        login_resp = auth_client.get("/api/v1/auth/github/login")
        state = login_resp.cookies["oauth_state"]

        resp = auth_client.get(f"/api/v1/auth/github/callback?code=good_code&state={state}")
        assert resp.status_code == 302
        assert "localhost:3000" in resp.headers["location"]

    def test_success_sets_session_cookie(self, auth_client):
        login_resp = auth_client.get("/api/v1/auth/github/login")
        state = login_resp.cookies["oauth_state"]

        resp = auth_client.get(f"/api/v1/auth/github/callback?code=good_code&state={state}")
        assert resp.status_code == 302
        assert "session" in resp.cookies

    def test_success_clears_state_cookie(self, auth_client):
        login_resp = auth_client.get("/api/v1/auth/github/login")
        state = login_resp.cookies["oauth_state"]

        resp = auth_client.get(f"/api/v1/auth/github/callback?code=good_code&state={state}")
        # State cookie must be deleted (Max-Age=0)
        raw = resp.headers.get("set-cookie", "")
        assert "oauth_state" in raw
        assert "Max-Age=0" in raw or "max-age=0" in raw.lower()

    def test_repeat_login_updates_login_field(self, db_session):
        """On second login the github_login field is updated, slug is unchanged."""
        from fastapi.testclient import TestClient

        from app.dependencies import get_db
        from app.identity.github_client import get_github_client
        from app.main import app
        from tests.conftest import make_github_transport

        def _do_login(github_login: str) -> None:
            transport = make_github_transport(
                github_user_id=9001, github_login=github_login
            )
            mock = GitHubOAuthClient(httpx.Client(transport=transport))
            app.dependency_overrides[get_db] = lambda: (yield db_session)
            app.dependency_overrides[get_github_client] = lambda: (yield mock)
            try:
                with TestClient(app, base_url=HTTPS_BASE_URL, follow_redirects=False) as c:
                    lr = c.get("/api/v1/auth/github/login")
                    state = lr.cookies["oauth_state"]
                    c.get(f"/api/v1/auth/github/callback?code=x&state={state}")
            finally:
                app.dependency_overrides.clear()

        _do_login("original")

        user = _find_user_by_github_id(db_session, 9001)
        assert user is not None
        profile1 = get_user_profile(db_session, user.id)
        assert profile1 is not None
        slug_before = profile1.slug

        _do_login("renamed")

        db_session.expire_all()
        user_after = _find_user_by_github_id(db_session, 9001)
        assert user_after is not None
        assert user_after.github_login == "renamed"

        profile2 = get_user_profile(db_session, user_after.id)
        assert profile2 is not None
        assert profile2.slug == slug_before


class TestMeEndpoint:
    def test_unauthenticated_returns_401(self, auth_client):
        resp = auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "UNAUTHORIZED"

    def test_authenticated_returns_user_data(self, auth_client, db_session):
        # Login flow: oauth_state cookie goes into jar, session cookie comes back.
        lr = auth_client.get("/api/v1/auth/github/login")
        state = lr.cookies["oauth_state"]
        cb = auth_client.get(f"/api/v1/auth/github/callback?code=c&state={state}")
        assert "session" in cb.cookies  # verify session cookie was issued

        # Jar sends session cookie automatically.
        resp = auth_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["github_login"] == "testuser"
        assert body["profile_slug"] is not None


class TestLogoutEndpoint:
    def test_logout_returns_204(self, auth_client):
        resp = auth_client.post("/api/v1/auth/logout")
        assert resp.status_code == 204

    def test_logout_clears_session_cookie(self, auth_client):
        resp = auth_client.post("/api/v1/auth/logout")
        raw = resp.headers.get("set-cookie", "")
        assert "session" in raw
        assert "Max-Age=0" in raw or "max-age=0" in raw.lower()

    def test_logout_after_login_invalidates_session(self, auth_client, db_session):
        # Login — jar picks up session cookie automatically.
        lr = auth_client.get("/api/v1/auth/github/login")
        state = lr.cookies["oauth_state"]
        cb = auth_client.get(f"/api/v1/auth/github/callback?code=c&state={state}")
        assert "session" in cb.cookies

        # Verify we can reach /me (jar sends session cookie).
        me_resp = auth_client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200

        # Logout — server responds with Max-Age=0, client removes cookie from jar.
        auth_client.post("/api/v1/auth/logout")

        # /me should now return 401 (session cookie gone from jar).
        me_after = auth_client.get("/api/v1/auth/me")
        assert me_after.status_code == 401
