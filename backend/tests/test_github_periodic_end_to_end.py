"""Periodic syncs end to end (ADR-018, step 6.5), the way the process runs them:
main()'s wiring, sessions from SessionLocal, the real processor over a fake
GitHub, the period read from the environment, and an idle loop whose clock moves
only by the poll waits. Rows are committed, as in production."""

import logging
import threading
from datetime import datetime, timedelta

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.github import worker as worker_module
from app.github.client import GitHubApiClient, RateLimitPause, RateLimitState
from app.github.sync import make_processor
from app.github.worker import SyncWorker
from app.models.github import GitHubRepository, GitHubSyncJob
from app.models.identity import User
from app.models.projects import Project
from app.settings import Settings
from tests.test_github_constraints import _link, _owner, _repository_fields

T0 = datetime(2026, 11, 4, 16, 45)
PERIOD = 120
BATCH = 7
GITHUB_REPO_IDS = {"old": 910_001, "none": 910_002, "draft": 910_003}


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


class FakeGitHub:
    """/rate_limit with the budget of the manual check, and each repository by id."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.reads: list[int] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        reset = int((self.clock.now + timedelta(hours=1) - datetime(1970, 1, 1)).total_seconds())
        headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4988",
            "x-ratelimit-reset": str(reset),
            "x-ratelimit-used": "12",
            "x-ratelimit-resource": "core",
        }
        if path == "/rate_limit":
            core = {"limit": 5000, "remaining": 4988, "reset": reset, "used": 12}
            return httpx.Response(200, json={"resources": {"core": core}})
        if path.startswith("/repositories/"):
            repo_id = int(path.rsplit("/", 1)[1])
            self.reads.append(repo_id)
            name = f"repo{repo_id}"
            return httpx.Response(
                200,
                headers=headers,
                json={
                    "id": repo_id,
                    "name": name,
                    "full_name": f"octo/{name}",
                    "owner": {"login": "octo", "id": 77, "type": "User"},
                    "private": False,
                    "html_url": f"https://github.com/octo/{name}",
                    "description": "From GitHub",
                    "fork": False,
                    "archived": False,
                    "pushed_at": "2026-10-31T09:30:00Z",
                },
            )
        if path.endswith("/languages"):
            return httpx.Response(200, headers=headers, json={"Python": 100})
        if path.endswith("/contributors"):
            return httpx.Response(204, headers=headers)
        raise AssertionError(f"unexpected request {path}")


@pytest.fixture
def repositories(db_engine):
    """Two published projects, one repository with an old job and one with none,
    and a draft's repository with a job left QUEUED while no worker ran."""
    with Session(db_engine) as db:
        owner = _owner(db)
        ids = {}
        for key, github_repo_id in GITHUB_REPO_IDS.items():
            name = f"repo{github_repo_id}"
            repository = GitHubRepository(
                **_repository_fields(github_repo_id=github_repo_id, owner_github_id=77, name=name)
            )
            db.add(repository)
            db.flush()
            published = key != "draft"
            fields = {"title": "T", "summary": "S", "role": "R", "contribution": "C"}
            project = Project(
                owner_id=owner.id,
                status="PUBLISHED" if published else "DRAFT",
                visibility="PUBLIC" if published else "PRIVATE",
                **(fields if published else {}),
            )
            db.add(project)
            db.flush()
            _link(db, project, repository)
            ids[key] = repository.id
        old = T0 - timedelta(days=3)
        for key, status, created_at in (("old", "SYNCED", old), ("draft", "QUEUED", old)):
            db.add(
                GitHubSyncJob(
                    github_repository_id=ids[key],
                    status=status,
                    scheduled_at=created_at,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        owner_id = owner.id
        db.commit()
    yield ids
    with Session(db_engine) as db:
        db.execute(delete(User).where(User.id == owner_id))
        db.execute(delete(GitHubRepository).where(GitHubRepository.id.in_(ids.values())))
        db.commit()


@pytest.fixture
def period_from_the_environment(monkeypatch):
    """The values set in the container: Settings reads them from the environment."""
    monkeypatch.setenv("GITHUB_PERIODIC_SYNC_SECONDS", str(PERIOD))
    monkeypatch.setenv("GITHUB_PERIODIC_SYNC_BATCH", str(BATCH))
    monkeypatch.setattr(worker_module, "settings", Settings(_env_file=None))


def _process(clock: Clock) -> tuple[SyncWorker, FakeGitHub]:
    github = FakeGitHub(clock)
    client = GitHubApiClient(
        httpx.Client(transport=httpx.MockTransport(github)),
        "worker_client_id",
        "worker_client_secret",
        rate_limits=RateLimitState(),
        pause=RateLimitPause(),
        now=clock,
    )
    return SyncWorker(client, make_processor(client, clock), now=clock), github


def _created(repository_id) -> list[tuple[datetime, str]]:
    with SessionLocal() as db:
        rows = db.execute(
            select(GitHubSyncJob.created_at, GitHubSyncJob.status)
            .where(
                GitHubSyncJob.github_repository_id == repository_id,
                GitHubSyncJob.created_at >= T0,
            )
            .order_by(GitHubSyncJob.created_at)
        )
        return [(created_at, status) for created_at, status in rows]


@pytest.mark.usefixtures("period_from_the_environment")
def test_an_idle_loop_keeps_syncing_published_repositories(repositories, caplog, monkeypatch):
    # alembic's fileConfig in the db_engine fixture disables existing loggers.
    monkeypatch.setattr(logging.getLogger(worker_module.__name__), "disabled", False)
    caplog.set_level(logging.INFO, logger=worker_module.__name__)
    clock = Clock()
    worker, github = _process(clock)
    stop = threading.Event()
    idle = timedelta(minutes=33)

    def wait(seconds: float) -> None:
        clock.now += timedelta(seconds=seconds)
        if clock.now - T0 >= idle:
            stop.set()

    worker.run_forever(SessionLocal, stop, wait=wait)

    messages = [record.getMessage() for record in caplog.records]
    started = f"GitHub sync worker: started, periodic sync every {PERIOD} s, batch {BATCH}"
    first_job = next(i for i, message in enumerate(messages) if message.startswith("Sync job"))
    assert started in messages[:first_job]
    assert "periodic syncs queued" in caplog.text
    for key in ("old", "none"):
        jobs = _created(repositories[key])
        # 33 minutes at a 120-second period, with the enqueue at most once a minute.
        assert len(jobs) >= 11, key
        assert {status for _, status in jobs} == {"SYNCED"}, key
        gaps = [later[0] - earlier[0] for earlier, later in zip(jobs, jobs[1:], strict=False)]
        assert all(timedelta(seconds=PERIOD) <= gap <= timedelta(minutes=3) for gap in gaps), key
    assert _created(repositories["draft"]) == []
    assert github.reads.count(GITHUB_REPO_IDS["draft"]) == 1


@pytest.mark.usefixtures("period_from_the_environment")
def test_iterations_after_the_startup_jobs_queue_the_next_round(repositories):
    """run_once by hand: the first round, the empty iterations, the second round."""
    clock = Clock()
    worker, _ = _process(clock)
    worker_module.check_credentials(worker.client)

    def iterate() -> bool:
        with SessionLocal() as db:
            return worker.run_once(db)

    while iterate():
        pass
    assert len(_created(repositories["old"])) == 1
    assert len(_created(repositories["none"])) == 1

    # A look one second early finds nothing, and the next look is a minute later.
    clock.now = T0 + timedelta(seconds=PERIOD - 1)
    assert iterate() is False
    clock.now = T0 + timedelta(seconds=PERIOD + 58)
    assert iterate() is False
    clock.now = T0 + timedelta(seconds=PERIOD + 59)
    assert iterate() is True
    assert iterate() is True
    assert iterate() is False
    assert len(_created(repositories["old"])) == 2
    assert len(_created(repositories["none"])) == 2
