"""Per-user GitHub request budget and the backend's rate-limit pause (ADR-018)."""

import threading
import time
import uuid
from datetime import datetime, timedelta

import httpx
import pytest
from pydantic import ValidationError

from app.github import budget as budget_module
from app.github.budget import (
    LINK_COST,
    LIST_PAGE_COST,
    MANUAL_SYNC_COST,
    GitHubUserLimitReached,
    UserRequestBudget,
    user_request_budget,
)
from app.github.client import (
    GitHubApiClient,
    GitHubRateLimited,
    InvalidGitHubInput,
    RateLimitPause,
    RateLimitState,
)
from app.settings import Settings, settings

T0 = datetime(2026, 10, 30, 12, 0, 0)
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")


def test_operation_costs_follow_adr_018():
    assert (LIST_PAGE_COST, LINK_COST, MANUAL_SYNC_COST) == (1, 6, 7)


def test_settings_default_and_minimum():
    assert Settings.model_fields["github_user_requests_per_hour"].default == 60
    assert user_request_budget._limit == settings.github_user_requests_per_hour
    with pytest.raises(ValidationError):
        Settings(_env_file=None, github_user_requests_per_hour=6)


# Budget.


def test_reserve_holds_the_worst_case_until_settled():
    budget = UserRequestBudget(60)

    reservation = budget.reserve(USER, LINK_COST, T0)

    assert budget.spent(USER, T0) == 6
    reservation.settle(1)
    assert budget.spent(USER, T0) == 1


@pytest.mark.parametrize(("used", "kept"), [(-3, 0), (0, 0), (6, 6), (40, 6)])
def test_settle_keeps_between_zero_and_reserved(used, kept):
    budget = UserRequestBudget(60)

    budget.reserve(USER, LINK_COST, T0).settle(used)

    assert budget.spent(USER, T0) == kept


def test_unsettled_reservation_counts_in_full():
    budget = UserRequestBudget(60)

    budget.reserve(USER, MANUAL_SYNC_COST, T0)

    assert budget.spent(USER, T0) == 7


def test_over_budget_is_refused_with_retry_after():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 30, T0).settle(30)
    budget.reserve(USER, 30, T0 + timedelta(minutes=10)).settle(28)

    with pytest.raises(GitHubUserLimitReached) as exc:
        budget.reserve(USER, LINK_COST, T0 + timedelta(minutes=20))

    # 58 spent; 6 more fit only once the first 30 leave the window at T0 + 60 min.
    assert exc.value.retry_after_seconds == 40 * 60
    assert budget.spent(USER, T0 + timedelta(minutes=20)) == 58


def test_cheaper_operation_still_fits():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 30, T0).settle(30)
    budget.reserve(USER, 28, T0).settle(28)

    with pytest.raises(GitHubUserLimitReached):
        budget.reserve(USER, LINK_COST, T0)
    budget.reserve(USER, LIST_PAGE_COST, T0)
    budget.reserve(USER, LIST_PAGE_COST, T0)
    with pytest.raises(GitHubUserLimitReached):
        budget.reserve(USER, LIST_PAGE_COST, T0)


def test_window_slides():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 60, T0).settle(60)

    with pytest.raises(GitHubUserLimitReached) as exc:
        budget.reserve(USER, 1, T0 + timedelta(minutes=59, seconds=59, microseconds=500_000))
    assert exc.value.retry_after_seconds == 1

    budget.reserve(USER, 1, T0 + timedelta(hours=1))
    assert budget.spent(USER, T0 + timedelta(hours=1)) == 1


def test_users_have_separate_budgets():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 60, T0).settle(60)

    budget.reserve(OTHER, MANUAL_SYNC_COST, T0)

    assert budget.spent(OTHER, T0) == 7


@pytest.mark.parametrize("cost", [0, -1, 61])
def test_invalid_cost_is_rejected(cost):
    with pytest.raises(ValueError):
        UserRequestBudget(60).reserve(USER, cost, T0)


def test_limit_must_cover_a_manual_sync():
    with pytest.raises(ValueError):
        UserRequestBudget(6)


def test_concurrent_reservations_never_exceed_the_limit(monkeypatch):
    # Yield to other threads between the check and the append, so that a missing
    # lock shows up as over-granting instead of hiding behind the GIL.
    original = budget_module._Charge

    def yielding_charge(**fields):
        time.sleep(0.001)
        return original(**fields)

    monkeypatch.setattr(budget_module, "_Charge", yielding_charge)
    budget = UserRequestBudget(60)
    threads = 40
    start = threading.Barrier(threads)
    granted: list[int] = []
    refused: list[int] = []

    def worker() -> None:
        start.wait()
        try:
            budget.reserve(USER, LINK_COST, T0)
        except GitHubUserLimitReached:
            refused.append(1)
        else:
            granted.append(1)

    pool = [threading.Thread(target=worker) for _ in range(threads)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()

    assert len(granted) == 10
    assert len(refused) == 30
    assert budget.spent(USER, T0) == 60


# The backend's pause after an exhausted limit.


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _limited_then_ok(reset: datetime):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(
                403,
                json={"message": "API rate limit exceeded"},
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": str(int((reset - datetime(1970, 1, 1)).total_seconds())),
                },
            )
        return httpx.Response(200, json={})

    return handler, calls


