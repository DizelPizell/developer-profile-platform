"""Profile editing, publication, public profile and avatar."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models.identity import GitHubAccount, Profile, User
from tests.conftest import login, make_github_transport

PROFILE = "/api/v1/profile"
PUBLISH = "/api/v1/profile/publish"
UNPUBLISH = "/api/v1/profile/unpublish"
PUBLIC = "/api/v1/public/profiles"

LIMITS = {"display_name": 100, "headline": 160, "bio": 2000, "location": 100}
PUBLIC_KEYS = {"slug", "display_name", "headline", "bio", "location", "avatar_url", "github_login"}


def _error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert error["code"] == code
    return error


def _field_errors(resp) -> list[dict]:
    return _error(resp, 422, "VALIDATION_ERROR")["details"]["fields"]


def _profile_row(db_session, github_user_id: int) -> Profile:
    return db_session.execute(
        select(Profile).join(User).where(User.github_user_id == github_user_id)
    ).scalar_one()


def _publishable(client) -> dict:
    resp = client.patch(PROFILE, json={"display_name": "Ann Dev", "headline": "Backend developer"})
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
def client(auth_client):
    login(auth_client)
    return auth_client


# ---------------------------------------------------------------------------
# GET / PATCH /profile
# ---------------------------------------------------------------------------


class TestOwnProfile:
    def test_get_returns_all_fields(self, client):
        body = client.get(PROFILE).json()
        assert set(body) == PUBLIC_KEYS | {"status"}
        assert body["status"] == "PRIVATE"
        assert body["github_login"] == "testuser"
        assert body["avatar_url"] == "https://avatars.githubusercontent.com/u/10001?v=4"

    def test_partial_update_keeps_other_fields(self, client):
        client.patch(PROFILE, json={"display_name": "Ann", "location": "Berlin"})
        body = client.patch(PROFILE, json={"headline": "Engineer"}).json()
        assert body["display_name"] == "Ann"
        assert body["location"] == "Berlin"
        assert body["headline"] == "Engineer"

    def test_null_clears_field(self, client):
        client.patch(PROFILE, json={"location": "Berlin", "bio": "Hi"})
        body = client.patch(PROFILE, json={"location": None}).json()
        assert body["location"] is None
        assert body["bio"] == "Hi"

    def test_empty_body_changes_nothing(self, client):
        before = client.patch(PROFILE, json={"display_name": "Ann"}).json()
        assert client.patch(PROFILE, json={}).json() == before

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("  Ann  ", "Ann"), ("", None), ("   ", None), ("\tAnn\n", "Ann")],
    )
    def test_trim_and_blank_to_null(self, client, value, expected):
        client.patch(PROFILE, json={"display_name": "Old"})
        body = client.patch(PROFILE, json={"display_name": value}).json()
        assert body["display_name"] == expected

    @pytest.mark.parametrize("field", ["display_name", "headline", "location"])
    @pytest.mark.parametrize("bad", ["a\x00b", "a\x07b", "a\nb", "a\x7fb", "a\x85b"])
    def test_control_characters_rejected(self, client, field, bad):
        errors = _field_errors(client.patch(PROFILE, json={field: bad}))
        assert errors == [{"loc": ["body", field], "type": "control_characters"}]

    def test_bio_allows_newlines_and_normalizes_crlf(self, client):
        body = client.patch(PROFILE, json={"bio": "line one\r\nline two\n\nend"}).json()
        assert body["bio"] == "line one\nline two\n\nend"

    @pytest.mark.parametrize("bad", ["a\tb", "a\rb", "a\x00b"])
    def test_bio_rejects_other_control_characters(self, client, bad):
        errors = _field_errors(client.patch(PROFILE, json={"bio": bad}))
        assert errors == [{"loc": ["body", "bio"], "type": "control_characters"}]

    @pytest.mark.parametrize(("field", "limit"), LIMITS.items())
    def test_length_limits(self, client, field, limit):
        ok = client.patch(PROFILE, json={field: "  " + "a" * limit + "  "})
        assert ok.status_code == 200
        assert ok.json()[field] == "a" * limit

        errors = _field_errors(client.patch(PROFILE, json={field: "a" * (limit + 1)}))
        assert errors == [{"loc": ["body", field], "type": "string_too_long"}]

    @pytest.mark.parametrize(
        "payload",
        [
            {"slug": "new-slug"},
            {"status": "PUBLISHED"},
            {"avatar_url": "https://x"},
            {"unknown": 1},
            {"display_name": "Ann", "slug": "new-slug"},
        ],
    )
    def test_unknown_fields_rejected(self, client, payload):
        before = client.get(PROFILE).json()
        errors = _field_errors(client.patch(PROFILE, json=payload))
        assert all(e["type"] == "extra_forbidden" for e in errors if e["loc"][1] != "display_name")
        assert client.get(PROFILE).json() == before

    def test_non_string_value_rejected(self, client):
        errors = _field_errors(client.patch(PROFILE, json={"display_name": 5}))
        assert errors == [{"loc": ["body", "display_name"], "type": "string_type"}]

    def test_updated_at_changes_only_on_real_change(self, client, db_session):
        client.patch(PROFILE, json={"display_name": "Ann"})
        first = _profile_row(db_session, 10001).updated_at
        client.patch(PROFILE, json={"display_name": "Ann"})
        assert _profile_row(db_session, 10001).updated_at == first
        client.patch(PROFILE, json={"display_name": "Bob"})
        assert _profile_row(db_session, 10001).updated_at > first

    def test_other_users_profile_untouched(self, make_auth_client, db_session):
        alice = make_auth_client(make_github_transport(github_user_id=501, github_login="alice"))
        login(alice)
        bob = make_auth_client(make_github_transport(github_user_id=502, github_login="bob"))
        login(bob)
        bob.patch(PROFILE, json={"display_name": "Bob"})

        alice.patch(PROFILE, json={"display_name": "Alice", "headline": "A"})
        alice.post(PUBLISH)

        bob_body = bob.get(PROFILE).json()
        assert bob_body["slug"] == "bob"
        assert bob_body["display_name"] == "Bob"
        assert bob_body["headline"] is None
        assert bob_body["status"] == "PRIVATE"
        assert _profile_row(db_session, 502).display_name == "Bob"
        assert alice.get(PROFILE).json()["display_name"] == "Alice"

    @pytest.mark.parametrize(
        ("method", "path"),
        [("get", PROFILE), ("patch", PROFILE), ("post", PUBLISH), ("post", UNPUBLISH)],
    )
    def test_requires_session(self, auth_client, method, path):
        kwargs = {"json": {"display_name": "x"}} if method == "patch" else {}
        _error(getattr(auth_client, method)(path, **kwargs), 401, "UNAUTHORIZED")

    def test_unknown_session_token_gives_401(self, auth_client):
        auth_client.cookies.set("session", "not-a-real-token")
        _error(auth_client.get(PROFILE), 401, "UNAUTHORIZED")


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------


class TestPublication:
    def test_publish_and_unpublish(self, client):
        _publishable(client)
        assert client.post(PUBLISH).json()["status"] == "PUBLISHED"
        assert client.post(UNPUBLISH).json()["status"] == "PRIVATE"

    @pytest.mark.parametrize(
        ("payload", "missing"),
        [
            ({}, ["display_name", "headline"]),
            ({"display_name": "Ann"}, ["headline"]),
            ({"headline": "Dev"}, ["display_name"]),
        ],
    )
    def test_incomplete_profile_cannot_be_published(self, client, payload, missing):
        client.patch(PROFILE, json=payload)
        error = _error(client.post(PUBLISH), 422, "PROFILE_INCOMPLETE")
        assert error["details"] == {"missing_fields": missing}
        assert client.get(PROFILE).json()["status"] == "PRIVATE"

    def test_publish_is_idempotent(self, client, db_session):
        _publishable(client)
        client.post(PUBLISH)
        updated_at = _profile_row(db_session, 10001).updated_at
        resp = client.post(PUBLISH)
        assert resp.status_code == 200 and resp.json()["status"] == "PUBLISHED"
        assert _profile_row(db_session, 10001).updated_at == updated_at

    def test_unpublish_private_is_noop(self, client):
        resp = client.post(UNPUBLISH)
        assert resp.status_code == 200 and resp.json()["status"] == "PRIVATE"

    @pytest.mark.parametrize(
        ("payload", "missing"),
        [
            ({"display_name": None}, ["display_name"]),
            ({"headline": "   "}, ["headline"]),
            ({"display_name": "", "headline": None}, ["display_name", "headline"]),
        ],
    )
    def test_required_fields_cannot_be_cleared_when_published(self, client, payload, missing):
        before = _publishable(client)
        client.post(PUBLISH)
        error = _error(client.patch(PROFILE, json=payload), 422, "PROFILE_INCOMPLETE")
        assert error["details"] == {"missing_fields": missing}
        after = client.get(PROFILE).json()
        assert after["display_name"] == before["display_name"]
        assert after["headline"] == before["headline"]

    def test_published_profile_can_edit_other_fields(self, client):
        _publishable(client)
        client.post(PUBLISH)
        resp = client.patch(PROFILE, json={"bio": "New bio", "headline": "Lead"})
        assert resp.status_code == 200
        assert resp.json()["headline"] == "Lead"


class TestDatabaseConstraints:
    def _insert_user(self, db_session, github_user_id: int) -> User:
        user = User(github_user_id=github_user_id, github_login=f"u{github_user_id}")
        db_session.add(user)
        db_session.flush()
        return user

    @pytest.mark.parametrize(
        ("display_name", "headline"), [(None, "Dev"), ("Ann", None), (None, None)]
    )
    def test_published_without_required_fields_rejected(self, db_session, display_name, headline):
        user = self._insert_user(db_session, 70001)
        with pytest.raises(IntegrityError, match="ck_profiles_published_complete"):
            with db_session.begin_nested():
                db_session.execute(
                    text(
                        "INSERT INTO profiles (user_id, slug, status, display_name, headline) "
                        "VALUES (:u, 'direct-insert', 'PUBLISHED', :d, :h)"
                    ),
                    {"u": user.id, "d": display_name, "h": headline},
                )

    def test_clearing_headline_of_published_row_rejected(self, db_session):
        user = self._insert_user(db_session, 70002)
        db_session.execute(
            text(
                "INSERT INTO profiles (user_id, slug, status, display_name, headline) "
                "VALUES (:u, 'direct-update', 'PUBLISHED', 'Ann', 'Dev')"
            ),
            {"u": user.id},
        )
        with pytest.raises(IntegrityError, match="ck_profiles_published_complete"):
            with db_session.begin_nested():
                db_session.execute(
                    text("UPDATE profiles SET headline = NULL WHERE user_id = :u"), {"u": user.id}
                )

    @pytest.mark.parametrize(("column", "limit"), LIMITS.items())
    def test_length_and_blank_checks(self, db_session, column, limit):
        user = self._insert_user(db_session, 70003)
        for bad in ("x" * (limit + 1), "   "):
            with pytest.raises(IntegrityError, match=f"ck_profiles_{column}"):
                with db_session.begin_nested():
                    db_session.execute(
                        text(
                            f"INSERT INTO profiles (user_id, slug, status, {column}) "
                            "VALUES (:u, 'direct-check', 'PRIVATE', :v)"
                        ),
                        {"u": user.id, "v": bad},
                    )


# ---------------------------------------------------------------------------
# Public profile
# ---------------------------------------------------------------------------


class TestPublicProfile:
    def _published(self, client) -> str:
        _publishable(client)
        client.patch(PROFILE, json={"bio": "About me", "location": "Berlin"})
        return client.post(PUBLISH).json()["slug"]

    def test_published_profile_is_visible_with_exact_keys(self, client, make_auth_client):
        slug = self._published(client)
        visitor = make_auth_client(send_origin=False)
        resp = visitor.get(f"{PUBLIC}/{slug}")
        assert resp.status_code == 200
        body = resp.json()
        # Projects are covered in test_public_projects.py.
        assert set(body) == PUBLIC_KEYS | {"featured", "other"}
        assert body == {
            "slug": slug,
            "display_name": "Ann Dev",
            "headline": "Backend developer",
            "bio": "About me",
            "location": "Berlin",
            "avatar_url": "https://avatars.githubusercontent.com/u/10001?v=4",
            "github_login": "testuser",
            "featured": [],
            "other": [],
        }
        assert "test@example.com" not in resp.text
        assert "PUBLISHED" not in resp.text

    def test_slug_is_case_insensitive(self, client):
        slug = self._published(client)
        assert client.get(f"{PUBLIC}/{slug.upper()}").status_code == 200

    def test_not_found_responses_are_identical(self, client, make_auth_client):
        private_slug = client.get(PROFILE).json()["slug"]
        visitor = make_auth_client(send_origin=False)

        def body_without_request_id(path: str) -> dict:
            resp = visitor.get(path)
            assert resp.status_code == 404
            error = resp.json()["error"]
            assert error.pop("request_id") == resp.headers["x-request-id"]
            return error

        unknown_url = body_without_request_id("/api/v1/this-route-does-not-exist")
        for slug in (private_slug, "no-such-profile", "-bad-", "ab", "a" * 40, "bad_slug%21"):
            assert body_without_request_id(f"{PUBLIC}/{slug}") == unknown_url, slug

    def test_unpublish_hides_profile_again(self, client):
        slug = self._published(client)
        assert client.get(f"{PUBLIC}/{slug}").status_code == 200
        client.post(UNPUBLISH)
        _error(client.get(f"{PUBLIC}/{slug}"), 404, "NOT_FOUND")


# ---------------------------------------------------------------------------
# avatar_url from GitHub
# ---------------------------------------------------------------------------


class TestAvatar:
    def _avatar(self, db_session, github_user_id: int = 10001) -> str | None:
        db_session.expire_all()
        return db_session.execute(
            select(GitHubAccount.avatar_url).join(User).where(User.github_user_id == github_user_id)
        ).scalar_one()

    def test_saved_on_first_login_and_updated_on_next(self, make_auth_client, db_session):
        client = make_auth_client(make_github_transport(avatar_url="https://avatars.example/1"))
        login(client)
        assert self._avatar(db_session) == "https://avatars.example/1"

        make_auth_client(make_github_transport(avatar_url="https://avatars.example/2"))
        login(client)
        assert self._avatar(db_session) == "https://avatars.example/2"

    def test_missing_avatar_on_relogin_keeps_stored_one(self, make_auth_client, db_session):
        client = make_auth_client(make_github_transport(avatar_url="https://avatars.example/1"))
        login(client)

        make_auth_client(make_github_transport(avatar_url=None))
        login(client)
        assert self._avatar(db_session) == "https://avatars.example/1"
        assert client.get(PROFILE).json()["avatar_url"] == "https://avatars.example/1"

    @pytest.mark.parametrize(
        "user_json",
        [
            {"id": 10001, "login": "testuser"},
            {"id": 10001, "login": "testuser", "avatar_url": None},
            {"id": 10001, "login": "testuser", "avatar_url": "javascript:alert(1)"},
            {"id": 10001, "login": "testuser", "avatar_url": "http://insecure.example/a.png"},
        ],
        ids=["missing", "null", "javascript", "http"],
    )
    def test_absent_or_unusable_avatar_is_null(self, make_auth_client, db_session, user_json):
        import httpx

        client = make_auth_client(
            make_github_transport(user_response=lambda request: httpx.Response(200, json=user_json))
        )
        login(client)
        assert self._avatar(db_session) is None
        assert client.get(PROFILE).json()["avatar_url"] is None
