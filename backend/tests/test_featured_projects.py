"""Featured projects (ADR-015, step 3.2b): feature, unfeature, reorder, ownership,
session, Origin, and races between two real transactions."""

import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.errors import AppError
from app.main import app, frontend_origin
from app.models.identity import Profile, User
from app.models.projects import Project, ProjectShowcase
from app.projects import service
from tests.conftest import login, make_github_transport, wait_until_blocked
from tests.test_projects import (
    COMPLETE,
    FOREIGN,
    PROJECTS,
    _create,
    _error,
    _field_errors,
    _published,
    _url,
)

REORDER = "/api/v1/profile/featured-projects/reorder"


@pytest.fixture
def client(auth_client):
    login(auth_client)
    return auth_client


@pytest.fixture
def other_client(client, make_auth_client):
    """A second user, logged in after the first."""
    other = make_auth_client(make_github_transport(github_user_id=20002, github_login="other"))
    login(other)
    return other


def _feature(client, project: dict):
    return client.post(_url(project, "showcase"))


def _unfeature(client, project: dict):
    return client.delete(_url(project, "showcase"))


def _items(*projects: dict) -> dict:
    return {"items": [{"project_id": p["id"], "position": i} for i, p in enumerate(projects, 1)]}


def _featured_set(client) -> dict[str, int]:
    """{project id: featured_position} as the cabinet list shows it."""
    items = client.get(PROJECTS).json()["items"]
    return {item["id"]: item["featured_position"] for item in items if item["featured_position"]}


@pytest.fixture
def three(client) -> list[dict]:
    """Three published projects featured at positions 1, 2, 3 through the API."""
    projects = [_published(client, title=f"P{i}") for i in (1, 2, 3)]
    for project in projects:
        assert _feature(client, project).status_code == 200
    return projects


# ---------------------------------------------------------------------------
# Feature
# ---------------------------------------------------------------------------


class TestFeature:
    def test_published_public_project_is_featured(self, client):
        project = _published(client)
        resp = _feature(client, project)
        assert resp.status_code == 200
        assert resp.json() == _items(project)
        assert client.get(_url(project)).json()["featured_position"] == 1

    def test_each_new_project_goes_last(self, client, three):
        assert _featured_set(client) == {p["id"]: i for i, p in enumerate(three, start=1)}

    def test_private_profile_can_feature(self, client):
        assert client.get("/api/v1/profile").json()["status"] == "PRIVATE"
        assert _feature(client, _published(client)).status_code == 200

    @pytest.mark.parametrize(
        ("prepare", "status", "visibility"),
        [
            ([], "DRAFT", "PRIVATE"),
            (
                [
                    ("post", "publish", {}),
                    ("post", "visibility", {"json": {"visibility": "PRIVATE"}}),
                ],
                "PUBLISHED",
                "PRIVATE",
            ),
            ([("post", "publish", {}), ("post", "archive", {})], "ARCHIVED", "PRIVATE"),
        ],
        ids=["draft", "published-private", "archived"],
    )
    def test_only_published_public_can_be_featured(self, client, prepare, status, visibility):
        project = _create(client, **COMPLETE)
        for method, action, kwargs in prepare:
            assert getattr(client, method)(_url(project, action), **kwargs).status_code == 200
        error = _error(_feature(client, project), 409, "PROJECT_NOT_FEATURABLE")
        assert error["details"] == {"status": status, "visibility": visibility}
        assert _featured_set(client) == {}

    def test_fourth_project_is_rejected(self, client, three):
        error = _error(
            _feature(client, _published(client, title="P4")), 409, "FEATURED_LIMIT_REACHED"
        )
        assert error["details"] == {"limit": 3}
        assert _featured_set(client) == {p["id"]: i for i, p in enumerate(three, start=1)}

    def test_repeated_feature_is_idempotent(self, client):
        first, second = _published(client, title="A"), _published(client, title="B")
        _feature(client, first)
        _feature(client, second)
        resp = _feature(client, first)
        assert resp.status_code == 200
        assert resp.json() == _items(first, second)

    def test_featured_project_can_be_featured_again_at_the_limit(self, client, three):
        resp = _feature(client, three[2])
        assert resp.status_code == 200
        assert resp.json() == _items(*three)

    def test_database_limit_is_reported_with_the_contract_code(self, client, three, monkeypatch):
        # Without the application check the insert reaches position 4, which the
        # position CHECK rejects; the response is the contract code, not a 500.
        monkeypatch.setattr(service, "FEATURED_PROJECTS_PER_PROFILE", 4)
        _error(_feature(client, _published(client, title="P4")), 409, "FEATURED_LIMIT_REACHED")
        # The savepoint kept the transaction usable.
        assert _featured_set(client) == {p["id"]: i for i, p in enumerate(three, start=1)}


