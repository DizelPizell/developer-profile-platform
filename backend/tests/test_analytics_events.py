"""POST /analytics/events (step 7.1, ADR-0029): daily counters, one 202 for counted and
dropped events, the owner's own views dropped, the limit per IP."""

import uuid

import pytest
from sqlalchemy import select

from app.clock import utcnow
from app.models.analytics import AnalyticsDailyCount
from tests.conftest import login
from tests.test_projects import _create, _published, _url

EVENTS = "/api/v1/analytics/events"


@pytest.fixture
def owner(auth_client):
    login(auth_client)
    auth_client.patch("/api/v1/profile", json={"display_name": "Ann", "headline": "Dev"})
    assert auth_client.post("/api/v1/profile/publish").status_code == 200
    return auth_client


@pytest.fixture
def slug(owner) -> str:
    return owner.get("/api/v1/profile").json()["slug"]


@pytest.fixture
def project(owner) -> dict:
    return _published(owner)


@pytest.fixture
def visitor(owner, make_auth_client):
    """No session; sends the frontend Origin, as the browser does."""
    return make_auth_client()


def _send(client, **body):
    resp = client.post(EVENTS, json=body)
    assert resp.status_code == 202, resp.text
    assert resp.content == b""


def _counts(db_session) -> list[tuple]:
    return list(
        db_session.execute(
            select(
                AnalyticsDailyCount.project_id,
                AnalyticsDailyCount.event_type,
                AnalyticsDailyCount.day,
                AnalyticsDailyCount.count,
            ).order_by(AnalyticsDailyCount.event_type)
        )
    )


def test_profile_views_add_up_in_one_row(visitor, slug, db_session):
    _send(visitor, type="PROFILE_VIEW", slug=slug)
    _send(visitor, type="PROFILE_VIEW", slug=slug.upper())

    assert _counts(db_session) == [(None, "PROFILE_VIEW", utcnow().date(), 2)]


def test_project_events_are_counted_per_project(visitor, slug, project, db_session):
    for kind in ("PROJECT_VIEW", "DEMO_CLICK", "GITHUB_CLICK", "PROJECT_VIEW"):
        _send(visitor, type=kind, slug=slug, project_id=project["id"])
    _send(visitor, type="GITHUB_CLICK", slug=slug)
    _send(visitor, type="CONTACT_CLICK", slug=slug)

    today = utcnow().date()
    rows = {(str(p) if p else None, kind, count) for p, kind, day, count in _counts(db_session)}
    assert {day for *_, day, _ in _counts(db_session)} == {today}
    assert rows == {
        (None, "CONTACT_CLICK", 1),
        (project["id"], "DEMO_CLICK", 1),
        (project["id"], "GITHUB_CLICK", 1),
        (None, "GITHUB_CLICK", 1),
        (project["id"], "PROJECT_VIEW", 2),
    }


def test_dropped_events_answer_202_and_count_nothing(visitor, owner, slug, project, db_session):
    draft = _create(owner, title="Draft")
    hidden = _published(owner, title="Hidden")
    assert owner.post(_url(hidden, "visibility"), json={"visibility": "PRIVATE"}).status_code == 200

    for body in (
        {"type": "PROFILE_VIEW", "slug": "nobody-here"},
        {"type": "PROFILE_VIEW", "slug": "Not a slug!"},
        {"type": "PROFILE_VIEW", "slug": slug, "project_id": project["id"]},
        {"type": "CONTACT_CLICK", "slug": slug, "project_id": project["id"]},
        {"type": "PROJECT_VIEW", "slug": slug},
        {"type": "DEMO_CLICK", "slug": slug},
        {"type": "PROJECT_VIEW", "slug": slug, "project_id": draft["id"]},
        {"type": "PROJECT_VIEW", "slug": slug, "project_id": hidden["id"]},
        {"type": "PROJECT_VIEW", "slug": slug, "project_id": "not-a-uuid"},
        {"type": "GITHUB_CLICK", "slug": slug, "project_id": str(uuid.uuid4())},
    ):
        _send(visitor, **body)

    assert _counts(db_session) == []


def test_unpublished_profile_drops_events(visitor, owner, slug, project, db_session):
    assert owner.post("/api/v1/profile/unpublish").status_code == 200

    _send(visitor, type="PROFILE_VIEW", slug=slug)
    _send(visitor, type="PROJECT_VIEW", slug=slug, project_id=project["id"])

    assert _counts(db_session) == []


def test_owner_views_are_not_counted(owner, slug, project, db_session):
    _send(owner, type="PROFILE_VIEW", slug=slug)
    _send(owner, type="PROJECT_VIEW", slug=slug, project_id=project["id"])

    assert _counts(db_session) == []


@pytest.mark.parametrize(
    "body",
    [
        {"type": "CV_DOWNLOAD", "slug": "ann"},
        {"slug": "ann"},
        {"type": "PROFILE_VIEW"},
        {"type": "PROFILE_VIEW", "slug": "ann", "referrer": "https://example.com"},
        {"type": "PROFILE_VIEW", "slug": "a" * 101},
    ],
)
def test_malformed_body_is_a_validation_error(visitor, body):
    resp = visitor.post(EVENTS, json=body)
    assert resp.status_code == 422, resp.text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_origin_is_required(owner, slug, make_auth_client, db_session):
    resp = make_auth_client(send_origin=False).post(
        EVENTS, json={"type": "PROFILE_VIEW", "slug": slug}
    )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "CSRF_ORIGIN_INVALID"
    assert _counts(db_session) == []


def test_sixty_events_a_minute_per_ip(visitor, slug, db_session):
    for _ in range(60):
        _send(visitor, type="PROFILE_VIEW", slug=slug)

    resp = visitor.post(EVENTS, json={"type": "PROFILE_VIEW", "slug": slug})

    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "RATE_LIMITED"
    assert int(resp.headers["Retry-After"]) >= 1
    assert _counts(db_session)[0][3] == 60


def test_counters_go_with_the_project(visitor, owner, slug, project, db_session):
    _send(visitor, type="PROFILE_VIEW", slug=slug)
    _send(visitor, type="PROJECT_VIEW", slug=slug, project_id=project["id"])

    assert owner.delete(_url(project)).status_code == 204
    db_session.expire_all()

    assert [kind for _, kind, *_ in _counts(db_session)] == ["PROFILE_VIEW"]
