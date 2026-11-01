"""The sync processor (ADR-018, step 6.4): metadata and languages read from a
mocked GitHub and stored one category at a time, and the job's outcome
through the worker."""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from app.github import service as github_service
from app.github.client import (
    GitHubApiClient,
    GitHubCredentialsRejected,
    GitHubMoved,
    GitHubNotFound,
    GitHubRateLimited,
    GitHubUnavailable,
    GitHubUnexpected,
    RateLimitPause,
    RateLimitState,
)
from app.github.sync import make_processor, sync_repository
from app.github.worker import SyncWorker
from app.models.github import (
    GitHubRepository,
    GitHubSyncCategoryStatus,
    GitHubSyncJob,
    ProjectRepository,
)
from app.models.identity import User
from tests.test_github_constraints import _link, _project, _repository

T0 = datetime(2026, 11, 1, 12, 0)
EARLIER = T0 - timedelta(days=2)
REPO_ID = 4242
OWNER_ID, OWNER = 10001, "testuser"


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


def _github_repo(name: str = "new-name", owner: str = OWNER, owner_id: int = OWNER_ID, **fields):
    return {
        "id": REPO_ID,
        "name": name,
        "full_name": f"{owner}/{name}",
        "owner": {"login": owner, "id": owner_id, "type": "User"},
        "private": False,
        "html_url": f"https://github.com/{owner}/{name}",
        "description": "From GitHub",
        "fork": False,
        "archived": False,
        "pushed_at": "2026-10-31T09:30:00Z",
        **fields,
    }


class FakeGitHub:
    """The repository by id, its languages and contributor pages by full name.
    fail[kind] answers instead, for kind in metadata, languages, contributors."""

    def __init__(self) -> None:
        self.repo = _github_repo()
        self.languages = {"Python": 1200, "Shell": 30}
        self.contributors: list[list[int]] | None = None
        self.fail: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[str] = []
        self.during: Callable[[], None] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        full_name = self.repo["full_name"]
        if path == f"/repositories/{REPO_ID}":
            kind = "metadata"
        elif path == f"/repos/{full_name}/languages":
            kind = "languages"
        elif path == f"/repos/{full_name}/contributors":
            kind = "contributors"
        else:
            raise AssertionError(f"unexpected request {path}")
        self.requests.append(kind)
        if self.during is not None:
            self.during()
        if kind in self.fail:
            return self.fail[kind](request)
        if kind == "metadata":
            return httpx.Response(200, json=self.repo)
        if kind == "languages":
            return httpx.Response(200, json=self.languages)
        if self.contributors is None:
            return httpx.Response(204)
        page = int(request.url.params["page"])
        headers = {}
        if page < len(self.contributors):
            headers["link"] = f'<https://api.github.com/x?page={page + 1}>; rel="next"'
        body = [{"id": user_id, "login": f"u{user_id}"} for user_id in self.contributors[page - 1]]
        return httpx.Response(200, json=body, headers=headers)


def _status(code: int, **headers) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(code, json={"message": "x"}, headers=headers)


def _timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


RATE_LIMITED = _status(
    403,
    **{
        "x-ratelimit-remaining": "0",
        "x-ratelimit-reset": str(int((T0 - datetime(1970, 1, 1)).total_seconds()) + 600),
    },
)
MOVED = _status(301, location="https://api.github.com/repositories/777")

FAILURES = [
    (_status(404), GitHubNotFound, "NOT_FOUND"),
    (_status(502), GitHubUnavailable, "GITHUB_UNAVAILABLE"),
    (_timeout, GitHubUnavailable, "GITHUB_UNAVAILABLE"),
    (MOVED, GitHubMoved, "UNEXPECTED_STATUS"),
    (_status(418), GitHubUnexpected, "UNEXPECTED_STATUS"),
]


