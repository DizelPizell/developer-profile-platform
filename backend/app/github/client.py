"""Read-only client for public GitHub data, with the app's credentials (ADR-016).

Requests go only to https://api.github.com; paths are built from validated
segments. Redirects are never followed: a moved repository is reported as
GitHubMoved with the id GitHub points to. Response bodies, URLs and credentials
are never logged or put into exception messages.
"""

import base64
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.github.constants import (
    GITHUB_API,
    GITHUB_HTML_URL_PREFIX,
    MAX_BIGINT,
    MAX_CONTRIBUTOR_PAGES,
    MAX_LIST_PAGE,
    PER_PAGE,
    is_valid_name,
    is_valid_owner,
)

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)
_USER_AGENT = "developer-profile-platform"

# GitHub's guidance when a secondary limit gives no retry-after (ADR-018).
SECONDARY_LIMIT_WAIT = timedelta(seconds=60)
# The primary limit resets every hour; a longer wait from a header is not believed.
MAX_RATE_LIMIT_WAIT = timedelta(hours=1)
# A wait of zero would make the pause end at once and the next request hit the limit.
MIN_RATE_LIMIT_WAIT = timedelta(seconds=1)

_MOVED_TO = re.compile(re.escape(GITHUB_API) + r"/repositories/([1-9][0-9]{0,18})(?:[/?#].*)?")


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class InvalidGitHubInput(ValueError):
    """An owner, name, id or page that fails the safety filter; nothing was sent."""


class GitHubError(Exception):
    """Base of the client's errors. Messages are fixed text, never GitHub's body."""


class GitHubNotFound(GitHubError):
    def __init__(self) -> None:
        super().__init__("GitHub resource not found or not public")


class GitHubRateLimited(GitHubError):
    """The platform's budget is exhausted until retry_at (naive UTC)."""

    def __init__(self, retry_at: datetime) -> None:
        super().__init__("GitHub rate limit exhausted")
        self.retry_at = retry_at


class GitHubUnavailable(GitHubError):
    """Timeout, network error, 5xx or a malformed body; retryable (ADR-018)."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(f"GitHub is unavailable ({reason})")
        self.reason = reason
        self.status = status


class GitHubMoved(GitHubError):
    """A renamed or transferred repository; the caller decides whether to read it by id."""

    def __init__(self, repository_id: int) -> None:
        super().__init__("GitHub repository moved")
        self.repository_id = repository_id


class GitHubUnexpected(GitHubError):
    def __init__(self, status: int) -> None:
        super().__init__(f"Unexpected GitHub status {status}")
        self.status = status


class GitHubCredentialsRejected(GitHubUnexpected):
    """401: a configuration error, not a job failure (ADR-016)."""


@dataclass(frozen=True)
class RateLimit:
    """GitHub's x-ratelimit-* headers of one response; missing or invalid values are None."""

    limit: int | None
    remaining: int | None
    reset_at: datetime | None
    used: int | None
    resource: str | None


class RateLimitState:
    """The latest rate limit seen by this process, shared by its requests.

    Responses may be processed out of order: within one reset window the lowest
    remaining is kept, and a response from an older window is ignored.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latest: RateLimit | None = None

    def update(self, value: RateLimit) -> None:
        with self._lock:
            current = self._latest
            if current is not None and current.reset_at and value.reset_at:
                if value.reset_at < current.reset_at:
                    return
                if (
                    value.reset_at == current.reset_at
                    and current.remaining is not None
                    and (value.remaining is None or value.remaining > current.remaining)
                ):
                    return
            self._latest = value

    @property
    def latest(self) -> RateLimit | None:
        with self._lock:
            return self._latest


rate_limit_state = RateLimitState()


class RateLimitPause:
    """After an exhausted-limit answer, no request until the reset (ADR-018).

    Each process keeps its own: the backend's makes link, import and the list
    answer 503 GITHUB_RATE_LIMITED without calling GitHub.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._until: datetime | None = None

    def start(self, until: datetime) -> None:
        with self._lock:
            if self._until is None or until > self._until:
                self._until = until

    def check(self, now: datetime) -> None:
        with self._lock:
            until = self._until
        if until is not None and now < until:
            raise GitHubRateLimited(until)


