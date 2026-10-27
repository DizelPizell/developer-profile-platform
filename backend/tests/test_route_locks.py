"""Project routes that change featured projects or count projects lock the owner's
profile row first (ADR-015). These tests call the real routes with the app's own
database session (no get_db override) against committed data, while another
connection holds SELECT ... FOR UPDATE on that profile row."""

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, text
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.identity.service import create_session
from app.main import app, frontend_origin
from app.models.identity import Profile, User
from app.models.projects import Project, ProjectShowcase
from app.settings import settings
from tests.conftest import HTTPS_BASE_URL
from tests.test_projects import COMPLETE


@pytest.fixture
def owner(db_engine):
    """A committed user with a session, a private profile and three published public
    projects, the first two featured. Deleted afterwards (cascade)."""
    suffix = uuid.uuid4().hex[:8]
    fields = {k: v for k, v in COMPLETE.items() if k != "technologies"}
    with db_engine.begin() as conn:
        user_id = conn.execute(
            insert(User)
            .values(github_user_id=uuid.uuid4().int % 10**12 + 10**9, github_login=suffix)
            .returning(User.id)
        ).scalar_one()
        profile_id = conn.execute(
            insert(Profile)
            .values(user_id=user_id, slug=f"lock-{suffix}", status="PRIVATE")
            .returning(Profile.id)
        ).scalar_one()
        projects = [
            conn.execute(
                insert(Project)
                .values(owner_id=user_id, status="PUBLISHED", visibility="PUBLIC", **fields)
                .returning(Project.id)
            ).scalar_one()
            for _ in range(3)
        ]
        for position, project_id in enumerate(projects[:2], start=1):
            conn.execute(
                insert(ProjectShowcase).values(
                    project_id=project_id, profile_id=profile_id, position=position
                )
            )
    with Session(db_engine) as db:
        token = create_session(db, user_id)
        db.commit()
    try:
        yield {"profile_id": profile_id, "projects": projects, "token": token}
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def _blocked_statement(db_engine, holder_pid: int) -> str:
    """The statement of the backend that waits on the holder's lock. Each poll ends its
    transaction: pg_stat_activity is a snapshot taken once per transaction."""
    with db_engine.connect() as conn:
        for _ in range(100):
            query = conn.execute(
                text(
                    "SELECT query FROM pg_stat_activity WHERE :holder = ANY(pg_blocking_pids(pid))"
                ),
                {"holder": holder_pid},
            ).scalar()
            conn.rollback()
            if query is not None:
                return query
            time.sleep(0.05)
    pytest.fail("the route never waited on the profile lock")


# (name, method, path, json, expected status); {a}, {b}, {c} are the three projects:
# a and b featured at 1 and 2, c not featured.
_ROUTES = [
    ("feature", "post", "/projects/{c}/showcase", None, 200),
    ("unfeature", "delete", "/projects/{a}/showcase", None, 200),
    ("reorder", "post", "/profile/featured-projects/reorder", {"project_ids": ["{b}", "{a}"]}, 200),
    ("archive", "post", "/projects/{a}/archive", None, 200),
    ("hide", "post", "/projects/{a}/visibility", {"visibility": "PRIVATE"}, 200),
    ("delete", "delete", "/projects/{a}", None, 204),
    ("create", "post", "/projects", {}, 201),
]


@pytest.mark.parametrize(
    ("method", "path", "body", "expected"),
    [route[1:] for route in _ROUTES],
    ids=[route[0] for route in _ROUTES],
)
def test_route_waits_for_the_profile_lock(db_engine, owner, method, path, body, expected):
    assert get_db not in app.dependency_overrides
    a, b, c = (str(project_id) for project_id in owner["projects"])

    def fill(value: str) -> str:
        return value.format(a=a, b=b, c=c)

    url = "/api/v1" + fill(path)
    kwargs = {}
    if body is not None:
        kwargs["json"] = {
            key: [fill(v) for v in value] if isinstance(value, list) else value
            for key, value in body.items()
        }

    client = TestClient(app, base_url=HTTPS_BASE_URL, headers={"Origin": frontend_origin})
    client.cookies.set(settings.session_cookie_name, owner["token"])
    result: dict = {}

    with db_engine.connect() as holder:
        transaction = holder.begin()
        try:
            holder_pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
            holder.execute(
                text("SELECT id FROM profiles WHERE id = :id FOR UPDATE"),
                {"id": owner["profile_id"]},
            )

            def run() -> None:
                try:
                    result["resp"] = getattr(client, method)(url, **kwargs)
                except Exception as exc:  # reported in the main thread
                    result["error"] = exc

            thread = threading.Thread(target=run)
            thread.start()
            statement = _blocked_statement(db_engine, holder_pid)
            # The route waits on its own profile lock, not on something later
            # (a foreign key check on profiles would also wait on FOR UPDATE).
            assert "FROM profiles" in statement
            assert "FOR UPDATE" in statement
            assert thread.is_alive()
        finally:
            transaction.rollback()
        thread.join(timeout=10)

    client.close()
    assert not thread.is_alive()
    assert "error" not in result, result.get("error")
    assert result["resp"].status_code == expected, result["resp"].text
