"""`github` in the items of GET /projects (step 5.6, ADR-017): the stored full_name and
html_url of each project's linked repository, read in one query, without GitHub."""

import uuid

import pytest
from sqlalchemy import event, update
from sqlalchemy.orm import Session

from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.models.github import GitHubRepository, ProjectRepository
from tests.test_github_link_api import (
    LOGIN,
    OTHER_GITHUB_ID,
    PROJECTS,
    T0,
    Env,
    _create,
    _link,
    _other_user,
    _repo,
    make_env,
)

REPOSITORIES = "/api/v1/integrations/github/repositories"
SUMMARY_KEYS = {
    "id",
    "status",
    "visibility",
    "title",
    "summary",
    "technologies",
    "featured_position",
    "github",
}


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    return make_env(make_auth_client, db_session)


def _github(full_name: str) -> dict:
    return {"full_name": full_name, "html_url": f"https://github.com/{full_name}"}


def _items(env: Env) -> dict[str, dict]:
    resp = env.http.get(PROJECTS)
    assert resp.status_code == 200, resp.text
    return {item["id"]: item for item in resp.json()["items"]}


def _linked(env: Env, repo_id: int, **project_fields) -> str:
    env.github.add(_repo(repo_id))
    project_id = _create(env.http, **project_fields)
    resp = _link(env.http, project_id, f"{LOGIN}/repo-{repo_id}")
    assert resp.status_code == 200, resp.text
    return project_id


def _published(env: Env, **fields) -> str:
    project_id = _create(
        env.http,
        title=fields.pop("title", "Shop"),
        summary="An online shop",
        role="Backend",
        contribution="The API",
        technologies=["Python"],
        **fields,
    )
    assert env.http.post(f"{PROJECTS}/{project_id}/publish").status_code == 200
    return project_id


def test_project_without_a_link_has_null(env):
    project_id = _create(env.http, title="Shop")

    item = _items(env)[project_id]

    assert set(item) == SUMMARY_KEYS
    assert item["github"] is None


def test_linked_project_has_only_full_name_and_html_url(env):
    project_id = _linked(env, 1)

    github = _items(env)[project_id]["github"]

    assert github == _github(f"{LOGIN}/repo-1")


def test_imported_project_has_its_repository(env):
    env.github.add(_repo(7, name="payments"))
    resp = env.http.post(f"{REPOSITORIES}/7/import")
    assert resp.status_code == 201, resp.text

    item = _items(env)[resp.json()["id"]]

    assert item["status"] == "DRAFT"
    assert item["github"] == _github(f"{LOGIN}/payments")


def test_replacing_the_repository_shows_the_new_one(env):
    project_id = _linked(env, 1)
    env.github.add(_repo(2))
    assert _link(env.http, project_id, f"{LOGIN}/repo-2").status_code == 200

    assert _items(env)[project_id]["github"] == _github(f"{LOGIN}/repo-2")


def test_unlinked_project_has_null_again(env):
    project_id = _linked(env, 1)
    assert env.http.delete(f"{PROJECTS}/{project_id}/repository").status_code == 200

    assert _items(env)[project_id]["github"] is None


def test_each_project_has_its_own_repository(env):
    first = _linked(env, 1)
    second = _linked(env, 2)
    plain = _create(env.http)

    items = _items(env)

    assert items[first]["github"] == _github(f"{LOGIN}/repo-1")
    assert items[second]["github"] == _github(f"{LOGIN}/repo-2")
    assert items[plain]["github"] is None


def test_every_project_state_shows_the_repository(env):
    draft = _linked(env, 1)
    public = _published(env, title="Public")
    hidden = _published(env, title="Hidden")
    archived = _published(env, title="Archived")
    resp = env.http.post(f"{PROJECTS}/{hidden}/visibility", json={"visibility": "PRIVATE"})
    assert resp.status_code == 200
    assert env.http.post(f"{PROJECTS}/{archived}/archive").status_code == 200
    for repo_id, project_id in [(2, public), (3, hidden), (4, archived)]:
        env.github.add(_repo(repo_id))
        assert _link(env.http, project_id, f"{LOGIN}/repo-{repo_id}").status_code == 200

    items = _items(env)

    assert [items[p]["status"] for p in (draft, public, hidden, archived)] == [
        "DRAFT",
        "PUBLISHED",
        "PUBLISHED",
        "ARCHIVED",
    ]
    assert items[hidden]["visibility"] == "PRIVATE"
    for repo_id, project_id in enumerate((draft, public, hidden, archived), start=1):
        assert items[project_id]["github"] == _github(f"{LOGIN}/repo-{repo_id}")