backend_pause = RateLimitPause()


@dataclass(frozen=True)
class GitHubRepositoryListEntry:
    """A repository as a list shows it: GitHub's lists carry no parent, so this type
    has no parent_full_name and cannot overwrite a stored one."""

    github_repo_id: int
    owner_github_id: int
    owner_login: str
    name: str
    full_name: str
    html_url: str
    description: str | None
    is_fork: bool
    is_archived: bool
    pushed_at: datetime | None


@dataclass(frozen=True)
class GitHubRepositoryData(GitHubRepositoryListEntry):
    """One repository, as stored in github_repositories (ADR-017)."""

    parent_full_name: str | None


@dataclass(frozen=True)
class RepositoryPage:
    items: tuple[GitHubRepositoryListEntry, ...]
    has_next: bool


@dataclass(frozen=True)
class ContributorPage:
    github_user_ids: tuple[int, ...]
    has_next: bool


def _header_int(headers: httpx.Headers, name: str) -> int | None:
    value = headers.get(name)
    if value is None or not value.isascii() or not value.isdigit():
        return None
    return int(value)


def parse_rate_limit(headers: httpx.Headers) -> RateLimit | None:
    remaining = _header_int(headers, "x-ratelimit-remaining")
    reset = _header_int(headers, "x-ratelimit-reset")
    if remaining is None and reset is None:
        return None
    reset_at = None
    if reset is not None:
        try:
            reset_at = datetime.fromtimestamp(reset, UTC).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            reset_at = None
    return RateLimit(
        limit=_header_int(headers, "x-ratelimit-limit"),
        remaining=remaining,
        reset_at=reset_at,
        used=_header_int(headers, "x-ratelimit-used"),
        resource=headers.get("x-ratelimit-resource"),
    )


def _is_secondary_limit(response: httpx.Response) -> bool:
    # Read only to classify the answer; the message is never logged or returned.
    try:
        message = response.json().get("message")
    except (ValueError, AttributeError):
        return False
    return isinstance(message, str) and "secondary rate limit" in message.lower()


def _limited_until(
    response: httpx.Response, rate: RateLimit | None, now: datetime
) -> datetime | None:
    """When a 403 or 429 is a rate limit, the time to wait until (ADR-018)."""
    if "retry-after" in response.headers:
        retry_after = _header_int(response.headers, "retry-after")
        if retry_after is None:
            # Negative, non-numeric or a date: still a limit, with GitHub's default wait.
            return now + SECONDARY_LIMIT_WAIT
        # Capped before the addition, so a huge value cannot overflow datetime.
        wait = min(retry_after, int(MAX_RATE_LIMIT_WAIT.total_seconds()))
        wait = max(wait, int(MIN_RATE_LIMIT_WAIT.total_seconds()))
        return now + timedelta(seconds=wait)
    if rate is not None and rate.remaining == 0:
        if rate.reset_at is not None and rate.reset_at > now:
            return min(max(rate.reset_at, now + MIN_RATE_LIMIT_WAIT), now + MAX_RATE_LIMIT_WAIT)
        return now + SECONDARY_LIMIT_WAIT
    if response.status_code == 429 or _is_secondary_limit(response):
        return now + SECONDARY_LIMIT_WAIT
    return None


def _moved_to(response: httpx.Response) -> int:
    match = _MOVED_TO.fullmatch(response.headers.get("location", ""))
    if match is None or int(match.group(1)) > MAX_BIGINT:
        raise GitHubUnexpected(response.status_code)
    return int(match.group(1))


# Body parsing: anything that does not have GitHub's documented shape is a
# malformed response, which ADR-018 treats like an unavailable GitHub.


def _malformed(status: int) -> GitHubUnavailable:
    return GitHubUnavailable("malformed_response", status)


