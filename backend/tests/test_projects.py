"""Project cabinet endpoints (ADR-015, step 3.2a): CRUD, technologies, transitions,
ownership, limits, featured side effects, session, Origin and CORS."""

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.main import app, frontend_origin
from app.models.identity import Profile, User
from app.models.projects import PROJECT_TEXT_LIMITS, Project, ProjectShowcase, Technology
from app.projects import service
from tests.conftest import login, make_github_transport

PROJECTS = "/api/v1/projects"
FOREIGN = "https://evil.example"

PROJECT_KEYS = {
    "id",
    "status",
    "visibility",
    "title",
    "summary",
    "description",
    "problem",
    "results",
    "role",
    "contribution",
    "technologies",
    "featured_position",
}
SUMMARY_KEYS = {
    "id",
    "status",
    "visibility",
    "title",
    "summary",
    "technologies",
    "featured_position",
}
SINGLE_LINE = ("title", "summary", "role")
MULTI_LINE = ("description", "problem", "results", "contribution")
COMPLETE = {
    "title": "Payments API",
    "summary": "Card payments for a marketplace",
    "role": "Backend developer",
    "contribution": "Designed and built the API",
    "technologies": ["Python", "PostgreSQL"],
}


def _error(resp, status: int, code: str) -> dict:
    assert resp.status_code == status, resp.text
    error = resp.json()["error"]
    assert error["code"] == code
    assert error["request_id"] == resp.headers["x-request-id"]
    return error


def _field_errors(resp) -> list[dict]:
    return _error(resp, 422, "VALIDATION_ERROR")["details"]["fields"]


