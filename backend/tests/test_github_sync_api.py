"""POST /integrations/github/repositories/{id}/sync (ADR-018, step 6.2): a manual
sync of a linked repository; the active job reused, the pause per repository, the
user's budget, ownership, and races with another sync and with a link."""

import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.github import service as github_service
from app.github.budget import UserRequestBudget
from app.models.github import GitHubRepository, GitHubSyncJob, ProjectRepository
from app.models.projects import Project
from app.settings import settings
from tests import test_github_link_api as link_tests
from tests.test_github_link_api import (
    LOGIN,
    OTHER_GITHUB_ID,
    PROJECTS,
    T0,
    Env,
    _create,
    _error,
    _link,
    _new_client,
    _other_user,
    _repo,
    make_env,
)

REPOSITORIES = "/api/v1/integrations/github/repositories"
PAUSE = timedelta(minutes=10)


@pytest.fixture
def env(make_auth_client, db_session: Session) -> Env:
    return make_env(make_auth_client, db_session)


def _sync(http: TestClient, repository_id: int | str) -> httpx.Response:
    return http.post(f"{REPOSITORIES}/{repository_id}/sync")


def _linked(env: Env, repo_id: int = 1, **fields) -> str:
    env.github.add(_repo(repo_id, **fields))
    project_id = _create(env.http)
    assert _link(env.http, project_id, f"{LOGIN}/repo-{repo_id}").status_code == 200
    return project_id


def _jobs(db: Session, github_repo_id: int = 1) -> list[tuple[str, datetime]]:
    return list(
        db.execute(
            select(GitHubSyncJob.status, GitHubSyncJob.created_at)
            .join(GitHubRepository, GitHubRepository.id == GitHubSyncJob.github_repository_id)
            .where(GitHubRepository.github_repo_id == github_repo_id)
            .order_by(GitHubSyncJob.created_at)
        )
    )


def _finish_jobs(db: Session, status: str = "SYNCED") -> None:
    db.execute(GitHubSyncJob.__table__.update().values(status=status))
    db.commit()


# A new job.


def test_a_new_job_is_queued_once_the_pause_has_passed(env, db_session):
    _linked(env)
    _finish_jobs(db_session)
    requests = len(env.github.requests)
    env.clock.now = T0 + PAUSE

    resp = _sync(env.http, 1)

    assert resp.status_code == 202, resp.text
    assert resp.json() == {
        "status": "QUEUED",
        "last_success_at": None,
        "next_manual_sync_at": "2026-10-30T12:20:00Z",
    }
    assert _jobs(db_session) == [("SYNCED", T0), ("QUEUED", T0 + PAUSE)]
    # The link cost 1; a new job counts the worker's maximum, 7 (ADR-018).
    assert env.budget.spent(env.user.id, T0 + PAUSE) == 1 + 7
    # GitHub is not called in the request.
    assert len(env.github.requests) == requests


@pytest.mark.parametrize("status", ["QUEUED", "SYNCING"])
def test_an_active_job_is_returned_and_costs_nothing(env, db_session, status):
    project_id = _linked(env)
    db_session.execute(GitHubSyncJob.__table__.update().values(status=status))
    db_session.commit()
    env.clock.now = T0 + timedelta(minutes=1)

    resp = _sync(env.http, 1)

    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == status
    assert resp.json()["next_manual_sync_at"] == "2026-10-30T12:10:00Z"
    assert _jobs(db_session) == [(status, T0)]
    assert env.budget.spent(env.user.id, env.clock.now) == 1
    assert env.http.get(f"{PROJECTS}/{project_id}").json()["github"]["sync"] == resp.json()


# The pause.


@pytest.mark.parametrize(
    ("after", "seconds"),
    [(timedelta(0), 600), (timedelta(minutes=5), 300), (PAUSE - timedelta(seconds=1), 1)],
)
@pytest.mark.parametrize("status", ["SYNCED", "FAILED"])
def test_a_job_created_within_the_pause_is_too_soon(env, db_session, status, after, seconds):
    _linked(env)
    _finish_jobs(db_session, status)
    env.clock.now = T0 + after

    resp = _sync(env.http, 1)

    error = _error(resp, 429, "GITHUB_SYNC_TOO_SOON")
    assert error["details"] == {"retry_after_seconds": seconds}
    assert resp.headers["Retry-After"] == str(seconds)
    assert _jobs(db_session) == [(status, T0)]
    assert env.budget.spent(env.user.id, env.clock.now) == 1


def test_the_retry_wait_is_rounded_up(env, db_session):
    _linked(env)
    _finish_jobs(db_session)
    env.clock.now = T0 + timedelta(minutes=9, seconds=58, microseconds=500_000)

    resp = _sync(env.http, 1)

    assert _error(resp, 429, "GITHUB_SYNC_TOO_SOON")["details"] == {"retry_after_seconds": 2}
    assert resp.headers["Retry-After"] == "2"