class Env:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.github = FakeGitHub()
        self.clock = Clock()
        self.client = GitHubApiClient(
            httpx.Client(transport=httpx.MockTransport(self.github)),
            "sync_client_id",
            "sync_client_secret",
            rate_limits=RateLimitState(),
            pause=RateLimitPause(),
            now=self.clock,
        )
        self.owner = _user(db, OWNER_ID)
        self.repository = _repository(
            db,
            github_repo_id=REPO_ID,
            owner_github_id=OWNER_ID,
            owner_login=OWNER,
            name="old-name",
            description="Old",
            is_archived=False,
            languages={"Old": 1},
            unavailable_since=EARLIER,
        )
        self.project = _project(db, self.owner)
        self.link = _link(db, self.project, self.repository, "OWNER")
        db.commit()

    def sync(self) -> None:
        sync_repository(self.db, self.client, self.repository.id, self.clock)

    def row(self) -> GitHubRepository:
        self.db.expire_all()
        return self.db.get(GitHubRepository, self.repository.id)

    def categories(self) -> dict[str, tuple]:
        rows = self.db.execute(
            select(
                GitHubSyncCategoryStatus.category,
                GitHubSyncCategoryStatus.last_success_at,
                GitHubSyncCategoryStatus.last_error,
                GitHubSyncCategoryStatus.last_error_at,
            ).where(GitHubSyncCategoryStatus.github_repository_id == self.repository.id)
        ).all()
        return {category: tuple(rest) for category, *rest in rows}

    def seed_categories(self, **errors: str) -> None:
        for category in ("metadata", "languages"):
            self.db.add(
                GitHubSyncCategoryStatus(
                    github_repository_id=self.repository.id,
                    category=category,
                    last_success_at=EARLIER,
                    last_error=errors.get(category),
                    last_error_at=EARLIER if category in errors else None,
                )
            )
        self.db.commit()


def _user(db: Session, github_user_id: int) -> User:
    user = User(github_user_id=github_user_id, github_login=f"user{github_user_id}")
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def worker_log(caplog, monkeypatch):
    # alembic's fileConfig (db_engine fixture) disables loggers that existed before it ran.
    monkeypatch.setattr(logging.getLogger("app.github.sync"), "disabled", False)
    caplog.set_level(logging.INFO, logger="app.github.sync")
    return caplog


@pytest.fixture
def env(db_session) -> Env:
    return Env(db_session)


# ---------------------------------------------------------------------------
# Both categories
# ---------------------------------------------------------------------------


def test_metadata_and_languages_are_stored(env):
    env.github.repo = _github_repo(
        name="new-name",
        description="Desc",
        archived=True,
        fork=True,
        parent={"full_name": "upstream/project"},
        pushed_at="2026-10-31T09:30:00+03:00",
    )
    env.seed_categories(metadata="NOT_FOUND", languages="GITHUB_UNAVAILABLE")

    env.sync()

    row = env.row()
    assert (row.owner_login, row.name, row.full_name) == (OWNER, "new-name", f"{OWNER}/new-name")
    assert row.html_url == f"https://github.com/{OWNER}/new-name"
    assert (row.description, row.is_archived, row.is_fork) == ("Desc", True, True)
    assert row.parent_full_name == "upstream/project"
    assert row.pushed_at == datetime(2026, 10, 31, 6, 30)
    assert row.languages == {"Python": 1200, "Shell": 30}
    assert (row.unavailable_since, row.updated_at) == (None, T0)
    assert env.categories() == {
        "metadata": (T0, None, None),
        "languages": (T0, None, None),
    }


def test_metadata_is_read_by_id_and_languages_under_the_current_name(env):
    env.sync()

    assert env.github.requests == ["metadata", "languages"]


def test_a_transferred_repository_takes_its_new_owner(env):
    env.github.repo = _github_repo(name="moved", owner="neworg", owner_id=99)

    env.sync()

    row = env.row()
    assert (row.owner_github_id, row.owner_login, row.full_name) == (99, "neworg", "neworg/moved")


def test_empty_languages_are_stored_as_an_empty_object(env):
    env.github.languages = {}

    env.sync()

    assert env.row().languages == {}


def test_a_second_sync_writes_the_same(env):
    env.sync()
    first = (env.row().languages, env.categories())
    env.sync()

    assert (env.row().languages, env.categories()) == first