def _create(client, **body) -> dict:
    resp = client.post(PROJECTS, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _published(client, **overrides) -> dict:
    project = _create(client, **{**COMPLETE, **overrides})
    resp = client.post(f"{PROJECTS}/{project['id']}/publish")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _url(project: dict, action: str = "") -> str:
    return f"{PROJECTS}/{project['id']}{'/' + action if action else ''}"


def _user_row(db_session, github_user_id: int = 10001) -> User:
    return db_session.execute(
        select(User).where(User.github_user_id == github_user_id)
    ).scalar_one()


def _profile_row(db_session, github_user_id: int = 10001) -> Profile:
    return db_session.execute(
        select(Profile).join(User).where(User.github_user_id == github_user_id)
    ).scalar_one()


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


# ---------------------------------------------------------------------------
# Create and list
# ---------------------------------------------------------------------------


class TestCreate:
    def test_new_project_is_empty_draft(self, client):
        body = _create(client)
        assert set(body) == PROJECT_KEYS
        assert body["status"] == "DRAFT"
        assert body["visibility"] == "PRIVATE"
        assert body["technologies"] == []
        assert body["featured_position"] is None
        assert all(body[field] is None for field in PROJECT_TEXT_LIMITS)

    def test_create_with_all_fields(self, client):
        body = _create(
            client, **COMPLETE, description="Long", problem="Slow checkout", results="2x faster"
        )
        assert body["title"] == "Payments API"
        assert body["technologies"] == ["Python", "PostgreSQL"]
        assert body["results"] == "2x faster"
        assert body["status"] == "DRAFT"

    def test_body_is_required(self, client):
        errors = _field_errors(client.post(PROJECTS))
        assert errors == [{"loc": ["body"], "type": "missing"}]

    @pytest.mark.parametrize(
        "payload",
        [{"status": "PUBLISHED"}, {"visibility": "PUBLIC"}, {"id": str(uuid.uuid4())}, {"x": 1}],
    )
    def test_unknown_fields_rejected(self, client, payload):
        errors = _field_errors(client.post(PROJECTS, json=payload))
        assert errors[0]["type"] == "extra_forbidden"

    def test_project_limit(self, client, db_session):
        owner = _user_row(db_session)
        db_session.add_all([Project(owner_id=owner.id) for _ in range(49)])
        db_session.flush()

        _create(client)  # the 50th
        error = _error(client.post(PROJECTS, json={}), 409, "PROJECT_LIMIT_REACHED")
        assert error["details"] == {"limit": 50}
        count = db_session.execute(
            select(func.count()).select_from(Project).where(Project.owner_id == owner.id)
        ).scalar_one()
        assert count == 50

    def test_limit_counts_only_own_projects(self, client, other_client, db_session):
        other = _user_row(db_session, 20002)
        db_session.add_all([Project(owner_id=other.id) for _ in range(50)])
        db_session.flush()

        _create(client)
        _error(other_client.post(PROJECTS, json={}), 409, "PROJECT_LIMIT_REACHED")


class TestList:
    def test_only_own_projects_newest_first(self, client, other_client):
        first = _create(client, title="First")
        second = _create(client, title="Second", technologies=["Go"])
        _create(other_client, title="Not mine")

        items = client.get(PROJECTS).json()["items"]
        assert [item["id"] for item in items] == [second["id"], first["id"]]
        assert set(items[0]) == SUMMARY_KEYS
        assert items[0]["technologies"] == ["Go"]
        assert items[0]["featured_position"] is None

    def test_empty_list(self, client):
        assert client.get(PROJECTS).json() == {"items": []}


# ---------------------------------------------------------------------------
# Read, ownership and 404
# ---------------------------------------------------------------------------


class TestReadAndOwnership:
    def test_get_own_project(self, client):
        created = _create(client, **COMPLETE)
        assert client.get(_url(created)).json() == created

    def test_foreign_missing_and_malformed_ids_are_identical_404(self, client, other_client):
        foreign = _create(other_client, title="Other's")
        responses = [
            client.get(_url(foreign)),
            client.get(f"{PROJECTS}/{uuid.uuid4()}"),
            client.get(f"{PROJECTS}/not-a-uuid"),
            client.get("/api/v1/no-such-route"),
        ]
        bodies = []
        for resp in responses:
            _error(resp, 404, "NOT_FOUND")
            error = resp.json()["error"]
            bodies.append({k: v for k, v in error.items() if k != "request_id"})
        assert all(body == bodies[-1] for body in bodies)

    @pytest.mark.parametrize(
        ("method", "action", "kwargs"),
        [
            ("patch", "", {"json": {"title": "Hijack"}}),
            ("delete", "", {}),
            ("post", "publish", {}),
            ("post", "archive", {}),
            ("post", "visibility", {"json": {"visibility": "PRIVATE"}}),
        ],
    )
    def test_foreign_project_cannot_be_changed(self, client, other_client, method, action, kwargs):
        foreign = _published(other_client)
        _error(getattr(client, method)(_url(foreign, action), **kwargs), 404, "NOT_FOUND")
        assert other_client.get(_url(foreign)).json() == foreign


# ---------------------------------------------------------------------------
# PATCH and normalization
# ---------------------------------------------------------------------------


class TestUpdate:
    def test_partial_update_keeps_other_fields(self, client):
        project = _create(client, title="T", role="R", technologies=["Go"])
        body = client.patch(_url(project), json={"summary": "S"}).json()
        assert (body["title"], body["role"], body["summary"]) == ("T", "R", "S")
        assert body["technologies"] == ["Go"]

    def test_null_clears_field(self, client):
        project = _create(client, title="T", role="R")
        body = client.patch(_url(project), json={"role": None}).json()
        assert body["role"] is None
        assert body["title"] == "T"

    def test_empty_body_changes_nothing(self, client):
        project = _create(client, **COMPLETE)
        assert client.patch(_url(project), json={}).json() == project

    @pytest.mark.parametrize("field", SINGLE_LINE + MULTI_LINE)
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("  Text  ", "Text"),
            ("\tText\n", "Text"),
            ("\r\n Text \r\n", "Text"),
            ("", None),
            ("   ", None),
            ("\n", None),
            ("\n\t \r\n", None),
        ],
    )
    def test_edges_trimmed_and_blank_becomes_null(self, client, field, value, expected):
        project = _create(client, **{field: "before"})
        assert client.patch(_url(project), json={field: value}).json()[field] == expected

    @pytest.mark.parametrize("field", SINGLE_LINE)
    @pytest.mark.parametrize("value", ["Line\nbreak", "Line\r\nbreak", "Tab\there"])
    def test_single_line_fields_reject_inner_breaks(self, client, field, value):
        project = _create(client)
        errors = _field_errors(client.patch(_url(project), json={field: value}))
        assert errors == [{"loc": ["body", field], "type": "control_characters"}]

    @pytest.mark.parametrize("field", MULTI_LINE)
    def test_multi_line_fields_keep_inner_newlines(self, client, field):
        project = _create(client)
        body = client.patch(_url(project), json={field: "One\r\nTwo\n\nThree"}).json()
        assert body[field] == "One\nTwo\n\nThree"

    @pytest.mark.parametrize("field", MULTI_LINE)
    @pytest.mark.parametrize("bad", ["Tab\there", "Null\x00", "Bell\x07"])
    def test_multi_line_fields_reject_other_controls(self, client, field, bad):
        project = _create(client)
        errors = _field_errors(client.patch(_url(project), json={field: bad}))
        assert errors == [{"loc": ["body", field], "type": "control_characters"}]

    @pytest.mark.parametrize(("field", "limit"), PROJECT_TEXT_LIMITS.items())
    def test_length_limits_at_boundary(self, client, field, limit):
        project = _create(client)
        ok = client.patch(_url(project), json={field: "я" * limit})
        assert ok.status_code == 200
        assert ok.json()[field] == "я" * limit
        # Trimmed before counting.
        assert client.patch(_url(project), json={field: f"  {'x' * limit}  "}).status_code == 200

        errors = _field_errors(client.patch(_url(project), json={field: "x" * (limit + 1)}))
        assert errors == [{"loc": ["body", field], "type": "string_too_long"}]

    def test_non_string_value_rejected(self, client):
        project = _create(client)
        errors = _field_errors(client.patch(_url(project), json={"title": 5}))
        assert errors == [{"loc": ["body", "title"], "type": "string_type"}]

    def test_updated_at_changes_only_on_real_change(self, client, db_session):
        project = _create(client, title="T", technologies=["Go"])

        def updated_at():
            row = db_session.get(Project, uuid.UUID(project["id"]))
            db_session.refresh(row)
            return row.updated_at

        first = updated_at()
        client.patch(_url(project), json={"title": "T", "technologies": ["go"]})
        assert updated_at() == first
        client.patch(_url(project), json={"technologies": ["Go", "Rust"]})
        second = updated_at()
        assert second > first
        client.patch(_url(project), json={"title": "New"})
        assert updated_at() > second

    @pytest.mark.parametrize("field", ["title", "summary", "role", "contribution"])
    def test_published_project_cannot_lose_required_field(self, client, field):
        project = _published(client)
        error = _error(client.patch(_url(project), json={field: "   "}), 422, "PROJECT_INCOMPLETE")
        assert error["details"] == {"missing_fields": [field]}
        assert client.get(_url(project)).json() == project

    def test_published_project_cannot_lose_all_technologies(self, client):
        project = _published(client)
        error = _error(
            client.patch(_url(project), json={"technologies": []}), 422, "PROJECT_INCOMPLETE"
        )
        assert error["details"] == {"missing_fields": ["technologies"]}

    def test_published_project_can_edit_other_fields(self, client):
        project = _published(client)
        body = client.patch(_url(project), json={"description": "More", "title": "Renamed"}).json()
        assert (body["description"], body["title"], body["status"]) == (
            "More",
            "Renamed",
            "PUBLISHED",
        )

    @pytest.mark.parametrize("status_action", ["draft", "archived"])
    def test_unpublished_project_can_be_emptied(self, client, status_action):
        project = _published(client) if status_action == "archived" else _create(client, **COMPLETE)
        if status_action == "archived":
            client.post(_url(project, "archive"))
        body = client.patch(
            _url(project), json={"title": None, "summary": None, "technologies": []}
        ).json()
        assert body["title"] is None and body["technologies"] == []


