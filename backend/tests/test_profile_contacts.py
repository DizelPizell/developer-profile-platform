"""Contacts of a profile (ADR-020): normalization, PATCH /profile, public profile
and GET /public/profiles/{slug}/contacts."""

import logging

import pytest
from pydantic_core import PydanticCustomError
from sqlalchemy import text

from app.profile.contacts import contact_url, normalize
from tests.conftest import login

PROFILE = "/api/v1/profile"
PUBLISH = "/api/v1/profile/publish"
UNPUBLISH = "/api/v1/profile/unpublish"
PUBLIC = "/api/v1/public/profiles"

EMAIL = {"type": "EMAIL", "value": "Ann.Dev+cv@Example.COM"}
TELEGRAM = {"type": "TELEGRAM", "value": "@ann_dev"}
LINKEDIN = {"type": "LINKEDIN", "value": "https://www.linkedin.com/in/ann-dev/"}
PHONE = {"type": "PHONE", "value": "+7 (912) 345-67-89"}


def _other(n: int = 1) -> dict:
    return {"type": "OTHER", "value": f"https://blog{n}.example.com/", "label": f"Blog {n}"}


ALL_FOUR = [EMAIL, TELEGRAM, LINKEDIN, PHONE]


@pytest.fixture
def client(auth_client):
    login(auth_client)
    return auth_client


def _patch(client, contacts):
    return client.patch(PROFILE, json={"contacts": contacts})


def _fields(resp) -> list[dict]:
    assert resp.status_code == 422, resp.text
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    return error["details"]["fields"]


def _publish(client) -> str:
    client.patch(PROFILE, json={"display_name": "Ann Dev", "headline": "Backend developer"})
    return client.post(PUBLISH).json()["slug"]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("contact_type", "value", "stored"),
    [
        ("EMAIL", " Ann.Dev+cv@Example.COM ", "Ann.Dev+cv@example.com"),
        ("EMAIL", "a_b-c@mail.sub-domain.io", "a_b-c@mail.sub-domain.io"),
        ("TELEGRAM", "ann_dev", "ann_dev"),
        ("TELEGRAM", "@Ann_Dev", "Ann_Dev"),
        ("TELEGRAM", "t.me/ann_dev", "ann_dev"),
        ("TELEGRAM", "https://t.me/ann_dev/", "ann_dev"),
        ("TELEGRAM", "HTTPS://T.ME/ann_dev", "ann_dev"),
        ("TELEGRAM", "a" * 32, "a" * 32),
        ("LINKEDIN", "linkedin.com/in/ann-dev", "ann-dev"),
        ("LINKEDIN", "https://linkedin.com/in/Ann-Dev-123", "Ann-Dev-123"),
        ("LINKEDIN", "https://www.linkedin.com/in/ann-dev/", "ann-dev"),
        ("LINKEDIN", "https://de.linkedin.com/in/ann-dev", "ann-dev"),
        ("PHONE", "+7 (912) 345-67-89", "+79123456789"),
        ("PHONE", "+12025550123", "+12025550123"),
        ("PHONE", "+" + "1" * 15, "+" + "1" * 15),
        ("OTHER", "https://example.com", "https://example.com"),
        ("OTHER", "HTTP://Example.com/a?b=1#c", "http://Example.com/a?b=1#c"),
        ("OTHER", "https://example.com:8443/path", "https://example.com:8443/path"),
    ],
)
def test_normalize_accepts(contact_type, value, stored):
    assert normalize(contact_type, value) == stored