def test_the_pause_is_per_repository_whoever_queued_the_job(env, make_auth_client, db_session):
    """Another user's link queued the job: the shared data was just requested."""
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    other, _ = _other_user(make_auth_client, db_session)
    _link(env.http, _create(env.http), f"{LOGIN}/repo-1")
    _finish_jobs(db_session)
    env.clock.now = T0 + timedelta(minutes=8)
    assert _link(other, _create(other), f"{LOGIN}/repo-1").status_code == 200
    _finish_jobs(db_session)
    env.clock.now = T0 + PAUSE

    error = _error(_sync(env.http, 1), 429, "GITHUB_SYNC_TOO_SOON")

    assert error["details"] == {"retry_after_seconds": 8 * 60}


def test_the_pause_is_configurable(env, db_session, monkeypatch):
    monkeypatch.setattr(settings, "github_manual_sync_cooldown_seconds", 60)
    _linked(env)
    _finish_jobs(db_session)
    env.clock.now = T0 + timedelta(minutes=1)

    assert _sync(env.http, 1).status_code == 202


# The user's budget.


def test_over_the_budget_no_job_is_queued(env, db_session):
    _linked(env)
    _finish_jobs(db_session)
    env.clock.now = T0 + PAUSE
    # 54 + the link's 1 = 55 spent: 5 left, a new job counts 7.
    env.budget.charge(env.user.id, 54, T0 - timedelta(minutes=45))

    resp = _sync(env.http, 1)

    error = _error(resp, 429, "GITHUB_USER_LIMIT_REACHED")
    assert error["details"] == {"retry_after_seconds": 5 * 60}
    assert resp.headers["Retry-After"] == "300"
    assert _jobs(db_session) == [("SYNCED", T0)]
    assert env.budget.spent(env.user.id, env.clock.now) == 55


def test_a_link_queues_without_counting_a_sync(env):
    """Jobs queued by link and import are not counted against the user (ADR-018)."""
    env.budget = UserRequestBudget(7)
    _linked(env)

    assert env.budget.spent(env.user.id, T0) == 1


# Who may sync.


@pytest.mark.parametrize("repository_id", ["0", "01", "-1", "+1", "1.0", "abc", "9" * 20])
def test_a_malformed_id_is_not_found(env, db_session, repository_id):
    _linked(env)

    _error(_sync(env.http, repository_id), 404, "NOT_FOUND")


def test_a_repository_none_of_the_users_projects_links_is_not_found(
    env, make_auth_client, db_session
):
    env.github.add(_repo(1), contributors=[[OTHER_GITHUB_ID]])
    other, _ = _other_user(make_auth_client, db_session)
    _link(other, _create(other), f"{LOGIN}/repo-1")
    _finish_jobs(db_session)
    env.clock.now = T0 + PAUSE

    # Stored and linked by another user; never stored at all.
    _error(_sync(env.http, 1), 404, "NOT_FOUND")
    _error(_sync(env.http, 2), 404, "NOT_FOUND")
    assert _jobs(db_session) == [("SYNCED", T0)]


def test_an_unlinked_repository_is_not_found(env, db_session):
    project_id = _linked(env)
    _finish_jobs(db_session)
    env.http.delete(f"{PROJECTS}/{project_id}/repository")
    env.clock.now = T0 + PAUSE

    _error(_sync(env.http, 1), 404, "NOT_FOUND")


@pytest.mark.parametrize("fact", ["unavailable", "no relation"])
def test_an_unavailable_repository_or_a_lost_relation_may_be_synced(env, db_session, fact):
    """A sync is how either recovers (ADR-017, ADR-018)."""
    _linked(env)
    _finish_jobs(db_session)
    if fact == "unavailable":
        db_session.execute(GitHubRepository.__table__.update().values(unavailable_since=T0))
    else:
        db_session.execute(ProjectRepository.__table__.update().values(relation="NONE"))
    db_session.commit()
    env.clock.now = T0 + PAUSE

    assert _sync(env.http, 1).status_code == 202


def test_requires_a_session_and_the_frontend_origin(env, make_auth_client, db_session):
    _linked(env)
    _finish_jobs(db_session)
    env.clock.now = T0 + PAUSE
    anonymous = _new_client(make_auth_client)
    no_origin = _new_client(make_auth_client, send_origin=False)
    no_origin.cookies = env.http.cookies

    _error(_sync(anonymous, 1), 401, "UNAUTHORIZED")
    _error(_sync(no_origin, 1), 403, "CSRF_ORIGIN_INVALID")
    assert _jobs(db_session) == [("SYNCED", T0)]


# Races: the repository row lock serializes manual syncs and links.