# ---------------------------------------------------------------------------
# Technologies
# ---------------------------------------------------------------------------


class TestTechnologies:
    def test_order_is_kept(self, client):
        names = ["TypeScript", "C#", "ASP.NET Core", "Node.js", "Вёрстка"]
        assert _create(client, technologies=names)["technologies"] == names

    def test_whitespace_is_trimmed_and_collapsed(self, client):
        body = _create(client, technologies=["  Node   js ", "Vue\t3", "Spring\nBoot"])
        assert body["technologies"] == ["Node js", "Vue 3", "Spring Boot"]

    def test_existing_spelling_is_reused(self, client, other_client, db_session):
        _create(other_client, technologies=["PostgreSQL"])
        body = _create(client, technologies=[" postgresql "])
        assert body["technologies"] == ["PostgreSQL"]
        count = db_session.execute(
            select(func.count())
            .select_from(Technology)
            .where(func.lower(Technology.name) == "postgresql")
        ).scalar_one()
        assert count == 1

    @pytest.mark.parametrize(
        "names",
        [["Go", "go"], ["Node js", "node   JS"], ["Python", "Go", "PYTHON"]],
    )
    def test_duplicates_ignoring_case_rejected(self, client, names):
        errors = _field_errors(client.post(PROJECTS, json={"technologies": names}))
        assert errors == [{"loc": ["body", "technologies"], "type": "duplicate_technology"}]

    def test_twenty_accepted_twenty_one_rejected(self, client):
        names = [f"Tech {i}" for i in range(21)]
        assert len(_create(client, technologies=names[:20])["technologies"]) == 20
        errors = _field_errors(client.post(PROJECTS, json={"technologies": names}))
        assert errors == [{"loc": ["body", "technologies"], "type": "too_long"}]

    def test_name_length(self, client):
        assert _create(client, technologies=["x" * 50])["technologies"] == ["x" * 50]
        assert _create(client, technologies=[f"  {'y' * 50}  "])["technologies"] == ["y" * 50]
        errors = _field_errors(client.post(PROJECTS, json={"technologies": ["x" * 51]}))
        assert errors == [{"loc": ["body", "technologies", 0], "type": "string_too_long"}]

    @pytest.mark.parametrize(
        ("name", "error_type"),
        [("", "string_too_short"), ("   ", "string_too_short"), ("Bell\x07", "control_characters")],
    )
    def test_bad_names_rejected(self, client, name, error_type):
        errors = _field_errors(client.post(PROJECTS, json={"technologies": ["Go", name]}))
        assert errors == [{"loc": ["body", "technologies", 1], "type": error_type}]

    def test_null_list_rejected(self, client):
        project = _create(client, technologies=["Go"])
        errors = _field_errors(client.patch(_url(project), json={"technologies": None}))
        assert errors == [{"loc": ["body", "technologies"], "type": "list_type"}]

    def test_list_is_replaced_or_kept(self, client):
        project = _create(client, technologies=["Go", "Rust"])
        assert client.patch(_url(project), json={"title": "T"}).json()["technologies"] == [
            "Go",
            "Rust",
        ]
        replaced = client.patch(_url(project), json={"technologies": ["Rust", "Zig"]}).json()
        assert replaced["technologies"] == ["Rust", "Zig"]
        assert client.patch(_url(project), json={"technologies": []}).json()["technologies"] == []