def _client(handler, pause: RateLimitPause, clock: Clock) -> GitHubApiClient:
    return GitHubApiClient(
        httpx.Client(transport=httpx.MockTransport(handler)),
        "client-id",
        "client-secret",
        rate_limits=RateLimitState(),
        pause=pause,
        now=clock,
    )


def test_exhausted_limit_pauses_requests_until_reset():
    reset = T0 + timedelta(minutes=10)
    handler, calls = _limited_then_ok(reset)
    pause, clock = RateLimitPause(), Clock(T0)
    client = _client(handler, pause, clock)

    with pytest.raises(GitHubRateLimited):
        client.get_languages("octocat", "Hello-World")
    clock.now = reset - timedelta(seconds=1)
    with pytest.raises(GitHubRateLimited) as exc:
        client.get_languages("octocat", "Hello-World")

    assert exc.value.retry_at == reset
    assert len(calls) == 1
    assert client.requests_sent == 1

    clock.now = reset
    assert client.get_languages("octocat", "Hello-World") == {}
    assert len(calls) == 2


def test_pause_is_shared_by_clients_of_the_process():
    reset = T0 + timedelta(minutes=10)
    handler, calls = _limited_then_ok(reset)
    pause, clock = RateLimitPause(), Clock(T0)

    with pytest.raises(GitHubRateLimited):
        _client(handler, pause, clock).get_languages("octocat", "Hello-World")
    with pytest.raises(GitHubRateLimited):
        _client(handler, pause, clock).get_repository_by_id(1296269)

    assert len(calls) == 1


def test_secondary_limit_pauses_for_its_retry_after():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, headers={"retry-after": "90"})

    pause, clock = RateLimitPause(), Clock(T0)
    client = _client(handler, pause, clock)

    with pytest.raises(GitHubRateLimited):
        client.get_languages("octocat", "Hello-World")
    clock.now = T0 + timedelta(seconds=89)
    with pytest.raises(GitHubRateLimited) as exc:
        client.get_languages("octocat", "Hello-World")

    assert exc.value.retry_at == T0 + timedelta(seconds=90)
    assert len(calls) == 1


def test_pause_keeps_the_later_time():
    pause = RateLimitPause()
    pause.start(T0 + timedelta(minutes=10))
    pause.start(T0 + timedelta(minutes=5))

    with pytest.raises(GitHubRateLimited) as exc:
        pause.check(T0 + timedelta(minutes=7))
    assert exc.value.retry_at == T0 + timedelta(minutes=10)
    pause.check(T0 + timedelta(minutes=10))


def test_invalid_input_is_reported_before_the_pause():
    pause = RateLimitPause()
    pause.start(T0 + timedelta(minutes=10))
    client = _client(lambda r: httpx.Response(200, json={}), pause, Clock(T0))

    with pytest.raises(InvalidGitHubInput):
        client.get_languages("octocat", "..")


# spend(): the reservation is settled on every exit.


def _owner_repository(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": 1296269,
            "name": "Hello-World",
            "full_name": "octocat/Hello-World",
            "owner": {"login": "octocat", "id": 583231},
            "private": False,
            "html_url": "https://github.com/octocat/Hello-World",
            "description": None,
            "fork": False,
            "archived": False,
            "pushed_at": None,
        },
    )


def test_spend_keeps_the_requests_sent():
    budget = UserRequestBudget(60)
    client = _client(_owner_repository, RateLimitPause(), Clock(T0))

    with budget.spend(USER, LINK_COST, T0, client):
        client.get_repository("octocat", "Hello-World")

    assert budget.spent(USER, T0) == 1


def test_spend_settles_when_the_operation_fails():
    budget = UserRequestBudget(60)
    pause = RateLimitPause()
    pause.start(T0 + timedelta(minutes=5))
    client = _client(_owner_repository, pause, Clock(T0))

    with pytest.raises(GitHubRateLimited):
        with budget.spend(USER, LINK_COST, T0, client):
            client.get_repository("octocat", "Hello-World")

    assert budget.spent(USER, T0) == 0


def test_spend_counts_only_this_operation():
    budget = UserRequestBudget(60)
    client = _client(_owner_repository, RateLimitPause(), Clock(T0))
    client.get_repository("octocat", "Hello-World")

    with budget.spend(USER, LIST_PAGE_COST, T0, client):
        client.get_repository("octocat", "Hello-World")

    assert budget.spent(USER, T0) == 1


def test_refused_spend_does_not_run_or_charge():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 60, T0)
    client = _client(_owner_repository, RateLimitPause(), Clock(T0))

    with pytest.raises(GitHubUserLimitReached):
        with budget.spend(USER, LINK_COST, T0, client):
            client.get_repository("octocat", "Hello-World")

    assert client.requests_sent == 0
    assert budget.spent(USER, T0) == 60


def test_users_without_recent_charges_are_forgotten():
    budget = UserRequestBudget(60)
    budget.reserve(USER, 1, T0)
    budget.reserve(OTHER, 1, T0 + timedelta(minutes=30))

    budget.reserve(OTHER, 1, T0 + timedelta(minutes=61))

    assert set(budget._charges) == {OTHER}