class TestSyncRaces:
    # The link tests' two-transaction helpers; not a base class, so pytest does
    # not collect their tests again here.
    races = link_tests.TestRaces()

    def _seed_linked(self, db_engine, repo_id: int) -> tuple[uuid.UUID, uuid.UUID]:
        """A user whose project links the repository; its one job is SYNCED at T0."""
        (user_id,), (project_id, _) = self.races._seed(db_engine, users=1)
        with Session(db_engine) as db:
            self.races._store(db, user_id, project_id, repo_id)
            db.execute(GitHubSyncJob.__table__.update().values(status="SYNCED"))
            db.commit()
        return user_id, project_id

    def _request(self, budget: UserRequestBudget, user_id, repo_id: int, now: datetime):
        return lambda db: github_service.request_sync(db, user_id, repo_id, budget=budget, now=now)

    def _statuses(self, db_engine, github_repo_id: int) -> list[str]:
        with db_engine.connect() as conn:
            return list(
                conn.execute(
                    select(GitHubSyncJob.status)
                    .join(
                        GitHubRepository,
                        GitHubRepository.id == GitHubSyncJob.github_repository_id,
                    )
                    .where(GitHubRepository.github_repo_id == github_repo_id)
                    .order_by(GitHubSyncJob.created_at)
                ).scalars()
            )

    def test_two_manual_syncs_queue_one_job_and_charge_once(self, db_engine):
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        user_id, _ = self._seed_linked(db_engine, repo_id)
        budget = UserRequestBudget(60)
        now = T0 + PAUSE
        try:
            result = self.races._race(
                db_engine,
                self._request(budget, user_id, repo_id, now),
                self._request(budget, user_id, repo_id, now),
                "commit",
            )
            assert result == {"ok": True}
            assert self._statuses(db_engine, repo_id) == ["SYNCED", "QUEUED"]
            assert budget.spent(user_id, now) == 7
        finally:
            self.races._cleanup(db_engine, [user_id], repo_id)

    def test_the_pause_holds_when_the_first_job_finished_before_the_commit(self, db_engine):
        """Without the row lock the second request would read the old job, find no
        active one in the index (the new job is already finished) and queue a
        second job within the pause. With it, it reads the new job."""
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        user_id, _ = self._seed_linked(db_engine, repo_id)
        budget = UserRequestBudget(60)
        now = T0 + PAUSE
        try:

            def sync_and_finish(db: Session) -> None:
                repository_id = self._request(budget, user_id, repo_id, now)(db)
                db.execute(
                    GitHubSyncJob.__table__.update()
                    .where(GitHubSyncJob.github_repository_id == repository_id)
                    .values(status="SYNCED")
                )

            result = self.races._race(
                db_engine, sync_and_finish, self._request(budget, user_id, repo_id, now), "commit"
            )
            assert isinstance(result.get("error"), AppError), result
            assert result["error"].code == "GITHUB_SYNC_TOO_SOON"
            assert self._statuses(db_engine, repo_id) == ["SYNCED", "SYNCED"]
            assert budget.spent(user_id, now) == 7
        finally:
            self.races._cleanup(db_engine, [user_id], repo_id)

    def test_a_manual_sync_waits_for_a_link_and_reuses_its_job(self, db_engine):
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        user_id, project_id = self._seed_linked(db_engine, repo_id)
        budget = UserRequestBudget(60)
        now = T0 + PAUSE
        try:
            # Linking the project again holds the repository row until the commit.
            def relink(db: Session) -> None:
                project = db.get(Project, project_id)
                checked = self.races._checked(repo_id, "OWNER")
                github_service.store_link(db, project, checked, now)

            result = self.races._race(
                db_engine, relink, self._request(budget, user_id, repo_id, now), "commit"
            )
            assert result == {"ok": True}
            # The link queued the job; the manual sync returned it for free.
            assert self._statuses(db_engine, repo_id) == ["SYNCED", "QUEUED"]
            assert budget.spent(user_id, now) == 0
        finally:
            self.races._cleanup(db_engine, [user_id], repo_id)

    def test_over_the_budget_the_job_is_rolled_back(self, db_engine):
        repo_id = 800_000_000 + uuid.uuid4().int % 1_000_000
        user_id, _ = self._seed_linked(db_engine, repo_id)
        budget = UserRequestBudget(7)
        budget.charge(user_id, 1, T0)
        now = T0 + PAUSE
        try:
            with Session(db_engine) as db:
                with pytest.raises(AppError) as exc:
                    self._request(budget, user_id, repo_id, now)(db)
                db.rollback()
            assert exc.value.code == "GITHUB_USER_LIMIT_REACHED"
            assert self._statuses(db_engine, repo_id) == ["SYNCED"]
        finally:
            self.races._cleanup(db_engine, [user_id], repo_id)
