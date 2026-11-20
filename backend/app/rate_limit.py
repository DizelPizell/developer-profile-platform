"""Per-IP rate limits for the endpoints a browser calls without a session (ADR-024).

Counters live in this process's memory: one uvicorn process, one host (ADR-021).
A restart resets them; that is accepted, the limit slows scraping, it does not
stop it (ADR-020).
"""

import math
import threading
import time

from fastapi import Request

from app.errors import AppError

# Entries are pruned only past this size: a few hundred visitors never pay for it.
_PRUNE_ABOVE = 10_000


class RateLimiter:
    """Fixed windows aligned to the clock; a request counts only when it passes."""

    def __init__(self, *limits: tuple[int, int]) -> None:
        # (requests, window seconds), all must pass.
        self._limits = limits
        self._counts: dict[tuple[int, str], tuple[float, int]] = {}
        # Sync endpoints run in a thread pool.
        self._lock = threading.Lock()

    def hit(self, key: str, now: float) -> int | None:
        """None when the request passes, otherwise seconds until it would."""
        with self._lock:
            if len(self._counts) > _PRUNE_ABOVE:
                self._prune(now)
            retry_after = 0.0
            windows = []
            for index, (allowed, seconds) in enumerate(self._limits):
                start = now - now % seconds
                window_start, count = self._counts.get((index, key), (start, 0))
                if window_start != start:
                    count = 0
                if count >= allowed:
                    retry_after = max(retry_after, start + seconds - now)
                windows.append(((index, key), start, count))
            if retry_after:
                return max(1, math.ceil(retry_after))
            for slot, start, count in windows:
                self._counts[slot] = (start, count + 1)
            return None

    def _prune(self, now: float) -> None:
        self._counts = {
            slot: value
            for slot, value in self._counts.items()
            if value[0] + self._limits[slot[0]][1] > now
        }

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


# Revealing an email or a phone (ADR-020).
contacts_limiter = RateLimiter((10, 60), (50, 3600))
# GitHub login and its callback, which exchanges the code with GitHub (ADR-012).
login_limiter = RateLimiter((20, 60))
# Analytics events from public pages (ADR-0029).
events_limiter = RateLimiter((60, 60))


def client_ip(request: Request) -> str:
    # uvicorn takes it from X-Forwarded-For only when Nginx sent it (ADR-021).
    return request.client.host if request.client else "unknown"


def retry_after(limiter: RateLimiter, request: Request) -> int | None:
    return limiter.hit(client_ip(request), time.time())


def rate_limited(seconds: int) -> AppError:
    return AppError(
        "RATE_LIMITED",
        "Too many requests, try again later",
        429,
        headers={"Retry-After": str(seconds)},
    )


def limit_contacts(request: Request) -> None:
    seconds = retry_after(contacts_limiter, request)
    if seconds is not None:
        raise rate_limited(seconds)


def limit_events(request: Request) -> None:
    seconds = retry_after(events_limiter, request)
    if seconds is not None:
        raise rate_limited(seconds)
