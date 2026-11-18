"""The public project page (step 4.3): the whitelist, one 404 for everything that is
not shown, screenshots in order without ids, and a query count that does not grow."""

from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import event

from app.settings import settings
from tests.conftest import login, make_github_transport
from tests.test_projects import COMPLETE, _create, _error, _published, _url

PUBLIC = "/api/v1/public/profiles"
PAGE_KEYS = {
    "id",
    "title",
    "summary",
    "description",
    "problem",
    "results",
    "role",
    "contribution",
    "technologies",
    "demo_url",
    "screenshots",
    "github",
    "owner",
}
SCREENSHOT_KEYS = {"url", "caption", "width", "height"}
OWNER_KEYS = {"slug", "display_name", "avatar_url"}


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", tmp_path)
    return tmp_path


@pytest.fixture
def client(auth_client):
    login(auth_client)
    auth_client.patch("/api/v1/profile", json={"display_name": "Ann", "headline": "Dev"})
    assert auth_client.post("/api/v1/profile/publish").status_code == 200
    return auth_client


@pytest.fixture
def slug(client) -> str:
    return client.get("/api/v1/profile").json()["slug"]


@pytest.fixture
def visitor(client, make_auth_client):
    """No session; created after the owner so it shares the same database session."""
    return make_auth_client(send_origin=False)


def _page_url(slug: str, project_id: str) -> str:
    return f"{PUBLIC}/{slug}/projects/{project_id}"


def _page(visitor, slug: str, project: dict) -> dict:
    resp = visitor.get(_page_url(slug, project["id"]))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _upload(client, project: dict, color: str, caption: str | None = None) -> dict:
    """Uploads a screenshot and returns it: the last item of the returned list."""
    out = BytesIO()
    Image.new("RGB", (40, 20), color).save(out, "PNG")
    resp = client.post(
        _url(project, "screenshots"),
        files={"file": ("shot.png", out.getvalue(), "image/png")},
        data={} if caption is None else {"caption": caption},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["items"][-1]


class TestContent:
    def test_whitelist_and_values(self, client, visitor, slug):
        project = _published(
            client,
            description="Long description",
            problem="The problem",
            results="The results",
            demo_url="https://demo.example/app",
            technologies=["Zeta", "alpha"],
        )
        body = _page(visitor, slug, project)
        assert set(body) == PAGE_KEYS
        profile = visitor.get(f"{PUBLIC}/{slug}").json()
        assert body == {
            "id": project["id"],
            "title": COMPLETE["title"],
            "summary": COMPLETE["summary"],
            "description": "Long description",
            "problem": "The problem",
            "results": "The results",
            "role": COMPLETE["role"],
            "contribution": COMPLETE["contribution"],
            "technologies": ["Zeta", "alpha"],
            "demo_url": "https://demo.example/app",
            "screenshots": [],
            "github": None,
            "owner": {
                "slug": slug,
                "display_name": "Ann",
                "avatar_url": profile["avatar_url"],
            },
        }

    def test_optional_fields_are_null(self, client, visitor, slug):
        body = _page(visitor, slug, _published(client))
        for key in ("description", "problem", "results", "demo_url"):
            assert body[key] is None

    def test_featured_project_has_no_position(self, client, visitor, slug):
        project = _published(client)
        assert client.post(_url(project, "showcase")).status_code == 200
        assert set(_page(visitor, slug, project)) == PAGE_KEYS

    def test_screenshots_in_order_without_ids(self, client, visitor, slug):
        project = _published(client)
        red = _upload(client, project, "red", "First")
        blue = _upload(client, project, "blue")
        resp = client.post(
            _url(project, "screenshots/reorder"),
            json={"screenshot_ids": [blue["id"], red["id"]]},
        )
        assert resp.status_code == 200, resp.text

        shots = _page(visitor, slug, project)["screenshots"]
        assert all(set(shot) == SCREENSHOT_KEYS for shot in shots)
        assert shots == [
            {"url": blue["url"], "caption": None, "width": 40, "height": 20},
            {"url": red["url"], "caption": "First", "width": 40, "height": 20},
        ]

    def test_slug_in_another_case(self, client, visitor, slug):
        project = _published(client)
        assert _page(visitor, slug.upper(), project)["id"] == project["id"]

    def test_no_cache_header(self, client, visitor, slug):
        resp = visitor.get(_page_url(slug, _published(client)["id"]))
        assert "cache-control" not in resp.headers


class TestNotFound:
    def _not_found(self, visitor, slug: str, project_id: str) -> None:
        _error(visitor.get(_page_url(slug, project_id)), 404, "NOT_FOUND")

    def test_draft_archived_and_hidden(self, client, visitor, slug):
        draft = _create(client, **COMPLETE)
        archived = _published(client, title="Archived")
        client.post(_url(archived, "archive"))
        hidden = _published(client, title="Hidden")
        client.post(_url(hidden, "visibility"), json={"visibility": "PRIVATE"})
        for project in (draft, archived, hidden):
            self._not_found(visitor, slug, project["id"])

    def test_private_profile(self, client, visitor, slug):
        project = _published(client)
        assert client.post("/api/v1/profile/unpublish").status_code == 200
        self._not_found(visitor, slug, project["id"])

    def test_unknown_slug_and_project(self, client, visitor, slug):
        project = _published(client)
        self._not_found(visitor, "nobody-here", project["id"])
        self._not_found(visitor, slug, "11111111-1111-4111-8111-111111111111")

    @pytest.mark.parametrize(
        "project_id",
        [
            "not-a-uuid",
            "11111111111141118111111111111111",
            "{11111111-1111-4111-8111-111111111111}",
        ],
    )
    def test_malformed_id(self, client, visitor, slug, project_id):
        self._not_found(visitor, slug, project_id)

    def test_project_of_another_user_under_this_slug(self, client, visitor, slug, make_auth_client):
        other = make_auth_client(make_github_transport(github_user_id=20002, github_login="other"))
        login(other)
        other.patch("/api/v1/profile", json={"display_name": "Bob", "headline": "Dev"})
        assert other.post("/api/v1/profile/publish").status_code == 200
        foreign = _published(other)
        self._not_found(visitor, slug, foreign["id"])
        other_slug = other.get("/api/v1/profile").json()["slug"]
        assert _page(visitor, other_slug, foreign)["owner"]["display_name"] == "Bob"


class TestQueryCount:
    def _statements(self, visitor, db_session, slug: str, project: dict) -> list[str]:
        seen: list[str] = []

        def record(conn, cursor, statement, *args) -> None:
            seen.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", record)
        try:
            resp = visitor.get(_page_url(slug, project["id"]))
        finally:
            event.remove(connection, "before_cursor_execute", record)
        assert resp.status_code == 200, resp.text
        return seen

    def test_five_selects_for_1_and_6_screenshots(self, client, visitor, slug, db_session):
        project = _published(client, technologies=["A", "B", "C"])
        _upload(client, project, "red")
        one = self._statements(visitor, db_session, slug, project)
        for color in ("blue", "green", "white", "black", "gray"):
            _upload(client, project, color)
        six = self._statements(visitor, db_session, slug, project)
        # Profile, project, technologies, screenshots, GitHub data.
        assert len(one) == len(six) == 5
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in six)
