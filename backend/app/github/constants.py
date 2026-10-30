"""GitHub constants and input filters shared by the API client, the smoke script
and the github_repositories CHECK.

Imports nothing from the application, so the client does not depend on the
database layer and the script needs no settings.
"""

import re

GITHUB_API = "https://api.github.com"
GITHUB_HTML_URL_PREFIX = "https://github.com/"

PER_PAGE = 100
MAX_LIST_PAGE = 100
# The relation check reads at most 5 contributor pages (ADR-017).
MAX_CONTRIBUTOR_PAGES = 5
# GitHub ids are stored as BIGINT.
MAX_BIGINT = 2**63 - 1

# Safety filters from ADR-016; GitHub stays the authority on existence.
OWNER_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
NAME_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,100}")


def is_valid_owner(value: object) -> bool:
    return isinstance(value, str) and OWNER_PATTERN.fullmatch(value) is not None


def is_valid_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and NAME_PATTERN.fullmatch(value) is not None
        and value not in {".", ".."}
    )