@pytest.mark.parametrize(
    ("contact_type", "value"),
    [
        # Email: mailto: injection, non-ASCII, malformed.
        ("EMAIL", "a@b.c?bcc=x"),
        ("EMAIL", "a@b.com?bcc=x@evil.example"),
        ("EMAIL", "a&b@example.com"),
        ("EMAIL", "a%40b@example.com"),
        ("EMAIL", "a b@example.com"),
        ("EMAIL", "ann@пример.рф"),
        ("EMAIL", "анна@example.com"),
        ("EMAIL", "ann@example"),
        ("EMAIL", "ann@example.c"),
        ("EMAIL", "ann"),
        ("EMAIL", "mailto:ann@example.com"),
        ("EMAIL", "a" * 250 + "@example.com"),
        # Telegram: other hosts, invites, deeper paths, queries, reserved paths.
        ("TELEGRAM", "abcd"),
        ("TELEGRAM", "a" * 33),
        ("TELEGRAM", "ann-dev"),
        ("TELEGRAM", "аннадев"),
        ("TELEGRAM", "t.me/+AbCdEfGhIjK"),
        ("TELEGRAM", "https://t.me/joinchat/AbCdEfGh"),
        ("TELEGRAM", "t.me/ann_dev/123"),
        ("TELEGRAM", "t.me/ann_dev?start=x"),
        ("TELEGRAM", "http://t.me/ann_dev"),
        ("TELEGRAM", "telegram.me/ann_dev"),
        ("TELEGRAM", "https://t.me.evil.example/ann_dev"),
        ("TELEGRAM", "https://evil.example/t.me/ann_dev"),
        ("TELEGRAM", "@@ann_dev"),
        ("TELEGRAM", "joinchat"),
        ("TELEGRAM", "t.me/addstickers"),
        ("TELEGRAM", "Proxy"),
        ("TELEGRAM", "setlanguage"),
        ("TELEGRAM", "confirmphone"),
        # LinkedIn: hosts compared exactly, other paths, queries.
        ("LINKEDIN", "https://linkedin.com.evil.example/in/ann-dev"),
        ("LINKEDIN", "https://linkedin.com@evil.example/in/ann-dev"),
        ("LINKEDIN", "https://evil.example/linkedin.com/in/ann-dev"),
        ("LINKEDIN", "https://evillinkedin.com/in/ann-dev"),
        ("LINKEDIN", "https://www.linkedin.com/company/acme"),
        ("LINKEDIN", "https://www.linkedin.com/in/ann-dev?trk=x"),
        ("LINKEDIN", "https://www.linkedin.com/in/ann-dev/details"),
        ("LINKEDIN", "https://www.linkedin.com:443/in/ann-dev"),
        ("LINKEDIN", "http://www.linkedin.com/in/ann-dev"),
        ("LINKEDIN", "ann-dev"),
        ("LINKEDIN", "https://www.linkedin.com/in/ab"),
        ("LINKEDIN", "https://www.linkedin.com/in/анна"),
        ("LINKEDIN", "javascript:alert(1)//linkedin.com/in/ann-dev"),
        # Phone: without +, letters, too short or long.
        ("PHONE", "89123456789"),
        ("PHONE", "+0123456789"),
        ("PHONE", "+7912"),
        ("PHONE", "+1234567890123456"),
        ("PHONE", "+7 912 ABC"),
        ("PHONE", "+７９１２３４５６７８９"),
        ("PHONE", "tel:+79123456789"),
        # Other: schemes, logins, whitespace, backslash, controls, hosts without a dot.
        ("OTHER", "javascript:alert(1)"),
        ("OTHER", "JavaScript://example.com/%0aalert(1)"),
        ("OTHER", "data:text/html,<script>alert(1)</script>"),
        ("OTHER", "ftp://example.com"),
        ("OTHER", "//example.com"),
        ("OTHER", "example.com"),
        ("OTHER", "https://user:pass@example.com"),
        ("OTHER", "https://user@example.com"),
        ("OTHER", "https://exa mple.com"),
        ("OTHER", "https://example.com\\@evil.example"),
        ("OTHER", "https://example.com/\x00"),
        ("OTHER", "https://localhost/"),
        ("OTHER", "https://example.com:99999/"),
        ("OTHER", "https://example.com/" + "a" * 2048),
    ],
)
def test_normalize_rejects(contact_type, value):
    with pytest.raises(PydanticCustomError):
        normalize(contact_type, value)


@pytest.mark.parametrize("contact_type", ["EMAIL", "TELEGRAM", "LINKEDIN", "PHONE", "OTHER"])
@pytest.mark.parametrize("value", ["", "   "])
def test_blank_value_is_an_error(contact_type, value):
    with pytest.raises(PydanticCustomError) as exc:
        normalize(contact_type, value)
    assert exc.value.type == "string_too_short"