# ---------------------------------------------------------------------------
# Unfeature
# ---------------------------------------------------------------------------


class TestUnfeature:
    @pytest.mark.parametrize("removed", [0, 1, 2])
    def test_removed_and_gap_closed(self, client, three, removed):
        resp = _unfeature(client, three[removed])
        assert resp.status_code == 200
        remaining = [p for i, p in enumerate(three) if i != removed]
        assert resp.json() == _items(*remaining)
        assert client.get(_url(three[removed])).json()["featured_position"] is None

    def test_not_featured_is_idempotent(self, client, three):
        resp = _unfeature(client, _create(client))
        assert resp.status_code == 200
        assert resp.json() == _items(*three)
        assert _unfeature(client, three[0]).json() == _unfeature(client, three[0]).json()

    def test_freed_slot_can_be_used_again(self, client, three):
        _unfeature(client, three[0])
        fourth = _published(client, title="P4")
        assert _feature(client, fourth).json() == _items(three[1], three[2], fourth)


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------


def _reorder(client, *projects: dict):
    return client.post(REORDER, json={"project_ids": [p["id"] for p in projects]})


class TestReorder:
    @pytest.mark.parametrize(
        "order",
        [(1, 0, 2), (0, 2, 1), (2, 0, 1), (1, 2, 0), (2, 1, 0), (0, 1, 2)],
        ids=["swap-1-2", "swap-2-3", "rotate-right", "rotate-left", "reverse", "same"],
    )
    def test_new_order(self, client, three, order):
        projects = [three[i] for i in order]
        resp = _reorder(client, *projects)
        assert resp.status_code == 200
        assert resp.json() == _items(*projects)
        assert _featured_set(client) == {p["id"]: i for i, p in enumerate(projects, start=1)}

    def test_swap_of_two(self, client):
        a, b = _published(client, title="A"), _published(client, title="B")
        _feature(client, a)
        _feature(client, b)
        assert _reorder(client, b, a).json() == _items(b, a)

    def test_empty_set(self, client):
        resp = client.post(REORDER, json={"project_ids": []})
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

    def test_uppercase_ids_are_accepted(self, client, three):
        resp = client.post(
            REORDER, json={"project_ids": [three[1]["id"].upper(), three[0]["id"], three[2]["id"]]}
        )
        assert resp.json() == _items(three[1], three[0], three[2])

    @pytest.mark.parametrize("case", ["missing", "extra", "replaced", "unknown", "empty"])
    def test_list_must_be_the_current_set(self, client, three, case):
        unfeatured = _published(client, title="Not featured")
        a, b, c = three
        ids = {
            "missing": [a["id"], b["id"]],
            "extra": None,  # set below: two featured plus one more
            "replaced": [a["id"], b["id"], unfeatured["id"]],
            "unknown": [a["id"], b["id"], str(uuid.uuid4())],
            "empty": [],
        }[case]
        if case == "extra":
            _unfeature(client, c)
            ids = [a["id"], b["id"], unfeatured["id"]]
        before = _featured_set(client)
        resp = client.post(REORDER, json={"project_ids": ids})
        _error(resp, 409, "FEATURED_ORDER_MISMATCH")
        assert _featured_set(client) == before

    def test_foreign_ids_are_a_mismatch(self, client, other_client):
        theirs = _published(other_client)
        _feature(other_client, theirs)
        _error(_reorder(client, theirs), 409, "FEATURED_ORDER_MISMATCH")
        mine = _published(client)
        _feature(client, mine)
        _error(_reorder(client, mine, theirs), 409, "FEATURED_ORDER_MISMATCH")
        assert _featured_set(other_client) == {theirs["id"]: 1}

    @pytest.mark.parametrize(
        ("body", "loc", "error_type"),
        [
            ({}, ["body", "project_ids"], "missing"),
            ({"project_ids": None}, ["body", "project_ids"], "list_type"),
            ({"project_ids": ["not-a-uuid"]}, ["body", "project_ids", 0], "uuid_parsing"),
            ({"project_ids": [7]}, ["body", "project_ids", 0], "uuid_type"),
            ({"project_ids": [], "extra": 1}, ["body", "extra"], "extra_forbidden"),
        ],
    )
    def test_malformed_body(self, client, body, loc, error_type):
        assert _error(client.post(REORDER, json=body), 422, "VALIDATION_ERROR")["details"] == {
            "fields": [{"loc": loc, "type": error_type}]
        }

    @pytest.mark.parametrize(
        "form",
        [
            lambda s: s.replace("-", ""),
            lambda s: "{" + s + "}",
            lambda s: "urn:uuid:" + s,
            lambda s: s[:8] + s[9:13] + "-" + s[13:],
        ],
        ids=["no-hyphens", "braces", "urn", "moved-hyphen"],
    )
    def test_non_canonical_ids_rejected(self, client, three, form):
        ids = [form(three[0]["id"]), three[1]["id"], three[2]["id"]]
        fields = _field_errors(client.post(REORDER, json={"project_ids": ids}))
        assert fields == [{"loc": ["body", "project_ids", 0], "type": "uuid_parsing"}]

    @pytest.mark.parametrize("upper", [False, True], ids=["same-case", "other-case"])
    def test_duplicates_rejected(self, client, three, upper):
        a, b, _ = three
        ids = [a["id"], a["id"].upper() if upper else a["id"], b["id"]]
        fields = _field_errors(client.post(REORDER, json={"project_ids": ids}))
        assert fields == [{"loc": ["body", "project_ids"], "type": "duplicate_project"}]
        assert _featured_set(client) == {p["id"]: i for i, p in enumerate(three, start=1)}

    def test_more_than_three_rejected(self, client, three):
        ids = [p["id"] for p in three] + [str(uuid.uuid4())]
        fields = _field_errors(client.post(REORDER, json={"project_ids": ids}))
        assert fields == [{"loc": ["body", "project_ids"], "type": "too_long"}]