def _body(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        raise _malformed(response.status_code) from None


def _positive_int(value: object, status: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_BIGINT:
        raise _malformed(status)
    return value


def _text(value: object, status: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _malformed(status)
    return value


def _flag(value: object, status: int) -> bool:
    if not isinstance(value, bool):
        raise _malformed(status)
    return value


def _timestamp(value: object, status: int) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _malformed(status)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise _malformed(status) from None
    if parsed.tzinfo is None:
        raise _malformed(status)
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _is_private(data: object) -> bool:
    # Public data only (ADR-016); app credentials should never see a private one.
    return isinstance(data, dict) and data.get("private") is True


def _list_entry(data: object, status: int) -> GitHubRepositoryListEntry:
    if not isinstance(data, dict) or not isinstance(data.get("owner"), dict):
        raise _malformed(status)
    owner_login = _text(data["owner"].get("login"), status)
    name = _text(data.get("name"), status)
    full_name = _text(data.get("full_name"), status)
    if full_name != f"{owner_login}/{name}":
        raise _malformed(status)
    html_url = data.get("html_url")
    if not isinstance(html_url, str) or not html_url.startswith(GITHUB_HTML_URL_PREFIX):
        html_url = f"{GITHUB_HTML_URL_PREFIX}{full_name}"
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise _malformed(status)
    return GitHubRepositoryListEntry(
        github_repo_id=_positive_int(data.get("id"), status),
        owner_github_id=_positive_int(data["owner"].get("id"), status),
        owner_login=owner_login,
        name=name,
        full_name=full_name,
        html_url=html_url,
        # PostgreSQL text cannot hold NUL.
        description=description.replace("\x00", "") if description else None,
        is_fork=_flag(data.get("fork"), status),
        is_archived=_flag(data.get("archived"), status),
        pushed_at=_timestamp(data.get("pushed_at"), status),
    )


def _repository(data: object, status: int) -> GitHubRepositoryData:
    if _is_private(data):
        raise GitHubNotFound()
    entry = _list_entry(data, status)
    parent_full_name = None
    parent = data.get("parent") if isinstance(data, dict) else None
    if entry.is_fork and isinstance(parent, dict):
        value = parent.get("full_name")
        parent_full_name = value if isinstance(value, str) and value.strip() else None
    return GitHubRepositoryData(**vars(entry), parent_full_name=parent_full_name)


def _check_repository_name(owner: str, name: str) -> None:
    if not is_valid_owner(owner) or not is_valid_name(name):
        raise InvalidGitHubInput("Invalid repository owner or name")


def _check_page(page: int, maximum: int) -> None:
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= maximum:
        raise InvalidGitHubInput("Invalid page")


class GitHubApiClient:
    """One instance per unit of work; rate_limits and pause are shared by the process.

    requests_sent counts requests that left this client (a timeout counts: GitHub
    may have served it), for the per-user budget (ADR-018).
    """

    def __init__(
        self,
        http_client: httpx.Client,
        client_id: str,
        client_secret: str,
        *,
        rate_limits: RateLimitState,
        pause: RateLimitPause,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = http_client
        token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")
        self._authorization = f"Basic {token}"
        self._rate_limits = rate_limits
        self._pause = pause
        self._now = now
        self.requests_sent = 0

    def __repr__(self) -> str:
        return f"GitHubApiClient(base_url={GITHUB_API!r})"

    def get_repository(self, owner: str, name: str) -> GitHubRepositoryData:
        _check_repository_name(owner, name)
        response = self._get("repository", f"/repos/{owner}/{name}")
        return _repository(_body(response), response.status_code)

    def get_repository_by_id(self, github_repo_id: int) -> GitHubRepositoryData:
        if (
            isinstance(github_repo_id, bool)
            or not isinstance(github_repo_id, int)
            or not 0 < github_repo_id <= MAX_BIGINT
        ):
            raise InvalidGitHubInput("Invalid repository id")
        response = self._get("repository_by_id", f"/repositories/{github_repo_id}")
        return _repository(_body(response), response.status_code)

    def list_user_repositories(self, login: str, page: int) -> RepositoryPage:
        """The user's own public repositories, most recently pushed first (ADR-017)."""
        if not is_valid_owner(login):
            raise InvalidGitHubInput("Invalid login")
        _check_page(page, MAX_LIST_PAGE)
        response = self._get(
            "user_repositories",
            f"/users/{login}/repos",
            params={
                "type": "owner",
                "sort": "pushed",
                "direction": "desc",
                "per_page": PER_PAGE,
                "page": page,
            },
        )
        data = _body(response)
        if not isinstance(data, list):
            raise _malformed(response.status_code)
        # One bad item must not hide the rest of the page: private items are not
        # shown (ADR-016), malformed ones are skipped and counted in the log.
        items = []
        skipped = 0
        for item in data:
            if _is_private(item):
                skipped += 1
                continue
            try:
                items.append(_list_entry(item, response.status_code))
            except GitHubUnavailable:
                skipped += 1
        if skipped:
            logger.warning("GitHub user_repositories: %s items skipped", skipped)
        has_next = "next" in response.links and page < MAX_LIST_PAGE
        return RepositoryPage(items=tuple(items), has_next=has_next)

    def get_languages(self, owner: str, name: str) -> dict[str, int]:
        """GitHub's own shape: {"language": bytes}, in GitHub's order."""
        _check_repository_name(owner, name)
        response = self._get("languages", f"/repos/{owner}/{name}/languages")
        data = _body(response)
        if not isinstance(data, dict):
            raise _malformed(response.status_code)
        languages: dict[str, int] = {}
        for language, size in data.items():
            if not language.strip() or isinstance(size, bool) or not isinstance(size, int):
                raise _malformed(response.status_code)
            if size < 0:
                raise _malformed(response.status_code)
            languages[language] = size
        return languages

    def get_contributor_page(self, owner: str, name: str, page: int) -> ContributorPage:
        """One page of contributor ids; anonymous contributors are not requested."""
        _check_repository_name(owner, name)
        _check_page(page, MAX_CONTRIBUTOR_PAGES)
        response = self._get(
            "contributors",
            f"/repos/{owner}/{name}/contributors",
            params={"per_page": PER_PAGE, "page": page},
        )
        # An empty repository has no contributors: 204 with no body.
        if response.status_code == 204:
            return ContributorPage(github_user_ids=(), has_next=False)
        data = _body(response)
        if not isinstance(data, list):
            raise _malformed(response.status_code)
        ids = []
        for item in data:
            if not isinstance(item, dict):
                raise _malformed(response.status_code)
            ids.append(_positive_int(item.get("id"), response.status_code))
        has_next = "next" in response.links and page < MAX_CONTRIBUTOR_PAGES
        return ContributorPage(github_user_ids=tuple(ids), has_next=has_next)

    def is_contributor(self, owner: str, name: str, github_user_id: int) -> bool:
        """Whether the user is in the first 5 contributor pages (ADR-017)."""
        for page in range(1, MAX_CONTRIBUTOR_PAGES + 1):
            result = self.get_contributor_page(owner, name, page)
            if github_user_id in result.github_user_ids:
                return True
            if not result.has_next:
                return False
        return False

    def _get(self, operation: str, path: str, params: dict | None = None) -> httpx.Response:
        self._pause.check(self._now())
        self.requests_sent += 1
        try:
            response = self._client.get(
                f"{GITHUB_API}{path}",
                params=params,
                headers={
                    "Authorization": self._authorization,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": _USER_AGENT,
                },
                timeout=_TIMEOUT,
                follow_redirects=False,
            )
        except httpx.TimeoutException:
            logger.warning("GitHub %s: timeout", operation)
            raise GitHubUnavailable("timeout") from None
        except httpx.RequestError as exc:
            logger.warning("GitHub %s: %s", operation, type(exc).__name__)
            raise GitHubUnavailable(type(exc).__name__) from None

        status = response.status_code
        rate = parse_rate_limit(response.headers)
        if rate is not None:
            self._rate_limits.update(rate)
        logger.info(
            "GitHub %s: status %s, remaining %s",
            operation,
            status,
            rate.remaining if rate is not None else None,
        )

        if status in (200, 204):
            return response
        if status == 404:
            raise GitHubNotFound()
        if status in (301, 302, 307, 308):
            raise GitHubMoved(_moved_to(response))
        if status in (403, 429):
            retry_at = _limited_until(response, rate, self._now())
            if retry_at is not None:
                self._pause.start(retry_at)
                raise GitHubRateLimited(retry_at)
        if status == 401:
            raise GitHubCredentialsRejected(status)
        if status >= 500:
            raise GitHubUnavailable(f"status_{status}", status)
        raise GitHubUnexpected(status)