def test_links_are_built_by_the_server():
    assert contact_url("EMAIL", "a@example.com") == "mailto:a@example.com"
    assert contact_url("TELEGRAM", "ann_dev") == "https://t.me/ann_dev"
    assert contact_url("LINKEDIN", "ann-dev") == "https://www.linkedin.com/in/ann-dev"
    assert contact_url("PHONE", "+79123456789") == "tel:+79123456789"
    assert contact_url("OTHER", "https://example.com/") == "https://example.com/"


# ---------------------------------------------------------------------------
# PATCH /profile
# ---------------------------------------------------------------------------


class TestWrite:
    def test_new_profile_has_no_contacts(self, client):
        assert client.get(PROFILE).json()["contacts"] == []

    def test_list_is_normalized_in_order_with_links(self, client):
        resp = _patch(client, [*ALL_FOUR, _other()])
        assert resp.status_code == 200, resp.text
        assert resp.json()["contacts"] == [
            {
                "type": "EMAIL",
                "value": "Ann.Dev+cv@example.com",
                "label": None,
                "url": "mailto:Ann.Dev+cv@example.com",
            },
            {"type": "TELEGRAM", "value": "ann_dev", "label": None, "url": "https://t.me/ann_dev"},
            {
                "type": "LINKEDIN",
                "value": "ann-dev",
                "label": None,
                "url": "https://www.linkedin.com/in/ann-dev",
            },
            {"type": "PHONE", "value": "+79123456789", "label": None, "url": "tel:+79123456789"},
            {
                "type": "OTHER",
                "value": "https://blog1.example.com/",
                "label": "Blog 1",
                "url": "https://blog1.example.com/",
            },
        ]
        assert client.get(PROFILE).json()["contacts"] == resp.json()["contacts"]

    def test_absent_keeps_list_replace_and_clear(self, client):
        _patch(client, [TELEGRAM, EMAIL])
        kept = client.patch(PROFILE, json={"location": "Berlin"}).json()["contacts"]
        assert [c["type"] for c in kept] == ["TELEGRAM", "EMAIL"]

        replaced = _patch(client, [PHONE]).json()["contacts"]
        assert [c["type"] for c in replaced] == ["PHONE"]

        assert _patch(client, []).json()["contacts"] == []
        assert client.get(PROFILE).json()["contacts"] == []

    def test_order_follows_the_list(self, client):
        _patch(client, [EMAIL, PHONE])
        reordered = _patch(client, [PHONE, EMAIL]).json()["contacts"]
        assert [c["type"] for c in reordered] == ["PHONE", "EMAIL"]

    def test_null_is_rejected(self, client):
        _patch(client, [EMAIL])
        fields = _fields(_patch(client, None))
        assert fields == [{"loc": ["body", "contacts"], "type": "list_type"}]
        assert len(client.get(PROFILE).json()["contacts"]) == 1

    def test_seven_contacts_are_the_limit(self, client):
        assert _patch(client, [*ALL_FOUR, _other(1), _other(2), _other(3)]).status_code == 200
        fields = _fields(_patch(client, [*ALL_FOUR, _other(1), _other(2), _other(3), _other(4)]))
        assert fields == [{"loc": ["body", "contacts"], "type": "too_long"}]

    def test_three_other_contacts_are_the_limit(self, client):
        fields = _fields(_patch(client, [_other(n) for n in range(1, 5)]))
        assert fields == [{"loc": ["body", "contacts"], "type": "too_many_other_contacts"}]

    def test_repeated_type_is_rejected(self, client):
        second = {"type": "EMAIL", "value": "other@example.com"}
        fields = _fields(_patch(client, [EMAIL, TELEGRAM, second]))
        assert fields == [{"loc": ["body", "contacts"], "type": "duplicate_contact_type"}]

    def test_item_errors_point_at_the_field(self, client):
        fields = _fields(
            _patch(
                client,
                [
                    TELEGRAM,
                    {"type": "PHONE", "value": "89123456789"},
                    {"type": "OTHER", "value": "javascript:alert(1)", "label": "x"},
                    {"type": "OTHER", "value": "https://example.com"},
                    {"type": "EMAIL", "value": "a@example.com", "label": "Work"},
                    {"type": "SKYPE", "value": "ann"},
                    {"type": "TELEGRAM", "value": "  "},
                ],
            )
        )
        assert fields == [
            {"loc": ["body", "contacts", 1, "value"], "type": "invalid_phone"},
            {"loc": ["body", "contacts", 2, "value"], "type": "invalid_url"},
            {"loc": ["body", "contacts", 3, "label"], "type": "missing"},
            {"loc": ["body", "contacts", 4, "label"], "type": "label_not_allowed"},
            {"loc": ["body", "contacts", 5, "type"], "type": "literal_error"},
            {"loc": ["body", "contacts", 6, "value"], "type": "string_too_short"},
        ]

    def test_label_is_plain_text(self, client):
        ok = _patch(client, [{**_other(), "label": "  My blog  "}])
        assert ok.json()["contacts"][0]["label"] == "My blog"
        for label, error in [
            ("   ", "missing"),
            ("a" * 41, "string_too_long"),
            ("a\nb", "control_characters"),
        ]:
            fields = _fields(_patch(client, [{**_other(), "label": label}]))
            assert fields == [{"loc": ["body", "contacts", 0, "label"], "type": error}]

    def test_url_field_and_unknown_fields_are_rejected(self, client):
        fields = _fields(
            _patch(client, [{**TELEGRAM, "url": "https://evil.example"}, {**EMAIL, "id": 1}])
        )
        assert fields == [
            {"loc": ["body", "contacts", 0, "url"], "type": "extra_forbidden"},
            {"loc": ["body", "contacts", 1, "id"], "type": "extra_forbidden"},
        ]

    def test_errors_and_logs_do_not_echo_input(self, client, caplog):
        marker = "zz-secret-marker"
        caplog.set_level(logging.DEBUG)
        resp = _patch(
            client,
            [
                {"type": "EMAIL", "value": f"{marker}@example.com?bcc=x"},
                {"type": "OTHER", "value": f"javascript:{marker}", "label": marker * 3},
            ],
        )
        assert resp.status_code == 422
        assert marker not in resp.text
        ok = _patch(client, [{"type": "EMAIL", "value": f"{marker}@example.com"}])
        assert ok.status_code == 200
        assert marker not in caplog.text

    def test_same_normalized_list_keeps_updated_at(self, client, db_session):
        def updated_at():
            return db_session.execute(
                text("SELECT updated_at FROM profiles p JOIN users u ON u.id = p.user_id "
                     "WHERE u.github_user_id = 10001")
            ).scalar_one()  # fmt: skip

        _patch(client, [EMAIL, TELEGRAM])
        before = updated_at()
        same = [
            {"type": "EMAIL", "value": "Ann.Dev+cv@EXAMPLE.com"},
            {**TELEGRAM, "value": "ann_dev"},
        ]
        assert _patch(client, same).status_code == 200
        assert updated_at() == before

        _patch(client, [TELEGRAM, EMAIL])
        assert updated_at() > before

    def test_contacts_do_not_affect_publication(self, client):
        _publish(client)
        resp = _patch(client, [EMAIL])
        assert resp.status_code == 200
        assert resp.json()["status"] == "PUBLISHED"
        assert _patch(client, []).json()["status"] == "PUBLISHED"

    def test_publish_and_unpublish_return_contacts(self, client):
        _patch(client, [TELEGRAM])
        _publish(client)
        assert client.post(UNPUBLISH).json()["contacts"][0]["type"] == "TELEGRAM"

    def test_origin_check_still_applies(self, make_auth_client):
        no_origin = make_auth_client(send_origin=False)
        login(no_origin)
        resp = no_origin.patch(PROFILE, json={"contacts": [TELEGRAM]})
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"
        assert no_origin.get(PROFILE).json()["contacts"] == []

    def test_users_email_never_becomes_a_contact(self, client):
        # The GitHub mock returns test@example.com for the user (ADR-012).
        assert client.get(PROFILE).json()["contacts"] == []

    def test_deleting_the_user_removes_contacts(self, client, db_session):
        _patch(client, [*ALL_FOUR, _other()])
        count = "SELECT count(*) FROM profile_contacts"
        assert db_session.execute(text(count)).scalar_one() == 5
        db_session.execute(text("DELETE FROM users WHERE github_user_id = 10001"))
        assert db_session.execute(text(count)).scalar_one() == 0


