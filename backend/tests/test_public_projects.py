"""Projects on the public profile (ADR-015, step 3.3): featured and other, the card
whitelist, visibility rules and a query count that does not grow with projects."""

import pytest
from sqlalchemy import event, select

from app.models.identity import User
from tests.conftest import login, make_github_transport
from tests.test_projects import COMPLETE, PROJECTS, _create, _error, _published, _url

PUBLIC = "/api/v1/public/profiles"
CARD_KEYS = {"id", "title", "summary", "role", "technologies"}
FEATURED_KEYS = CARD_KEYS | {"position"}
SECRET_TEXT = {
    "description": "Secret description marker",
    "problem": "Secret problem marker",
    "results": "Secret results marker",
    "contribution": "Secret contribution marker",
}


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


def _public(visitor, slug: str) -> dict:
    resp = visitor.get(f"{PUBLIC}/{slug}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _feature(client, *projects: dict) -> None:
    for project in projects:
        assert client.post(_url(project, "showcase")).status_code == 200


def _ids(cards: list[dict]) -> list[str]:
    return [card["id"] for card in cards]


class TestContent:
    def test_profile_without_projects(self, visitor, slug):
        body = _public(visitor, slug)
        assert body["featured"] == []
        assert body["other"] == []

    def test_only_featured(self, client, visitor, slug):
        a, b = _published(client, title="A"), _published(client, title="B")
        _feature(client, a, b)
        body = _public(visitor, slug)
        assert _ids(body["featured"]) == [a["id"], b["id"]]
        assert [card["position"] for card in body["featured"]] == [1, 2]
        assert body["other"] == []

    def test_only_other(self, client, visitor, slug):
        a = _published(client)
        body = _public(visitor, slug)
        assert body["featured"] == []
        assert _ids(body["other"]) == [a["id"]]

    def test_featured_by_position_and_other_newest_first(self, client, visitor, slug):
        p1, p2, p3, p4, p5 = (_published(client, title=f"P{i}") for i in range(1, 6))
        _feature(client, p1, p4, p2)
        client.post(
            "/api/v1/profile/featured-projects/reorder",
            json={"project_ids": [p2["id"], p1["id"], p4["id"]]},
        )
        body = _public(visitor, slug)
        assert _ids(body["featured"]) == [p2["id"], p1["id"], p4["id"]]
        assert [card["position"] for card in body["featured"]] == [1, 2, 3]
        # Not featured, newest first; a featured project is not repeated.
        assert _ids(body["other"]) == [p5["id"], p3["id"]]

    def test_card_content_and_technology_order(self, client, visitor, slug):
        project = _published(client, technologies=["Zeta", "alpha", "Mid"])
        _feature(client, project)
        other = _published(client, title="Other", technologies=["Go"])
        body = _public(visitor, slug)
        assert body["featured"] == [
            {
                "id": project["id"],
                "title": COMPLETE["title"],
                "summary": COMPLETE["summary"],
                "role": COMPLETE["role"],
                "technologies": ["Zeta", "alpha", "Mid"],
                "position": 1,
            }
        ]
        assert body["other"][0]["technologies"] == ["Go"]
        assert body["other"][0]["title"] == other["title"]


class TestVisibility:
    def test_only_published_public_projects(self, client, visitor, slug):
        shown = _published(client, title="Shown")
        _create(client, **COMPLETE)  # DRAFT
        archived = _published(client, title="Archived")
        client.post(_url(archived, "archive"))
        hidden = _published(client, title="Hidden")
        client.post(_url(hidden, "visibility"), json={"visibility": "PRIVATE"})
        body = _public(visitor, slug)
        assert body["featured"] == []
        assert _ids(body["other"]) == [shown["id"]]

    def test_hiding_removes_from_public(self, client, visitor, slug):
        featured, other = _published(client, title="F"), _published(client, title="O")
        _feature(client, featured)
        for project in (featured, other):
            client.post(_url(project, "visibility"), json={"visibility": "PRIVATE"})
        body = _public(visitor, slug)
        assert body["featured"] == []
        assert body["other"] == []

    def test_other_users_projects_are_not_shown(self, client, visitor, slug, make_auth_client):
        other_user = make_auth_client(
            make_github_transport(github_user_id=20002, github_login="other")
        )
        login(other_user)
        _published(other_user)
        body = _public(visitor, slug)
        assert body["featured"] == [] and body["other"] == []

    def test_private_profile_is_the_same_404(self, client, visitor, slug):
        project = _published(client)
        _feature(client, project)
        unknown = visitor.get("/api/v1/no-such-route").json()["error"]
        client.post("/api/v1/profile/unpublish")
        error = _error(visitor.get(f"{PUBLIC}/{slug}"), 404, "NOT_FOUND")
        assert {k: v for k, v in error.items() if k != "request_id"} == {
            k: v for k, v in unknown.items() if k != "request_id"
        }

    def test_republishing_shows_the_same_projects(self, client, visitor, slug):
        a, b, c = (_published(client, title=t) for t in "ABC")
        _feature(client, b, a)
        before = _public(visitor, slug)
        client.post("/api/v1/profile/unpublish")
        client.post("/api/v1/profile/publish")
        assert _public(visitor, slug) == before
        assert _ids(before["featured"]) == [b["id"], a["id"]]
        assert _ids(before["other"]) == [c["id"]]


class TestWhitelist:
    def test_exact_keys_and_no_private_fields(self, client, visitor, slug, db_session):
        featured = _published(client, title="F", **SECRET_TEXT)
        _published(client, title="O", **SECRET_TEXT)
        _feature(client, featured)
        resp = visitor.get(f"{PUBLIC}/{slug}")
        body = resp.json()
        assert [set(card) for card in body["featured"]] == [FEATURED_KEYS]
        assert [set(card) for card in body["other"]] == [CARD_KEYS]

        owner_id = db_session.execute(select(User.id).where(User.github_user_id == 10001))
        owner_id = str(owner_id.scalar_one())
        for leaked in [
            *SECRET_TEXT.values(),
            owner_id,
            "owner",
            "description",
            "contribution",
            "PUBLISHED",
            "PUBLIC",
            "PRIVATE",
            "status",
            "visibility",
            "created_at",
            "updated_at",
            "featured_position",
        ]:
            assert leaked not in resp.text, leaked


class TestQueryCount:
    def _count(self, visitor, slug: str, db_session) -> int:
        statements: list[str] = []

        def count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        # Listen on the connection the app's session uses in these tests.
        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            _public(visitor, slug)
        finally:
            event.remove(connection, "before_cursor_execute", count)
        return len(statements)

    def test_same_number_of_queries_for_1_and_30_projects(self, client, visitor, slug, db_session):
        _published(client, technologies=["Python"])
        one = self._count(visitor, slug, db_session)

        for i in range(29):
            _published(client, title=f"P{i}", technologies=[f"T{i}-{n}" for n in range(5)])
        projects = client.get(PROJECTS).json()["items"]
        assert len(projects) == 30
        _feature(client, *projects[:3])
        body = _public(visitor, slug)
        assert len(body["featured"]) == 3 and len(body["other"]) == 27

        thirty = self._count(visitor, slug, db_session)
        # Profile, projects, technologies: also rules out a listener that never fired.
        assert thirty == one == 3