# ---------------------------------------------------------------------------
# Ownership, session, Origin
# ---------------------------------------------------------------------------


class TestOwnershipAndAccess:
    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_foreign_project_is_404(self, client, other_client, method):
        theirs = _published(other_client)
        _feature(other_client, theirs)
        _error(getattr(client, method)(_url(theirs, "showcase")), 404, "NOT_FOUND")
        assert _featured_set(other_client) == {theirs["id"]: 1}
        assert _featured_set(client) == {}

    @pytest.mark.parametrize("method", ["post", "delete"])
    @pytest.mark.parametrize("project_id", [None, "not-a-uuid"], ids=["missing", "malformed"])
    def test_missing_or_malformed_id_is_404(self, client, method, project_id):
        path = f"{PROJECTS}/{project_id or uuid.uuid4()}/showcase"
        _error(getattr(client, method)(path), 404, "NOT_FOUND")

    @pytest.mark.parametrize(
        ("method", "path", "kwargs"),
        [
            ("post", f"{PROJECTS}/{uuid.uuid4()}/showcase", {}),
            ("delete", f"{PROJECTS}/{uuid.uuid4()}/showcase", {}),
            ("post", REORDER, {"json": {"project_ids": []}}),
        ],
    )
    def test_requires_session(self, auth_client, method, path, kwargs):
        _error(getattr(auth_client, method)(path, **kwargs), 401, "UNAUTHORIZED")

    @pytest.mark.parametrize("operation", ["feature", "unfeature", "reorder"])
    @pytest.mark.parametrize("headers", [{}, {"Origin": FOREIGN}], ids=["no-origin", "foreign"])
    def test_origin_required_and_nothing_changes(self, make_auth_client, operation, headers):
        client = make_auth_client()
        login(client)
        a, b = _published(client, title="A"), _published(client, title="B")
        _feature(client, a)
        _feature(client, b)
        bare = make_auth_client(send_origin=False)
        bare.cookies = client.cookies

        resp = {
            "feature": lambda: bare.post(_url(_published(client), "showcase"), headers=headers),
            "unfeature": lambda: bare.delete(_url(a, "showcase"), headers=headers),
            "reorder": lambda: bare.post(
                REORDER, json={"project_ids": [b["id"], a["id"]]}, headers=headers
            ),
        }[operation]()
        _error(resp, 403, "CSRF_ORIGIN_INVALID")
        assert _featured_set(client) == {a["id"]: 1, b["id"]: 2}

    def test_unfeature_preflight_allowed_from_frontend(self):
        resp = TestClient(app).options(
            f"{PROJECTS}/{uuid.uuid4()}/showcase",
            headers={"Origin": frontend_origin, "Access-Control-Request-Method": "DELETE"},
        )
        assert resp.status_code == 200
        assert "DELETE" in resp.headers["access-control-allow-methods"]