# ---------------------------------------------------------------------------
# Publish, archive, visibility
# ---------------------------------------------------------------------------


class TestPublish:
    def test_empty_project_lists_every_missing_field(self, client):
        project = _create(client)
        error = _error(client.post(_url(project, "publish")), 422, "PROJECT_INCOMPLETE")
        assert error["details"] == {
            "missing_fields": ["title", "summary", "role", "contribution", "technologies"]
        }
        assert client.get(_url(project)).json()["status"] == "DRAFT"

    @pytest.mark.parametrize(
        "missing", ["title", "summary", "role", "contribution", "technologies"]
    )
    def test_each_required_field(self, client, missing):
        body = {key: value for key, value in COMPLETE.items() if key != missing}
        project = _create(client, **body)
        error = _error(client.post(_url(project, "publish")), 422, "PROJECT_INCOMPLETE")
        assert error["details"] == {"missing_fields": [missing]}

    def test_description_problem_results_optional(self, client):
        project = _published(client)
        assert (project["status"], project["visibility"]) == ("PUBLISHED", "PUBLIC")
        assert project["description"] is None

    def test_publish_is_idempotent(self, client):
        project = _published(client)
        again = client.post(_url(project, "publish"))
        assert again.status_code == 200
        assert again.json() == project

    def test_publish_keeps_hidden_project_hidden(self, client):
        project = _published(client)
        client.post(_url(project, "visibility"), json={"visibility": "PRIVATE"})
        body = client.post(_url(project, "publish")).json()
        assert (body["status"], body["visibility"]) == ("PUBLISHED", "PRIVATE")

    def test_archived_project_can_be_published_again(self, client):
        project = _published(client)
        client.post(_url(project, "archive"))
        body = client.post(_url(project, "publish")).json()
        assert (body["status"], body["visibility"]) == ("PUBLISHED", "PUBLIC")

    def test_archived_incomplete_project_cannot_be_published(self, client):
        project = _published(client)
        client.post(_url(project, "archive"))
        client.patch(_url(project), json={"role": None})
        error = _error(client.post(_url(project, "publish")), 422, "PROJECT_INCOMPLETE")
        assert error["details"] == {"missing_fields": ["role"]}


