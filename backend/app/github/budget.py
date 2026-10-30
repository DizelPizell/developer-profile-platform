"""Per-user GitHub request budget (ADR-018).

Kept in this process's memory: V1 runs one backend process. A restart resets
it; several processes would each keep their own, multiplying the limit.
"""

import math
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.settings import settings

WINDOW = timedelta(hours=1)

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


class Reservation:
    """The worst case of one operation, held until settle() records what it spent."""

    def __init__(self, budget: "UserRequestBudget", charge: _Charge) -> None:
        self._budget = budget
        self._charge = charge
        self.reserved = charge.amount

    def settle(self, used: int) -> None:
        """Keep only the requests actually sent (at most the reserved amount)."""
        self._budget._settle(self._charge, max(0, min(used, self.reserved)))


class UserRequestBudget:
    """At most `limit` GitHub requests per user in any sliding 60 minutes."""

    def __init__(self, limit: int) -> None:
        if limit < MAX_OPERATION_COST:
            raise ValueError("The limit must cover the most expensive operation")
        self._limit = limit
        self._lock = threading.Lock()
        self._charges: dict[uuid.UUID, list[_Charge]] = {}

    def reserve(self, user_id: uuid.UUID, max_requests: int, now: datetime) -> Reservation:
        if not 1 <= max_requests <= self._limit:
            raise ValueError("Invalid operation cost")
        with self._lock:
            charges = [c for c in self._charges.get(user_id, []) if c.at > now - WINDOW]
            spent = sum(c.amount for c in charges)
            if spent + max_requests > self._limit:
                self._charges[user_id] = charges
                raise GitHubUserLimitReached(self._retry_after(charges, spent, max_requests, now))
            charge = _Charge(at=now, amount=max_requests)
            charges.append(charge)
            self._charges[user_id] = charges
            return Reservation(self, charge)

    def spent(self, user_id: uuid.UUID, now: datetime) -> int:
        with self._lock:
            return sum(c.amount for c in self._charges.get(user_id, []) if c.at > now - WINDOW)

    def _settle(self, charge: _Charge, used: int) -> None:
        with self._lock:
            charge.amount = used

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