def test_another_users_link_to_the_same_repository_is_not_mine(env, make_auth_client, db_session):
    other_http, _ = _other_user(make_auth_client, db_session)
    # The other user contributed to the repository.
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    theirs = _create(other_http, title="Theirs")
    assert _link(other_http, theirs, f"{LOGIN}/repo-1").status_code == 200
    mine = _create(env.http, title="Mine")

    items = _items(env)

    assert list(items) == [mine]
    assert items[mine]["github"] is None
    their_items = other_http.get(PROJECTS).json()["items"]
    assert [(i["id"], i["github"]) for i in their_items] == [(theirs, _github(f"{LOGIN}/repo-1"))]


def test_both_users_see_their_own_link_to_a_shared_repository(env, make_auth_client, db_session):
    other_http, _ = _other_user(make_auth_client, db_session)
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    mine = _linked(env, 1)
    theirs = _create(other_http)
    assert _link(other_http, theirs, f"{LOGIN}/repo-1").status_code == 200

    assert list(_items(env)) == [mine]
    assert _items(env)[mine]["github"] == _github(f"{LOGIN}/repo-1")


def test_lookup_returns_only_the_owners_links_of_the_given_projects(
    env, make_auth_client, db_session
):
    other_http, other = _other_user(make_auth_client, db_session)
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    first = uuid.UUID(_linked(env, 1))
    second = uuid.UUID(_linked(env, 2))
    theirs = uuid.UUID(_create(other_http))
    assert _link(other_http, str(theirs), f"{LOGIN}/repo-1").status_code == 200

    # The route passes only the user's own ids; the query keeps both rules on its own.
    mine = github_service.linked_repositories(db_session, env.user.id, [first, second, theirs])
    only_second = github_service.linked_repositories(db_session, env.user.id, [second])
    their_view = github_service.linked_repositories(db_session, other.id, [first, theirs])

    assert set(mine) == {first, second}
    assert set(only_second) == {second}
    assert {key: value.full_name for key, value in their_view.items()} == {
        theirs: f"{LOGIN}/repo-1"
    }


def test_unavailable_repository_is_still_shown(env, db_session):
    project_id = _linked(env, 1)
    db_session.execute(update(GitHubRepository).values(unavailable_since=T0))
    db_session.commit()

    assert _items(env)[project_id]["github"] == _github(f"{LOGIN}/repo-1")
    assert env.http.get(f"{PROJECTS}/{project_id}").json()["github"]["unavailable"] is True


def test_lost_relation_is_still_shown(env, db_session):
    project_id = _linked(env, 1)
    db_session.execute(update(ProjectRepository).values(relation="NONE"))
    db_session.commit()

    assert _items(env)[project_id]["github"] == _github(f"{LOGIN}/repo-1")


def test_stored_values_are_shown_without_calling_github(env):
    project_id = _linked(env, 1, title="Shop")
    env.github.requests.clear()
    # GitHub now has another name; the list shows the stored one and asks nothing.
    env.github.add(_repo(1, name="renamed"))

    assert _items(env)[project_id]["github"] == _github(f"{LOGIN}/repo-1")
    assert env.github.requests == []


def test_full_project_response_is_unchanged(env):
    project_id = _linked(env, 1)

    github = env.http.get(f"{PROJECTS}/{project_id}").json()["github"]

    assert {"relation", "languages", "sync", "github_repo_id"} <= set(github)


class TestQueryCount:
    def _statements(self, env: Env, db_session: Session) -> int:
        seen: list[str] = []

        def count(conn, cursor, statement, *args) -> None:
            seen.append(statement)

        connection = db_session.connection()
        event.listen(connection, "before_cursor_execute", count)
        try:
            resp = env.http.get(PROJECTS)
        finally:
            event.remove(connection, "before_cursor_execute", count)
        assert resp.status_code == 200, resp.text
        return len(seen)

    def test_same_number_of_queries_for_1_and_30_projects(self, env, db_session):
        # 30 links read GitHub 30 times; the default budget of 60 would be the limit.
        env.budget = UserRequestBudget(1000)
        _create(env.http, technologies=["Python"])
        one_plain = self._statements(env, db_session)

        env.http.delete(f"{PROJECTS}/{_items(env).popitem()[0]}")
        _linked(env, 1, technologies=["Python"])
        one_linked = self._statements(env, db_session)

        for repo_id in range(2, 31):
            _linked(env, repo_id, technologies=[f"T{repo_id}", "Go"])
        items = _items(env)
        assert len(items) == 30 and all(item["github"] for item in items.values())
        thirty_linked = self._statements(env, db_session)

        for project_id in list(items)[::2]:
            env.http.delete(f"{PROJECTS}/{project_id}/repository")
        assert sum(item["github"] is None for item in _items(env).values()) == 15
        thirty_mixed = self._statements(env, db_session)

        for project_id in list(items)[1::2]:
            env.http.delete(f"{PROJECTS}/{project_id}/repository")
        assert all(item["github"] is None for item in _items(env).values())
        thirty_plain = self._statements(env, db_session)

        assert one_plain == one_linked == thirty_linked == thirty_mixed == thirty_plain