class TestArchiveAndVisibility:
    def test_archive_published(self, client):
        project = _published(client)
        body = client.post(_url(project, "archive")).json()
        assert (body["status"], body["visibility"]) == ("ARCHIVED", "PRIVATE")

    def test_archive_hidden_published(self, client):
        project = _published(client)
        client.post(_url(project, "visibility"), json={"visibility": "PRIVATE"})
        body = client.post(_url(project, "archive")).json()
        assert (body["status"], body["visibility"]) == ("ARCHIVED", "PRIVATE")

    def test_archive_is_idempotent(self, client):
        project = _published(client)
        first = client.post(_url(project, "archive")).json()
        again = client.post(_url(project, "archive"))
        assert again.status_code == 200
        assert again.json() == first

    def test_draft_cannot_be_archived(self, client):
        project = _create(client, **COMPLETE)
        error = _error(client.post(_url(project, "archive")), 409, "PROJECT_TRANSITION_INVALID")
        assert error["details"] == {"status": "DRAFT"}
        assert client.get(_url(project)).json()["status"] == "DRAFT"

    def test_hide_and_show(self, client):
        project = _published(client)
        hidden = client.post(_url(project, "visibility"), json={"visibility": "PRIVATE"}).json()
        assert (hidden["status"], hidden["visibility"]) == ("PUBLISHED", "PRIVATE")
        shown = client.post(_url(project, "visibility"), json={"visibility": "PUBLIC"}).json()
        assert shown["visibility"] == "PUBLIC"

    def test_same_visibility_is_noop(self, client):
        project = _published(client)
        again = client.post(_url(project, "visibility"), json={"visibility": "PUBLIC"})
        assert again.status_code == 200
        assert again.json() == project

    @pytest.mark.parametrize("state", ["DRAFT", "ARCHIVED"])
    @pytest.mark.parametrize("visibility", ["PUBLIC", "PRIVATE"])
    def test_visibility_outside_published_rejected(self, client, state, visibility):
        project = _create(client, **COMPLETE) if state == "DRAFT" else _published(client)
        if state == "ARCHIVED":
            client.post(_url(project, "archive"))
        resp = client.post(_url(project, "visibility"), json={"visibility": visibility})
        error = _error(resp, 409, "PROJECT_TRANSITION_INVALID")
        assert error["details"] == {"status": state}
        body = client.get(_url(project)).json()
        assert (body["status"], body["visibility"]) == (state, "PRIVATE")

    @pytest.mark.parametrize(
        "payload",
        [{}, {"visibility": "HIDDEN"}, {"visibility": None}, {"visibility": "PUBLIC", "x": 1}],
    )
    def test_visibility_body_validated(self, client, payload):
        project = _published(client)
        _field_errors(client.post(_url(project, "visibility"), json=payload))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


class TestDelete:
    def test_delete_removes_project_but_not_technologies(self, client, db_session):
        project = _published(client)
        resp = client.delete(_url(project))
        assert resp.status_code == 204
        assert resp.content == b""
        _error(client.get(_url(project)), 404, "NOT_FOUND")
        _error(client.delete(_url(project)), 404, "NOT_FOUND")
        assert db_session.execute(
            select(func.count()).select_from(Technology).where(Technology.name == "Python")
        ).scalar_one()

    @pytest.mark.parametrize("prepare", ["draft", "published", "archived"])
    def test_any_state_can_be_deleted(self, client, prepare):
        project = _create(client) if prepare == "draft" else _published(client)
        if prepare == "archived":
            client.post(_url(project, "archive"))
        assert client.delete(_url(project)).status_code == 204


# ---------------------------------------------------------------------------
# Featured projects: side effects of archive, hide and delete
# ---------------------------------------------------------------------------


