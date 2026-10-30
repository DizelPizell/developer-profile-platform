"""The repository list page cache (ADR-017): lifetime, size bound, threads."""

import threading
import uuid
from datetime import datetime, timedelta

import pytest

from app.github.client import RepositoryPage
from app.github.page_cache import RepositoryPageCache, repository_page_cache
from app.settings import settings

T0 = datetime(2026, 10, 30, 12, 0, 0)
TTL = timedelta(seconds=300)
USER = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _page(has_next: bool = False) -> RepositoryPage:
    return RepositoryPage(items=(), has_next=has_next)


def test_page_is_kept_until_its_lifetime_ends():
    cache = RepositoryPageCache(TTL)
    page = _page()
    cache.put(USER, 1, page, T0)

    assert cache.get(USER, 1, T0 + TTL - timedelta(microseconds=1)) is page
    assert cache.get(USER, 1, T0 + TTL) is None


def test_key_is_user_and_page():
    cache = RepositoryPageCache(TTL)
    cache.put(USER, 1, _page(), T0)

    assert cache.get(USER, 2, T0) is None
    assert cache.get(OTHER, 1, T0) is None


def test_least_recently_used_page_leaves_first():
    cache = RepositoryPageCache(TTL, max_pages=2)
    cache.put(USER, 1, _page(), T0)
    cache.put(USER, 2, _page(), T0)
    cache.get(USER, 1, T0)  # page 2 is now the least recently used

    cache.put(USER, 3, _page(), T0)

    assert cache.get(USER, 2, T0) is None
    assert cache.get(USER, 1, T0) is not None
    assert cache.get(USER, 3, T0) is not None


def test_expired_pages_are_dropped_when_written():
    cache = RepositoryPageCache(TTL)
    cache.put(USER, 1, _page(), T0)
    cache.put(OTHER, 1, _page(), T0 + timedelta(seconds=10))

    cache.put(USER, 2, _page(), T0 + TTL)

    assert set(cache._pages) == {(OTHER, 1), (USER, 2)}


@pytest.mark.parametrize(("ttl", "size"), [(timedelta(0), 1), (TTL, 0)])
def test_invalid_lifetime_or_size_is_rejected(ttl, size):
    with pytest.raises(ValueError):
        RepositoryPageCache(ttl, max_pages=size)


def test_shared_cache_uses_the_setting():
    assert repository_page_cache._ttl == timedelta(
        seconds=settings.github_repository_list_cache_seconds
    )


def test_concurrent_writers_keep_the_bound():
    cache = RepositoryPageCache(TTL, max_pages=10)
    threads = 20
    start = threading.Barrier(threads)
    errors: list[BaseException] = []

    def worker(index: int) -> None:
        start.wait()
        try:
            for page in range(1, 51):
                cache.put(uuid.UUID(int=index), page, _page(), T0)
                cache.get(uuid.UUID(int=index), page, T0)
        except BaseException as exc:  # noqa: BLE001 - reported below
            errors.append(exc)

    pool = [threading.Thread(target=worker, args=(i,)) for i in range(threads)]
    for thread in pool:
        thread.start()
    for thread in pool:
        thread.join()

    assert errors == []
    assert len(cache._pages) == 10