# ---------------------------------------------------------------------------
# Public profile and the endpoint for email and phone
# ---------------------------------------------------------------------------


class TestPublic:
    def test_public_profile_hides_email_and_phone(self, client, make_auth_client):
        _patch(client, [*ALL_FOUR, _other()])
        slug = _publish(client)
        visitor = make_auth_client(send_origin=False)
        resp = visitor.get(f"{PUBLIC}/{slug}")
        assert resp.status_code == 200
        assert resp.json()["contacts"] == [
            {"type": "EMAIL", "value": None, "label": None, "url": None},
            {"type": "TELEGRAM", "value": "ann_dev", "label": None, "url": "https://t.me/ann_dev"},
            {
                "type": "LINKEDIN",
                "value": "ann-dev",
                "label": None,
                "url": "https://www.linkedin.com/in/ann-dev",
            },
            {"type": "PHONE", "value": None, "label": None, "url": None},
            {
                "type": "OTHER",
                "value": "https://blog1.example.com/",
                "label": "Blog 1",
                "url": "https://blog1.example.com/",
            },
        ]
        for hidden in ("example.com", "Ann.Dev", "79123456789", "test@example.com"):
            assert hidden not in resp.text.replace("blog1.example.com", "")

    def test_reveal_returns_the_value_without_caching(self, client, make_auth_client):
        _patch(client, ALL_FOUR)
        slug = _publish(client)
        visitor = make_auth_client(send_origin=False)

        email = visitor.get(f"{PUBLIC}/{slug}/contacts", params={"type": "EMAIL"})
        assert email.status_code == 200
        assert email.headers["cache-control"] == "no-store"
        assert email.json() == {
            "type": "EMAIL",
            "value": "Ann.Dev+cv@example.com",
            "url": "mailto:Ann.Dev+cv@example.com",
        }
        phone = visitor.get(f"{PUBLIC}/{slug.upper()}/contacts", params={"type": "PHONE"})
        assert phone.json() == {"type": "PHONE", "value": "+79123456789", "url": "tel:+79123456789"}

    def test_reveal_not_found_is_the_profile_404(self, client, make_auth_client):
        _patch(client, [TELEGRAM, EMAIL])
        private_slug = client.get(PROFILE).json()["slug"]
        visitor = make_auth_client(send_origin=False)

        def body(path: str, **params) -> dict:
            resp = visitor.get(path, params=params)
            assert resp.status_code == 404, resp.text
            error = resp.json()["error"]
            del error["request_id"]
            return error

        reference = body(f"{PUBLIC}/{private_slug}")
        assert body(f"{PUBLIC}/{private_slug}/contacts", type="EMAIL") == reference
        assert body(f"{PUBLIC}/nobody-here/contacts", type="EMAIL") == reference
        assert body(f"{PUBLIC}/Bad_Slug!/contacts", type="EMAIL") == reference

        slug = _publish(client)
        assert body(f"{PUBLIC}/{slug}/contacts", type="PHONE") == reference

    @pytest.mark.parametrize("params", [{"type": "TELEGRAM"}, {"type": "email"}, {}])
    def test_reveal_rejects_other_types(self, client, make_auth_client, params):
        _patch(client, ALL_FOUR)
        slug = _publish(client)
        visitor = make_auth_client(send_origin=False)
        fields = _fields(visitor.get(f"{PUBLIC}/{slug}/contacts", params=params))
        assert [f["loc"] for f in fields] == [["query", "type"]]

    def test_unpublished_profile_hides_contacts(self, client, make_auth_client):
        _patch(client, [EMAIL])
        slug = _publish(client)
        client.post(UNPUBLISH)
        visitor = make_auth_client(send_origin=False)
        assert visitor.get(f"{PUBLIC}/{slug}/contacts", params={"type": "EMAIL"}).status_code == 404