class TestFeaturedSideEffects:
    @pytest.fixture
    def featured(self, client, db_session) -> list[dict]:
        """Three published projects featured at positions 1, 2, 3 (rows written directly)."""
        profile = _profile_row(db_session)
        projects = [_published(client, title=f"P{i}") for i in (1, 2, 3)]
        db_session.add_all(
            ProjectShowcase(project_id=uuid.UUID(p["id"]), profile_id=profile.id, position=i)
            for i, p in enumerate(projects, start=1)
        )
        db_session.flush()
        return projects

    def _positions(self, db_session) -> dict[str, int]:
        profile = _profile_row(db_session)
        rows = db_session.execute(
            select(ProjectShowcase.project_id, ProjectShowcase.position).where(
                ProjectShowcase.profile_id == profile.id
            )
        )
        return {str(project_id): position for project_id, position in rows}

    def test_positions_are_returned(self, client, featured):
        assert client.get(_url(featured[1])).json()["featured_position"] == 2
        items = client.get(PROJECTS).json()["items"]
        assert {item["id"]: item["featured_position"] for item in items} == {
            p["id"]: i for i, p in enumerate(featured, start=1)
        }

    @pytest.mark.parametrize("removed", [0, 1, 2])
    def test_archive_removes_and_closes_gap(self, client, db_session, featured, removed):
        body = client.post(_url(featured[removed], "archive")).json()
        assert body["featured_position"] is None
        remaining = [p["id"] for i, p in enumerate(featured) if i != removed]
        assert self._positions(db_session) == {remaining[0]: 1, remaining[1]: 2}

    def test_hide_removes_and_closes_gap(self, client, db_session, featured):
        resp = client.post(_url(featured[0], "visibility"), json={"visibility": "PRIVATE"})
        assert resp.json()["featured_position"] is None
        assert self._positions(db_session) == {featured[1]["id"]: 1, featured[2]["id"]: 2}

    def test_delete_removes_and_closes_gap(self, client, db_session, featured):
        assert client.delete(_url(featured[1])).status_code == 204
        assert self._positions(db_session) == {featured[0]["id"]: 1, featured[2]["id"]: 2}

    def test_showing_or_republishing_does_not_restore(self, client, db_session, featured):
        client.post(_url(featured[0], "visibility"), json={"visibility": "PRIVATE"})
        client.post(_url(featured[0], "visibility"), json={"visibility": "PUBLIC"})
        client.post(_url(featured[1], "archive"))
        client.post(_url(featured[1], "publish"))
        assert self._positions(db_session) == {featured[2]["id"]: 1}

    def test_noops_and_errors_keep_featured(self, client, db_session, featured):
        before = self._positions(db_session)
        client.post(_url(featured[0], "visibility"), json={"visibility": "PUBLIC"})
        client.post(_url(featured[0], "publish"))
        client.patch(_url(featured[0]), json={"title": None})  # 422, published
        assert self._positions(db_session) == before

    def test_removing_unfeatured_project_keeps_others(self, client, db_session, featured):
        extra = _published(client, title="Extra")
        client.post(_url(extra, "archive"))
        client.delete(_url(extra))
        assert self._positions(db_session) == {p["id"]: i for i, p in enumerate(featured, start=1)}


# ---------------------------------------------------------------------------
# Session, Origin and CORS
# ---------------------------------------------------------------------------

_ENDPOINTS = [
    ("get", PROJECTS, {}),
    ("post", PROJECTS, {"json": {}}),
    ("get", f"{PROJECTS}/{uuid.uuid4()}", {}),
    ("patch", f"{PROJECTS}/{uuid.uuid4()}", {"json": {}}),
    ("delete", f"{PROJECTS}/{uuid.uuid4()}", {}),
    ("post", f"{PROJECTS}/{uuid.uuid4()}/publish", {}),
    ("post", f"{PROJECTS}/{uuid.uuid4()}/archive", {}),
    ("post", f"{PROJECTS}/{uuid.uuid4()}/visibility", {"json": {"visibility": "PUBLIC"}}),
]


