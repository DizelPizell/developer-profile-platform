"""GET /analytics/profile and GET /analytics/projects/{id} (step 7.2, ADR-0029):
sums for the owner only, the period in UTC days, zeros for quiet projects and days."""

import uuid
from datetime import timedelta

import pytest

from app.clock import utcnow
from app.models.analytics import AnalyticsDailyCount
from tests.conftest import login, make_github_transport
from tests.test_projects import _create, _profile_row, _published

PROFILE = "/api/v1/analytics/profile"
PROJECT_COUNT_KEYS = {"project_views", "demo_clicks", "github_clicks"}
ZERO = dict.fromkeys(PROJECT_COUNT_KEYS, 0)


@pytest.fixture
def owner(auth_client):
    login(auth_client)
    return auth_client


def _add(db_session, profile_id, event_type, count, days_ago=0, project_id=None):
    db_session.add(
        AnalyticsDailyCount(
            profile_id=profile_id,
            project_id=project_id,
            event_type=event_type,
            day=utcnow().date() - timedelta(days=days_ago),
            count=count,
        )
    )
    db_session.flush()


def _get(client, url, status=200):
    resp = client.get(url)
    assert resp.status_code == status, resp.text
    return resp.json()


def test_profile_sums_the_period_and_lists_every_project(owner, db_session):
    first = _published(owner, title="First")
    quiet = _create(owner, title="Quiet")
    profile_id = _profile_row(db_session).id
    first_id = uuid.UUID(first["id"])

    _add(db_session, profile_id, "PROFILE_VIEW", 5)
    _add(db_session, profile_id, "PROFILE_VIEW", 3, days_ago=29)
    _add(db_session, profile_id, "PROFILE_VIEW", 100, days_ago=30)  # outside 30 days
    _add(db_session, profile_id, "CONTACT_CLICK", 2, days_ago=1)
    _add(db_session, profile_id, "GITHUB_CLICK", 1)  # the profile's GitHub link
    _add(db_session, profile_id, "GITHUB_CLICK", 4, project_id=first_id)
    _add(db_session, profile_id, "PROJECT_VIEW", 7, days_ago=2, project_id=first_id)
    _add(db_session, profile_id, "DEMO_CLICK", 2, project_id=first_id)

    body = _get(owner, PROFILE)

    today = utcnow().date()
    assert body["period"] == {
        "days": 30,
        "start": str(today - timedelta(days=29)),
        "end": str(today),
    }
    assert body["totals"] == {
        "profile_views": 8,
        "project_views": 7,
        "demo_clicks": 2,
        "github_clicks": 5,
        "contact_clicks": 2,
    }
    # The order of GET /projects: newest first.
    assert [p["id"] for p in body["projects"]] == [quiet["id"], first["id"]]
    assert body["projects"][0] == {
        "id": quiet["id"],
        "title": "Quiet",
        "status": "DRAFT",
        "visibility": "PRIVATE",
        "counts": ZERO,
    }
    assert body["projects"][1]["counts"] == {
        "project_views": 7,
        "demo_clicks": 2,
        "github_clicks": 4,
    }


def test_profile_period_of_seven_and_ninety_days(owner, db_session):
    profile_id = _profile_row(db_session).id
    _add(db_session, profile_id, "PROFILE_VIEW", 1, days_ago=6)
    _add(db_session, profile_id, "PROFILE_VIEW", 10, days_ago=7)
    _add(db_session, profile_id, "PROFILE_VIEW", 100, days_ago=89)
    _add(db_session, profile_id, "PROFILE_VIEW", 1000, days_ago=90)

    assert _get(owner, f"{PROFILE}?days=7")["totals"]["profile_views"] == 1
    assert _get(owner, f"{PROFILE}?days=90")["totals"]["profile_views"] == 111


def test_profile_lists_a_draft_without_a_title(owner):
    draft = _create(owner)

    body = _get(owner, PROFILE)

    assert body["projects"] == [
        {
            "id": draft["id"],
            "title": None,
            "status": "DRAFT",
            "visibility": "PRIVATE",
            "counts": ZERO,
        }
    ]


def test_profile_without_events_is_all_zeros(owner):
    body = _get(owner, PROFILE)

    assert set(body["totals"].values()) == {0}
    assert body["projects"] == []


def test_counters_of_another_profile_are_not_shown(owner, make_auth_client, db_session):

    other = make_auth_client(make_github_transport(github_user_id=10002, github_login="other"))
    login(other)
    other_project = _published(other, title="Theirs")
    other_profile_id = _profile_row(db_session, github_user_id=10002).id
    _add(db_session, other_profile_id, "PROFILE_VIEW", 9)
    _add(db_session, other_profile_id, "PROJECT_VIEW", 9, project_id=uuid.UUID(other_project["id"]))

    assert _get(owner, PROFILE)["totals"]["profile_views"] == 0
    error = _get(owner, f"/api/v1/analytics/projects/{other_project['id']}", status=404)
    assert error["error"]["code"] == "NOT_FOUND"


def test_project_daily_has_every_day_oldest_first(owner, db_session):
    project = _published(owner)
    project_id = uuid.UUID(project["id"])
    profile_id = _profile_row(db_session).id
    _add(db_session, profile_id, "PROJECT_VIEW", 3, project_id=project_id)
    _add(db_session, profile_id, "DEMO_CLICK", 1, project_id=project_id)
    _add(db_session, profile_id, "PROJECT_VIEW", 2, days_ago=6, project_id=project_id)
    _add(db_session, profile_id, "GITHUB_CLICK", 5, days_ago=7, project_id=project_id)
    _add(db_session, profile_id, "PROFILE_VIEW", 50)

    body = _get(owner, f"/api/v1/analytics/projects/{project['id']}?days=7")

    today = utcnow().date()
    assert body["period"]["start"] == str(today - timedelta(days=6))
    assert body["totals"] == {"project_views": 5, "demo_clicks": 1, "github_clicks": 0}
    assert [d["day"] for d in body["daily"]] == [
        str(today - timedelta(days=offset)) for offset in range(6, -1, -1)
    ]
    assert body["daily"][0]["counts"] == {**ZERO, "project_views": 2}
    assert body["daily"][1]["counts"] == ZERO
    assert body["daily"][-1]["counts"] == {**ZERO, "project_views": 3, "demo_clicks": 1}


def test_project_default_period_is_thirty_days(owner):
    project = _create(owner, title="Draft")

    body = _get(owner, f"/api/v1/analytics/projects/{project['id']}")

    assert body["period"]["days"] == 30
    assert len(body["daily"]) == 30
    assert body["totals"] == ZERO


@pytest.mark.parametrize("project_id", ["not-a-uuid", str(uuid.uuid4())])
def test_unknown_project_is_not_found(owner, project_id):
    error = _get(owner, f"/api/v1/analytics/projects/{project_id}", status=404)
    assert error["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("days", ["1", "14", "365", "abc"])
def test_other_periods_are_a_validation_error(owner, days):
    error = _get(owner, f"{PROFILE}?days={days}", status=422)
    assert error["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("url", [PROFILE, f"/api/v1/analytics/projects/{uuid.uuid4()}"])
def test_reading_requires_a_session(make_auth_client, url):
    error = _get(make_auth_client(), url, status=401)
    assert error["error"]["code"] == "UNAUTHORIZED"
