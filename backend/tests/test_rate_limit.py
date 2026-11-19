"""Per-IP rate limits (ADR-024): the limiter itself, contacts and login."""

from urllib.parse import parse_qs, urlparse

from app.rate_limit import RateLimiter
from tests.conftest import login

CONTACTS = "/api/v1/public/profiles/nobody-here/contacts?type=EMAIL"
LOGIN = "/api/v1/auth/github/login"
CALLBACK = "/api/v1/auth/github/callback"


class TestRateLimiter:
    def test_blocks_past_the_limit_until_the_next_window(self):
        limiter = RateLimiter((2, 60))
        assert limiter.hit("a", 120.0) is None
        assert limiter.hit("a", 130.0) is None
        assert limiter.hit("a", 150.5) == 30
        assert limiter.hit("a", 180.0) is None

    def test_keys_are_counted_apart(self):
        limiter = RateLimiter((1, 60))
        assert limiter.hit("a", 0.0) is None
        assert limiter.hit("b", 0.0) is None
        assert limiter.hit("a", 1.0) == 59

    def test_a_rejected_request_is_not_counted(self):
        limiter = RateLimiter((2, 60), (3, 3600))
        for now in (0.0, 1.0):
            assert limiter.hit("a", now) is None
        assert limiter.hit("a", 2.0) == 58
        # Only the two passed requests count toward the hour.
        assert limiter.hit("a", 60.0) is None
        assert limiter.hit("a", 61.0) == 3539

    def test_every_limit_must_pass(self):
        limiter = RateLimiter((10, 60), (2, 3600))
        assert limiter.hit("a", 0.0) is None
        assert limiter.hit("a", 1.0) is None
        assert limiter.hit("a", 2.0) == 3598

    def test_ended_windows_are_pruned(self, monkeypatch):
        monkeypatch.setattr("app.rate_limit._PRUNE_ABOVE", 2)
        limiter = RateLimiter((1, 60))
        for key in "abc":
            limiter.hit(key, 0.0)
        limiter.hit("d", 60.0)
        assert set(key for _, key in limiter._counts) == {"d"}


class TestContacts:
    def test_eleventh_request_in_a_minute_is_429(self, make_auth_client):
        client = make_auth_client(send_origin=False)
        for _ in range(10):
            assert client.get(CONTACTS).status_code == 404

        resp = client.get(CONTACTS)

        assert resp.status_code == 429
        assert 1 <= int(resp.headers["Retry-After"]) <= 60
        error = resp.json()["error"]
        assert error["code"] == "RATE_LIMITED"
        assert error["request_id"] == resp.headers["X-Request-ID"]

    def test_another_ip_is_not_limited(self, make_auth_client):
        first = make_auth_client(send_origin=False, client=("203.0.113.1", 1))
        for _ in range(11):
            first.get(CONTACTS)
        other = make_auth_client(send_origin=False, client=("203.0.113.2", 1))

        assert other.get(CONTACTS).status_code == 404


class TestLogin:
    def test_login_past_the_limit_redirects_with_the_code(self, make_auth_client):
        client = make_auth_client()
        for _ in range(20):
            assert client.get(LOGIN).status_code == 302

        resp = client.get(LOGIN)

        assert resp.status_code == 302
        location = urlparse(resp.headers["location"])
        assert location.path == "/login"
        assert parse_qs(location.query) == {"error": ["RATE_LIMITED"]}
        assert "oauth_state" not in resp.cookies

    def test_callback_past_the_limit_redirects_without_calling_github(self, make_auth_client):
        calls = []

        def handler(request):
            calls.append(request)
            raise AssertionError("GitHub must not be called")

        from tests.conftest import _MockTransport

        client = make_auth_client(_MockTransport(handler))
        for _ in range(20):
            client.get(CALLBACK)
        state = "s"
        client.cookies.set("oauth_state", state, path="/api/v1/auth/github")

        resp = client.get(f"{CALLBACK}?code=c&state={state}")

        assert parse_qs(urlparse(resp.headers["location"]).query) == {"error": ["RATE_LIMITED"]}
        assert calls == []

    def test_a_normal_login_passes(self, auth_client):
        assert login(auth_client)