class TestSessionOriginCors:
    @pytest.mark.parametrize(("method", "path", "kwargs"), _ENDPOINTS)
    def test_requires_session(self, auth_client, method, path, kwargs):
        _error(getattr(auth_client, method)(path, **kwargs), 401, "UNAUTHORIZED")

    @pytest.mark.parametrize(
        ("method", "action", "kwargs"),
        [
            ("patch", "", {"json": {"title": "Changed"}}),
            ("delete", "", {}),
            ("post", "publish", {}),
            ("post", "archive", {}),
            ("post", "visibility", {"json": {"visibility": "PRIVATE"}}),
        ],
    )
    @pytest.mark.parametrize("headers", [{}, {"Origin": FOREIGN}], ids=["no-origin", "foreign"])
    def test_origin_required_and_nothing_changes(
        self, make_auth_client, method, action, kwargs, headers
    ):
        client = make_auth_client()
        login(client)
        project = _published(client)
        bare = make_auth_client(send_origin=False)
        bare.cookies = client.cookies

        resp = getattr(bare, method)(_url(project, action), headers=headers, **kwargs)
        _error(resp, 403, "CSRF_ORIGIN_INVALID")
        assert client.get(_url(project)).json() == project

    def test_create_requires_origin(self, make_auth_client):
        client = make_auth_client(send_origin=False)
        login(client)
        _error(client.post(PROJECTS, json={}), 403, "CSRF_ORIGIN_INVALID")
        assert client.get(PROJECTS).json() == {"items": []}

    def test_delete_preflight_allowed_from_frontend(self):
        resp = TestClient(app).options(
            f"{PROJECTS}/{uuid.uuid4()}",
            headers={"Origin": frontend_origin, "Access-Control-Request-Method": "DELETE"},
        )
        assert resp.status_code == 200
        assert resp.headers["access-control-allow-origin"] == frontend_origin
        assert "DELETE" in resp.headers["access-control-allow-methods"]

    def test_delete_preflight_refused_from_foreign_origin(self):
        resp = TestClient(app).options(
            f"{PROJECTS}/{uuid.uuid4()}",
            headers={"Origin": FOREIGN, "Access-Control-Request-Method": "DELETE"},
        )
        assert resp.status_code == 400
        assert "access-control-allow-origin" not in resp.headers


# ---------------------------------------------------------------------------
# get-or-create race (two real transactions)
# ---------------------------------------------------------------------------


class TestTechnologyRace:
    """Two transactions resolve the same name. The second must wait on the first's
    uncommitted row, then reuse it (commit) or insert its own (rollback). These tests
    commit to the test database and delete their rows afterwards."""

    def _wait_until_blocked(self, db_engine, pid: int) -> None:
        with db_engine.connect() as conn:
            for _ in range(100):
                wait = conn.execute(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                ).scalar()
                if wait == "Lock":
                    return
                time.sleep(0.05)
        pytest.fail("the second transaction never waited on a lock")

    def _cleanup(self, db_engine, names: list[str]) -> None:
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM technologies WHERE lower(name) = ANY(:names)"),
                {"names": [name.lower() for name in names]},
            )

    @pytest.mark.parametrize("first_outcome", ["commit", "rollback"])
    def test_second_transaction_waits_then_reuses_or_inserts(self, db_engine, first_outcome):
        name = f"Race {uuid.uuid4().hex[:8]}"
        result: dict = {}
        try:
            with Session(db_engine) as first, Session(db_engine) as second:
                [first_id] = service._resolve_technologies(first, [name])
                pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

                def run() -> None:
                    try:
                        result["ids"] = service._resolve_technologies(second, [name.upper()])
                        second.commit()
                    except Exception as exc:  # reported in the main thread
                        result["error"] = exc

                thread = threading.Thread(target=run)
                thread.start()
                self._wait_until_blocked(db_engine, pid)
                getattr(first, first_outcome)()
                thread.join(timeout=10)

            assert not thread.is_alive()
            assert "error" not in result, result.get("error")
            with db_engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT id, name FROM technologies WHERE lower(name) = :n"),
                    {"n": name.lower()},
                ).all()
            assert len(rows) == 1
            if first_outcome == "commit":
                assert result["ids"] == [first_id]
                assert rows[0].name == name
            else:
                assert result["ids"] == [rows[0].id] != [first_id]
                assert rows[0].name == name.upper()
        finally:
            self._cleanup(db_engine, [name])

    def test_overlapping_lists_in_opposite_order(self, db_engine):
        a, b = (f"Race {uuid.uuid4().hex[:8]} {suffix}" for suffix in ("a", "b"))
        result: dict = {}
        try:
            with Session(db_engine) as first, Session(db_engine) as second:
                first_ids = service._resolve_technologies(first, [b, a])
                pid = second.execute(text("SELECT pg_backend_pid()")).scalar_one()

                def run() -> None:
                    try:
                        result["ids"] = service._resolve_technologies(second, [a, b])
                        second.commit()
                    except Exception as exc:
                        result["error"] = exc

                thread = threading.Thread(target=run)
                thread.start()
                self._wait_until_blocked(db_engine, pid)
                first.commit()
                thread.join(timeout=10)

            assert "error" not in result, result.get("error")
            assert result["ids"] == list(reversed(first_ids))
        finally:
            self._cleanup(db_engine, [a, b])