def test_no_transaction_is_open_while_github_answers(env):
    seen = []
    env.github.during = lambda: seen.append(env.db.in_transaction())

    env.sync()

    assert seen == [False, False]


def test_a_deleted_repository_is_not_requested(env):
    sync_repository(env.db, env.client, uuid.uuid4(), env.clock)

    assert env.github.requests == []


# ---------------------------------------------------------------------------
# A failed category
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("answer", "exc", "label"), FAILURES)
def test_a_failed_metadata_read_changes_nothing(env, answer, exc, label):
    env.seed_categories()
    env.github.fail["metadata"] = answer
    env.clock.now = T0 + timedelta(minutes=1)

    with pytest.raises(exc):
        env.sync()

    row = env.row()
    assert (row.name, row.description, row.languages) == ("old-name", "Old", {"Old": 1})
    assert row.unavailable_since == EARLIER
    assert env.github.requests == ["metadata"]
    assert env.categories() == {
        "metadata": (EARLIER, label, T0 + timedelta(minutes=1)),
        "languages": (EARLIER, None, None),
    }


@pytest.mark.parametrize(("answer", "exc", "label"), FAILURES)
def test_a_failed_languages_read_keeps_the_metadata(env, answer, exc, label):
    env.seed_categories()
    env.github.fail["languages"] = answer

    with pytest.raises(exc):
        env.sync()

    row = env.row()
    assert (row.name, row.description, row.languages) == ("new-name", "From GitHub", {"Old": 1})
    assert env.categories() == {
        "metadata": (T0, None, None),
        "languages": (EARLIER, label, T0),
    }


def test_a_first_failure_creates_the_category_row(env):
    env.github.fail["languages"] = _status(502)

    with pytest.raises(GitHubUnavailable):
        env.sync()

    assert env.categories()["languages"] == (None, "GITHUB_UNAVAILABLE", T0)


@pytest.mark.parametrize("category", ["metadata", "languages"])
@pytest.mark.parametrize(
    ("answer", "exc"),
    [(RATE_LIMITED, GitHubRateLimited), (_status(401), GitHubCredentialsRejected)],
)
def test_a_rate_limit_or_401_records_no_error(env, category, answer, exc):
    env.seed_categories()
    env.github.fail[category] = answer

    with pytest.raises(exc):
        env.sync()

    assert env.categories()[category] == (EARLIER, None, None)


@pytest.mark.parametrize("languages", [{"C\x00": 1}, {"Go": -1}, []])
def test_malformed_languages_keep_the_stored_ones(env, languages):
    env.github.languages = languages

    with pytest.raises(GitHubUnavailable):
        env.sync()

    assert env.row().languages == {"Old": 1}


# ---------------------------------------------------------------------------
# Through the worker and the cabinet
# ---------------------------------------------------------------------------


def _queued_job(env: Env, **fields) -> uuid.UUID:
    job = GitHubSyncJob(
        github_repository_id=env.repository.id,
        scheduled_at=T0,
        created_at=T0 - timedelta(minutes=5),
        updated_at=T0 - timedelta(minutes=5),
        **fields,
    )
    env.db.add(job)
    env.db.commit()
    return job.id


def _run(env: Env) -> None:
    SyncWorker(env.client, make_processor(env.client, env.clock), now=env.clock).run_once(env.db)


def _job(env: Env, job_id: uuid.UUID) -> tuple:
    row = env.db.execute(
        select(GitHubSyncJob.status, GitHubSyncJob.attempt_count, GitHubSyncJob.last_error).where(
            GitHubSyncJob.id == job_id
        )
    ).one()
    return tuple(row)


def test_a_synced_job_shows_in_the_cabinet(env):
    job_id = _queued_job(env)

    _run(env)

    assert _job(env, job_id) == ("SYNCED", 1, None)
    github = github_service.project_github(env.db, env.project.id, T0)
    assert github.synced_at.replace(tzinfo=None) == T0
    assert [(item.name, item.bytes) for item in github.languages] == [
        ("Python", 1200),
        ("Shell", 30),
    ]
    assert (github.sync.status, github.full_name, github.unavailable) == (
        "SYNCED",
        f"{OWNER}/new-name",
        False,
    )