# ---------------------------------------------------------------------------
# Races (two real transactions)
# ---------------------------------------------------------------------------


class TestFeaturedRace:
    """Two transactions change the same profile's featured projects. The second
    waits on the first's profile lock, then works on what the first left. These
    tests commit to the test database and delete their user afterwards (cascade)."""

    def _seed(self, db_engine, projects: int, featured: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
        """A user with a private profile, published public projects and the first
        `featured` of them featured; committed."""
        suffix = uuid.uuid4().hex[:8]
        with db_engine.begin() as conn:
            user_id = conn.execute(
                insert(User)
                .values(github_user_id=uuid.uuid4().int % 10**12 + 10**9, github_login=suffix)
                .returning(User.id)
            ).scalar_one()
            profile_id = conn.execute(
                insert(Profile)
                .values(user_id=user_id, slug=f"race-{suffix}", status="PRIVATE")
                .returning(Profile.id)
            ).scalar_one()
            project_fields = {k: v for k, v in COMPLETE.items() if k != "technologies"}
            ids = [
                conn.execute(
                    insert(Project)
                    .values(
                        owner_id=user_id,
                        status="PUBLISHED",
                        visibility="PUBLIC",
                        **{**project_fields, "title": f"Race {i}"},
                    )
                    .returning(Project.id)
                ).scalar_one()
                for i in range(projects)
            ]
            for position, project_id in enumerate(ids[:featured], start=1):
                conn.execute(
                    insert(ProjectShowcase).values(
                        project_id=project_id, profile_id=profile_id, position=position
                    )
                )
        return user_id, ids

    def _cleanup(self, db_engine, user_id: uuid.UUID) -> None:
        with db_engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})

    def _positions(self, db_engine, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
        with db_engine.connect() as conn:
            rows = conn.execute(
                select(ProjectShowcase.project_id, ProjectShowcase.position)
                .join(Profile, Profile.id == ProjectShowcase.profile_id)
                .where(Profile.user_id == user_id)
            )
            return {project_id: position for project_id, position in rows}

    # The same steps and lock order as the routes.
    def _feature(self, db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        user = db.get(User, user_id)
        profile = service.lock_owner_profile(db, user)
        project = service.get_own_project(db, user, str(project_id), for_update=True)
        service.feature(db, profile, project)

    def _unfeature(self, db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> None:
        user = db.get(User, user_id)
        service.lock_owner_profile(db, user)
        service.unfeature(db, service.get_own_project(db, user, str(project_id), for_update=True))

    def _reorder(self, db: Session, user_id: uuid.UUID, project_ids: list[uuid.UUID]) -> None:
        user = db.get(User, user_id)
        service.reorder_featured(db, service.lock_owner_profile(db, user), project_ids)

    def _race(self, db_engine, first_step, second_step, first_outcome: str = "commit") -> dict:
        """Runs first_step, then second_step in a thread that must block on a lock,
        then ends the first transaction. Returns {"ok": True} or {"error": exc}."""
        result: dict = {}
        with Session(db_engine) as first, Session(db_engine) as second:
            first_step(first)
            pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

            def run() -> None:
                try:
                    second_step(second)
                    second.commit()
                    result["ok"] = True
                except Exception as exc:  # reported in the main thread
                    second.rollback()
                    result["error"] = exc

            thread = threading.Thread(target=run)
            thread.start()
            wait_until_blocked(db_engine, pid)
            getattr(first, first_outcome)()
            thread.join(timeout=10)
            assert not thread.is_alive()
        return result

    def _assert_no_gaps(self, positions: dict[uuid.UUID, int]) -> None:
        assert sorted(positions.values()) == list(range(1, len(positions) + 1))

    @pytest.mark.parametrize("first_outcome", ["commit", "rollback"])
    def test_two_features_for_the_last_slot(self, db_engine, first_outcome):
        user_id, ids = self._seed(db_engine, projects=4, featured=2)
        try:
            result = self._race(
                db_engine,
                lambda db: self._feature(db, user_id, ids[2]),
                lambda db: self._feature(db, user_id, ids[3]),
                first_outcome,
            )
            positions = self._positions(db_engine, user_id)
            if first_outcome == "commit":
                assert isinstance(result.get("error"), AppError), result
                assert result["error"].code == "FEATURED_LIMIT_REACHED"
                assert positions == {ids[0]: 1, ids[1]: 2, ids[2]: 3}
            else:
                assert result == {"ok": True}
                assert positions == {ids[0]: 1, ids[1]: 2, ids[3]: 3}
        finally:
            self._cleanup(db_engine, user_id)

    def test_two_reorders(self, db_engine):
        user_id, (a, b, c) = self._seed(db_engine, projects=3, featured=3)
        try:
            result = self._race(
                db_engine,
                lambda db: self._reorder(db, user_id, [c, a, b]),
                lambda db: self._reorder(db, user_id, [b, c, a]),
            )
            assert result == {"ok": True}
            positions = self._positions(db_engine, user_id)
            self._assert_no_gaps(positions)
            assert positions == {b: 1, c: 2, a: 3}
        finally:
            self._cleanup(db_engine, user_id)

    def test_reorder_after_concurrent_unfeature_is_a_mismatch(self, db_engine):
        user_id, (a, b, c) = self._seed(db_engine, projects=3, featured=3)
        try:
            result = self._race(
                db_engine,
                lambda db: self._unfeature(db, user_id, b),
                lambda db: self._reorder(db, user_id, [b, c, a]),
            )
            assert isinstance(result.get("error"), AppError), result
            assert result["error"].code == "FEATURED_ORDER_MISMATCH"
            positions = self._positions(db_engine, user_id)
            self._assert_no_gaps(positions)
            assert positions == {a: 1, c: 2}
        finally:
            self._cleanup(db_engine, user_id)
