"""Account deletion (ADR-0028, step 9.7a): DELETE /auth/me, the cleanup of expired
sessions at sign-in and the delete_user command for restores."""

import logging
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.clock import utcnow
from app.identity import delete_user
from app.identity import router as identity_router
from app.identity.service import create_session, get_or_create_user
from app.models.github import GitHubRepository, ProjectRepository
from app.models.identity import AuthSession, Profile, User
from app.models.projects import Project, ProjectScreenshot
from app.settings import settings
from tests.conftest import login, make_github_transport
from tests.test_github_constraints import _link, _repository
from tests.test_project_screenshots import _image, _upload

ME = "/api/v1/auth/me"
PROJECTS = "/api/v1/projects"


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", tmp_path)
    return tmp_path


@pytest.fixture
def client(auth_client):
    login(auth_client)
    return auth_client


@pytest.fixture
def other_client(client, make_auth_client):
    other = make_auth_client(make_github_transport(github_user_id=20002, github_login="other"))
    login(other)
    return other


def _user_id(db, github_user_id: int = 10001) -> uuid.UUID | None:
    return db.execute(
        select(User.id).where(User.github_user_id == github_user_id)
    ).scalar_one_or_none()


def _count(db, model, *where) -> int:
    return db.execute(select(func.count()).select_from(model).where(*where)).scalar_one()


def _project_with_screenshot(client) -> dict:
    project = client.post(PROJECTS, json={"title": "Shop"}).json()
    assert _upload(client, project, _image()).status_code == 201
    return project


def test_deletes_the_account_and_everything_it_owns(client, db_session, media_root):
    project = _project_with_screenshot(client)
    resp = client.patch(
        "/api/v1/profile",
        json={"contacts": [{"type": "TELEGRAM", "value": "@ann_dev"}]},
    )
    assert resp.status_code == 200, resp.text
    user_id = _user_id(db_session)

    resp = client.delete(ME)

    assert resp.status_code == 204
    assert _user_id(db_session) is None
    assert _count(db_session, Profile, Profile.user_id == user_id) == 0
    assert _count(db_session, Project, Project.owner_id == user_id) == 0
    assert _count(db_session, AuthSession, AuthSession.user_id == user_id) == 0
    assert _count(db_session, ProjectScreenshot) == 0
    assert list((media_root / "projects").glob("*/*")) == []
    assert not (media_root / "projects" / project["id"]).exists()


def test_clears_the_cookie_and_the_session_stops_working(client):
    resp = client.delete(ME)

    assert settings.session_cookie_name in resp.headers["set-cookie"]
    assert "Max-Age=0" in resp.headers["set-cookie"]
    assert client.get(ME).status_code == 401


def test_other_accounts_and_shared_repositories_stay(client, other_client, db_session):
    other_project = _project_with_screenshot(other_client)
    repository = _repository(db_session)
    for owner in (10001, 20002):
        project = Project(owner_id=_user_id(db_session, owner), title=f"Linked {owner}")
        db_session.add(project)
        db_session.flush()
        _link(db_session, project, repository)

    assert client.delete(ME).status_code == 204

    assert other_client.get(f"{PROJECTS}/{other_project['id']}").status_code == 200
    assert _count(db_session, ProjectScreenshot) == 1
    assert _count(db_session, GitHubRepository, GitHubRepository.id == repository.id) == 1
    assert _count(db_session, ProjectRepository) == 1


def test_needs_a_session(auth_client):
    assert auth_client.delete(ME).status_code == 401


def test_needs_the_frontend_origin(client, make_auth_client, db_session):
    token = client.cookies[settings.session_cookie_name]
    foreign = make_auth_client(headers={"Origin": "https://evil.example"})
    foreign.cookies.set(settings.session_cookie_name, token)

    resp = foreign.delete(ME)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"
    assert _user_id(db_session) is not None


def test_signing_in_again_starts_an_empty_account(client, db_session):
    _project_with_screenshot(client)
    old_id = _user_id(db_session)
    client.delete(ME)

    login(client)

    new_id = _user_id(db_session)
    assert new_id is not None and new_id != old_id
    assert client.get(PROJECTS).json()["items"] == []


def test_the_log_names_the_id_only(client, db_session, caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    monkeypatch.setattr(identity_router.logger, "disabled", False)
    caplog.set_level(logging.WARNING, logger=identity_router.logger.name)
    user_id = _user_id(db_session)

    client.delete(ME)

    [line] = [r.getMessage() for r in caplog.records if "account deleted" in r.getMessage()]
    assert line == f"account deleted user_id={user_id}"


def test_signing_in_removes_expired_sessions_of_every_user(auth_client, db_session):
    other, _ = get_or_create_user(db_session, 5100, "olga", None)
    expired = create_session(db_session, other.id)
    live = create_session(db_session, other.id)
    db_session.execute(
        AuthSession.__table__.update()
        .where(AuthSession.user_id == other.id)
        .where(AuthSession.token_hash == _hash(expired))
        .values(expires_at=utcnow() - timedelta(seconds=1))
    )

    login(auth_client)

    hashes = set(
        db_session.execute(
            select(AuthSession.token_hash).where(AuthSession.user_id == other.id)
        ).scalars()
    )
    assert hashes == {_hash(live)}


def _hash(token: str) -> str:
    from app.identity.service import hash_token

    return hash_token(token)


def test_the_command_deletes_restored_accounts_and_skips_unknown_ids(
    client, db_session, media_root
):
    _project_with_screenshot(client)
    user_id = _user_id(db_session)
    unknown = uuid.uuid4()

    lines = delete_user.run(db_session, [user_id, unknown])

    assert lines == [f"{user_id}: deleted, 1 files", f"{unknown}: no such account"]
    assert _user_id(db_session) is None
    assert list((media_root / "projects").glob("*/*")) == []


@pytest.mark.parametrize("argv", [[], ["not-a-uuid"]])
def test_the_command_needs_ids(argv, capsys):
    assert delete_user.main(argv) == 2
    assert "usage" in capsys.readouterr().out
