"""Per-user GitHub request budget (ADR-018).

Kept in this process's memory: V1 runs one backend process. A restart resets
it; several processes would each keep their own, multiplying the limit.
"""

import math
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.github.client import GitHubApiClient
from app.settings import settings

WINDOW = timedelta(hours=1)
SWEEP_INTERVAL = timedelta(minutes=1)

# The most an operation may spend, reserved before it starts (ADR-018).
LIST_PAGE_COST = 1
LINK_COST = 6  # the repository plus up to 5 contributor pages; import too
MANUAL_SYNC_COST = 7  # metadata, languages, up to 5 contributor pages
MAX_OPERATION_COST = MANUAL_SYNC_COST


class GitHubUserLimitReached(Exception):
    """The user's budget does not cover the operation: 429 GITHUB_USER_LIMIT_REACHED."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("GitHub request budget of the user is exhausted")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _Charge:
    at: datetime
    amount: int


class UserRequestBudget:
    """At most `limit` GitHub requests per user in any sliding 60 minutes."""

    def __init__(self, limit: int) -> None:
        if limit < MAX_OPERATION_COST:
            raise ValueError("The limit must cover the most expensive operation")
        self._limit = limit
        self._lock = threading.Lock()
        self._charges: dict[uuid.UUID, list[_Charge]] = {}
        self._swept_at: datetime | None = None

    @contextmanager
    def spend(
        self, user_id: uuid.UUID, max_requests: int, now: datetime, client: GitHubApiClient
    ) -> Iterator[None]:
        """Reserve the worst case, run the operation, keep what the client sent.

        For link, import and the list. Settles on every exit, errors included, so
        a refused or paused operation costs only the requests that reached GitHub
        (ADR-018).
        """
        charge = self._reserve(user_id, max_requests, now)
        sent_before = client.requests_sent
        try:
            yield
        finally:
            self._settle(charge, client.requests_sent - sent_before)

    def charge(self, user_id: uuid.UUID, requests: int, now: datetime) -> None:
        """A fixed charge with nothing to settle: a manual sync that queues a job
        counts its maximum, because the worker makes the requests later (ADR-018)."""
        self._reserve(user_id, requests, now)

    def spent(self, user_id: uuid.UUID, now: datetime) -> int:
        with self._lock:
            return sum(c.amount for c in self._charges.get(user_id, []) if c.at > now - WINDOW)

    def _reserve(self, user_id: uuid.UUID, max_requests: int, now: datetime) -> _Charge:
        if not 1 <= max_requests <= self._limit:
            raise ValueError("Invalid operation cost")
        with self._lock:
            self._sweep(now)
            charges = [c for c in self._charges.get(user_id, []) if c.at > now - WINDOW]
            spent = sum(c.amount for c in charges)
            if spent + max_requests > self._limit:
                self._charges[user_id] = charges
                raise GitHubUserLimitReached(self._retry_after(charges, spent, max_requests, now))
            charge = _Charge(at=now, amount=max_requests)
            charges.append(charge)
            self._charges[user_id] = charges
            return charge

    def _sweep(self, now: datetime) -> None:
        # At most once a minute, forget users with no charge left in the window, so
        # the dict holds only users active in the last hour. Called under the lock.
        if self._swept_at is not None and now - self._swept_at < SWEEP_INTERVAL:
            return
        self._swept_at = now
        for user_id in [
            user_id
            for user_id, charges in self._charges.items()
            if all(c.at <= now - WINDOW for c in charges)
        ]:
            del self._charges[user_id]

    def _settle(self, charge: _Charge, used: int) -> None:
        # Keep only the requests actually sent, at most the reserved amount.
        with self._lock:
            charge.amount = max(0, min(used, charge.amount))

    def _retry_after(
        self, charges: list[_Charge], spent: int, max_requests: int, now: datetime
    ) -> int:
        # Charges leave the window oldest first; wait until enough of them have.
        for charge in sorted(charges, key=lambda c: c.at):
            spent -= charge.amount
            if spent + max_requests <= self._limit:
                return max(1, math.ceil((charge.at + WINDOW - now).total_seconds()))
        return math.ceil(WINDOW.total_seconds())


user_request_budget = UserRequestBudget(settings.github_user_requests_per_hour)