def test_partial_success_retries_the_job_and_keeps_synced_at(env):
    env.seed_categories()
    job_id = _queued_job(env)
    env.github.fail["languages"] = _status(502)

    _run(env)

    assert _job(env, job_id) == ("QUEUED", 1, "GITHUB_UNAVAILABLE")
    github = github_service.project_github(env.db, env.project.id, T0)
    # The data is as old as its oldest category.
    assert github.synced_at.replace(tzinfo=None) == EARLIER
    assert github.full_name == f"{OWNER}/new-name"


def test_a_missing_repository_is_retried_with_not_found(env):
    job_id = _queued_job(env)
    env.github.fail["metadata"] = _status(404)

    _run(env)

    assert _job(env, job_id) == ("QUEUED", 1, "NOT_FOUND")


def test_a_rate_limit_mid_job_keeps_the_attempt(env):
    job_id = _queued_job(env, attempt_count=2)
    env.github.fail["languages"] = RATE_LIMITED

    _run(env)

    assert _job(env, job_id) == ("QUEUED", 2, None)
    assert env.row().name == "new-name"


def test_the_processor_uses_the_given_client(env):
    job_id = _queued_job(env)
    other = FakeGitHub()
    other.fail["metadata"] = _status(500)
    env.client = GitHubApiClient(
        httpx.Client(transport=httpx.MockTransport(other)),
        "id",
        "secret",
        rate_limits=RateLimitState(),
        pause=RateLimitPause(),
        now=env.clock,
    )

    _run(env)

    assert other.requests == ["metadata"]
    assert _job(env, job_id)[2] == "GITHUB_UNAVAILABLE"


# ---------------------------------------------------------------------------
# The relation of every link (ADR-017)
# ---------------------------------------------------------------------------

OTHER_ID, STRANGER_ID = 20002, 30003


def _add_link(env: Env, github_user_id: int, relation: str) -> uuid.UUID:
    user = _user(env.db, github_user_id)
    link = _link(env.db, _project(env.db, user), env.repository, relation)
    link.relation_checked_at = EARLIER
    env.db.commit()
    return link.id


def _relations(env: Env) -> dict[uuid.UUID, tuple[str, datetime]]:
    rows = env.db.execute(
        select(
            ProjectRepository.id, ProjectRepository.relation, ProjectRepository.relation_checked_at
        ).where(ProjectRepository.github_repository_id == env.repository.id)
    ).all()
    return {link_id: (relation, checked) for link_id, relation, checked in rows}


def test_the_owner_needs_no_contributor_pages(env):
    env.db.execute(update(ProjectRepository).values(relation="NONE"))
    env.db.commit()

    env.sync()

    assert env.github.requests == ["metadata", "languages"]
    assert _relations(env) == {env.link.id: ("OWNER", T0)}


def test_every_link_is_recomputed_with_one_pass_over_the_pages(env):
    contributor = _add_link(env, OTHER_ID, "NONE")
    stranger = _add_link(env, STRANGER_ID, "CONTRIBUTOR")
    env.github.contributors = [[1, 2], [OTHER_ID, 3]]

    env.sync()

    assert _relations(env) == {
        env.link.id: ("OWNER", T0),
        contributor: ("CONTRIBUTOR", T0),
        stranger: ("NONE", T0),
    }
    assert env.github.requests == ["metadata", "languages", "contributors", "contributors"]


def test_pages_stop_once_every_developer_is_found(env):
    contributor = _add_link(env, OTHER_ID, "NONE")
    env.github.contributors = [[OTHER_ID], [1], [2]]

    env.sync()

    assert _relations(env)[contributor][0] == "CONTRIBUTOR"
    assert env.github.requests.count("contributors") == 1


def test_at_most_five_pages_and_seven_requests(env):
    contributor = _add_link(env, OTHER_ID, "CONTRIBUTOR")
    env.github.contributors = [[n] for n in range(1, 6)] + [[OTHER_ID]]

    env.sync()

    assert _relations(env)[contributor][0] == "NONE"
    assert env.github.requests.count("contributors") == 5
    # The manual sync charges the user 7 (ADR-018): the most a job can make.
    assert env.client.requests_sent == 7


