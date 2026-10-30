"""In-memory cache of repository list pages (ADR-017).

Kept in this process's memory, like the request budget (ADR-018). Holds only
successful pages and only GitHub's fields: whether an item is linked is read
from the database on every call and never kept here.
"""

import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta

from app.github.client import RepositoryPage
from app.settings import settings

# A page holds at most 100 items of a few hundred bytes each; 500 pages stay
# within tens of megabytes.
MAX_CACHED_PAGES = 500


class RepositoryPageCache:
    """Pages keyed by user and page number, kept for `ttl`.

    When full, the least recently used page leaves first. Expired pages are
    dropped when the cache is written.
    """

    def __init__(self, ttl: timedelta, max_pages: int = MAX_CACHED_PAGES) -> None:
        if ttl <= timedelta(0) or max_pages < 1:
            raise ValueError("The cache needs a positive lifetime and size")
        self._ttl = ttl
        self._max_pages = max_pages
        self._lock = threading.Lock()
        self._pages: OrderedDict[tuple[uuid.UUID, int], tuple[datetime, RepositoryPage]] = (
            OrderedDict()
        )

    def get(self, user_id: uuid.UUID, page: int, now: datetime) -> RepositoryPage | None:
        key = (user_id, page)
        with self._lock:
            entry = self._pages.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if now - stored_at >= self._ttl:
                del self._pages[key]
                return None
            self._pages.move_to_end(key)
            return value

    def put(self, user_id: uuid.UUID, page: int, value: RepositoryPage, now: datetime) -> None:
        key = (user_id, page)
        with self._lock:
            for expired in [k for k, (at, _) in self._pages.items() if now - at >= self._ttl]:
                del self._pages[expired]
            self._pages[key] = (now, value)
            self._pages.move_to_end(key)
            while len(self._pages) > self._max_pages:
                self._pages.popitem(last=False)


repository_page_cache = RepositoryPageCache(
    timedelta(seconds=settings.github_repository_list_cache_seconds)
)