def test_an_empty_contributor_list_is_none(env):
    contributor = _add_link(env, OTHER_ID, "CONTRIBUTOR")
    env.github.contributors = None

    env.sync()

    assert _relations(env)[contributor][0] == "NONE"


def test_a_transfer_changes_the_owners_relation(env):
    env.github.repo = _github_repo(owner="neworg", owner_id=99)
    env.github.contributors = [[OWNER_ID]]

    env.sync()

    assert _relations(env) == {env.link.id: ("CONTRIBUTOR", T0)}


def test_a_new_owner_after_a_transfer_is_owner(env):
    new_owner = _add_link(env, OTHER_ID, "NONE")
    env.github.repo = _github_repo(owner="other", owner_id=OTHER_ID)
    env.github.contributors = [[1]]

    env.sync()

    assert _relations(env) == {env.link.id: ("NONE", T0), new_owner: ("OWNER", T0)}


@pytest.mark.parametrize("answer", [_status(502), _timeout, RATE_LIMITED, _status(404)])
def test_unread_contributors_keep_the_relations(env, worker_log, answer):
    contributor = _add_link(env, OTHER_ID, "CONTRIBUTOR")
    job_id = _queued_job(env)
    env.github.fail["contributors"] = answer

    _run(env)

    assert _relations(env) == {
        env.link.id: ("OWNER", T0),
        contributor: ("CONTRIBUTOR", EARLIER),
    }
    assert _job(env, job_id) == ("SYNCED", 1, None)
    assert any("contributors not read" in r.getMessage() for r in worker_log.records)


def test_rejected_credentials_on_contributors_stop_the_worker(env):
    contributor = _add_link(env, OTHER_ID, "CONTRIBUTOR")
    env.github.fail["contributors"] = _status(401)

    with pytest.raises(GitHubCredentialsRejected):
        env.sync()

    assert _relations(env)[contributor] == ("CONTRIBUTOR", EARLIER)


def test_no_relation_is_recomputed_when_a_category_fails(env):
    env.db.execute(update(ProjectRepository).values(relation_checked_at=EARLIER))
    env.db.commit()
    env.github.fail["languages"] = _status(502)

    with pytest.raises(GitHubUnavailable):
        env.sync()

    assert _relations(env) == {env.link.id: ("OWNER", EARLIER)}


def test_a_link_replaced_during_the_sync_is_left_alone(env):
    contributor = _add_link(env, OTHER_ID, "CONTRIBUTOR")
    project_id = env.db.scalar(
        select(ProjectRepository.project_id).where(ProjectRepository.id == contributor)
    )
    env.github.contributors = [[1]]

    def relink():
        if env.github.requests[-1] != "contributors":
            return
        env.db.execute(delete(ProjectRepository).where(ProjectRepository.id == contributor))
        env.db.execute(
            insert(ProjectRepository).values(
                project_id=project_id,
                owner_id=env.db.scalar(select(User.id).where(User.github_user_id == OTHER_ID)),
                github_repository_id=env.repository.id,
                relation="CONTRIBUTOR",
                relation_checked_at=T0 - timedelta(minutes=1),
            )
        )
        env.db.commit()

    env.github.during = relink
    env.sync()

    relations = _relations(env)
    assert contributor not in relations
    assert sorted(relations.values()) == [
        ("CONTRIBUTOR", T0 - timedelta(minutes=1)),
        ("OWNER", T0),
    ]


def test_links_of_other_repositories_are_untouched(env):
    other_repository = _repository(env.db)
    user = _user(env.db, OTHER_ID)
    other = _link(env.db, _project(env.db, user), other_repository, "CONTRIBUTOR")
    env.db.commit()

    env.sync()

    assert (
        env.db.scalar(
            select(ProjectRepository.relation_checked_at).where(ProjectRepository.id == other.id)
        )
        != T0
    )


def test_no_links_need_no_contributor_pages(env):
    env.db.execute(delete(ProjectRepository))
    env.db.commit()

    env.sync()

    assert env.github.requests == ["metadata", "languages"]
