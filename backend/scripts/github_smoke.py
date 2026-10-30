"""Manual smoke check of GitHub's REST API with the app's credentials (step 5.2).

Checks what ADR-016, ADR-017 and ADR-018 list as not verified, without a user
token:

- the credentials are accepted (core limit 5,000, not the unauthenticated 60);
- GET /repositories/{id} reads a public repository by numeric id;
- a renamed repository answers 301 and where Location points;
- GET /users/{login}/repos?type=owner returns only public repositories;
- README and the recursive file tree are readable;
- a 304 to a conditional request does not spend x-ratelimit-remaining;
- public repositories of an organization are readable;
- an empty repository's contributors answer 204 (when one is given).

Only GET requests to https://api.github.com, one at a time, redirects not
followed. The credentials come from GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
in the environment; this script does not read .env. It prints statuses,
rate-limit headers, Location and a short conclusion: never response bodies or
credentials. About 15 requests from the platform's shared hourly budget.

Run from the repository root, with the backend image (compose passes .env to
the container's environment). The script imports app.github.client, so build
the image from the current code first: docker compose build backend.
Linux and macOS:

    docker compose run --rm --no-deps -v "$PWD/backend/scripts:/app/scripts:ro" \
        backend python -m scripts.github_smoke

Git Bash on Windows (without MSYS_NO_PATHCONV the mount path is rewritten):

    MSYS_NO_PATHCONV=1 docker compose run --rm --no-deps \
        -v "$(pwd -W)/backend/scripts:/app/scripts:ro" backend python -m scripts.github_smoke

PowerShell:

    docker compose run --rm --no-deps -v "${PWD}/backend/scripts:/app/scripts:ro" `
        backend python -m scripts.github_smoke

or from backend/, with the variables already exported in the shell:

    python -m scripts.github_smoke --org github --empty-repo owner/name
"""

import argparse
import base64
import os
import re
import sys
from dataclasses import dataclass

import httpx

# The client's own filters; importing it needs no database or settings.
from app.github.client import GITHUB_API, is_valid_name, is_valid_owner

_RATE_HEADERS = ("limit", "remaining", "used", "resource")


@dataclass
class Row:
    label: str
    status: str
    rate: str
    location: str
    conclusion: str


def _full_name(value: str) -> tuple[str, str]:
    owner, _, name = value.partition("/")
    if not is_valid_owner(owner) or not is_valid_name(name):
        raise argparse.ArgumentTypeError("expected owner/name")
    return owner, name


def _owner(value: str) -> str:
    if not is_valid_owner(value):
        raise argparse.ArgumentTypeError("expected a GitHub login")
    return value


class Smoke:
    def __init__(self, client: httpx.Client, authorization: str) -> None:
        self._client = client
        self._authorization = authorization
        self.rows: list[Row] = []

    def get(
        self, label: str, path: str, params: dict | None = None, etag: str | None = None
    ) -> httpx.Response | None:
        headers = {
            "Authorization": self._authorization,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "developer-profile-platform-smoke",
        }
        if etag:
            headers["If-None-Match"] = etag
        try:
            response = self._client.get(
                f"{GITHUB_API}{path}",
                params=params,
                headers=headers,
                timeout=httpx.Timeout(10.0),
                follow_redirects=False,
            )
        except httpx.HTTPError as exc:
            self.rows.append(Row(label, type(exc).__name__, "-", "-", "request failed"))
            return None
        rate = " ".join(
            f"{key}={response.headers.get(f'x-ratelimit-{key}', '-')}" for key in _RATE_HEADERS
        )
        location = response.headers.get("location", "-")
        self.rows.append(Row(label, str(response.status_code), rate, location, ""))
        return response

    def conclude(self, text: str) -> None:
        self.rows[-1].conclusion = text


def _json(response: httpx.Response | None) -> object:
    if response is None or response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _used(response: httpx.Response | None) -> int | None:
    value = response.headers.get("x-ratelimit-used") if response is not None else None
    return int(value) if value is not None and value.isdigit() else None


def run(smoke: Smoke, args: argparse.Namespace) -> None:
    owner, name = args.repo

    limits = _json(smoke.get("rate_limit", "/rate_limit"))
    resources = limits.get("resources") if isinstance(limits, dict) else None
    core = resources.get("core") if isinstance(resources, dict) else None
    core = core if isinstance(core, dict) else {}
    smoke.conclude(
        f"core limit {core.get('limit')}: "
        + ("app credentials accepted" if core.get("limit") == 5000 else "NOT the app limit")
    )

    first = smoke.get("repository by name", f"/repos/{owner}/{name}")
    repo = _json(first)
    repo_id = repo.get("id") if isinstance(repo, dict) else None
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    smoke.conclude(
        f"id {repo_id}, private={repo.get('private') if isinstance(repo, dict) else '?'}"
    )

    # The conditional request comes right after `first`, with nothing in between,
    # so x-ratelimit-used of the three answers can be compared directly.
    etag = first.headers.get("etag") if first is not None else None
    if etag:
        conditional = smoke.get("same, If-None-Match", f"/repos/{owner}/{name}", etag=etag)
        after = smoke.get("same, unconditional", f"/repos/{owner}/{name}")
        used = (_used(first), _used(conditional), _used(after))
        if None in used or conditional is None or conditional.status_code != 304:
            verdict = "no 304; cannot tell"
        elif used[1] == used[0] and used[2] == used[0] + 1:
            verdict = "304 is free"
        elif used[1] == used[0] + 1 and used[2] == used[0] + 2:
            verdict = "304 spends the limit"
        else:
            verdict = "other traffic on the shared budget; run again"
        smoke.rows[-2].conclusion = f"used {used[0]} -> {used[1]} -> {used[2]}: {verdict}"
    else:
        smoke.conclude("no ETag; conditional check skipped")

    if isinstance(repo_id, int):
        by_id = _json(smoke.get("repository by id", f"/repositories/{repo_id}"))
        same = isinstance(by_id, dict) and by_id.get("id") == repo_id
        smoke.conclude("reads by numeric id" if same else "does NOT read by id")

    readme = smoke.get("README", f"/repos/{owner}/{name}/readme")
    smoke.conclude(
        "readable" if readme is not None and readme.status_code == 200 else "not readable"
    )

    if is_valid_name(branch):
        tree = _json(
            smoke.get(
                "tree, recursive",
                f"/repos/{owner}/{name}/git/trees/{branch}",
                params={"recursive": "1"},
            )
        )
        if isinstance(tree, dict):
            smoke.conclude(f"readable, truncated={tree.get('truncated')}")
        else:
            smoke.conclude("not readable")

    contributors = smoke.get(
        "contributors", f"/repos/{owner}/{name}/contributors", params={"per_page": 1}
    )
    if contributors is not None:
        smoke.conclude("has next page" if "next" in contributors.links else "single page")

    old_owner, old_name = args.renamed
    smoke.get("renamed repository", f"/repos/{old_owner}/{old_name}")
    moved = smoke.rows[-1]
    if moved.status in {"301", "302", "307", "308"}:
        target = re.fullmatch(r"https://api\.github\.com/repositories/([0-9]+)", moved.location)
        smoke.conclude(
            f"redirect to repository id {target.group(1)}"
            if target
            else "redirect, Location is NOT /repositories/{id}"
        )
    else:
        smoke.conclude("no redirect; pick another renamed repository with --renamed")

    listing = _json(
        smoke.get(
            "user repositories, type=owner",
            f"/users/{args.user}/repos",
            params={"type": "owner", "per_page": 100},
        )
    )
    if isinstance(listing, list):
        private = sum(1 for item in listing if isinstance(item, dict) and item.get("private"))
        smoke.conclude(f"{len(listing)} items, {private} private")

    org = _json(
        smoke.get(
            "organization repositories",
            f"/orgs/{args.org}/repos",
            params={"type": "public", "per_page": 5},
        )
    )
    if isinstance(org, list):
        smoke.conclude(f"{len(org)} public repositories readable")
    else:
        smoke.conclude("not readable")

    if args.empty_repo:
        empty_owner, empty_name = args.empty_repo
        smoke.get("empty repository", f"/repos/{empty_owner}/{empty_name}")
        smoke.get(
            "empty repository contributors", f"/repos/{empty_owner}/{empty_name}/contributors"
        )
        status = smoke.rows[-1].status
        smoke.conclude("204 as documented" if status == "204" else f"{status}, not 204")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=_full_name, default=("octocat", "Hello-World"))
    parser.add_argument(
        "--renamed",
        type=_full_name,
        default=("twitter", "bootstrap"),
        help="an old name of a renamed repository (twitter/bootstrap is now twbs/bootstrap)",
    )
    parser.add_argument("--user", type=_owner, default="octocat")
    parser.add_argument(
        "--org",
        type=_owner,
        default="github",
        help="an organization; pass one known to restrict OAuth app access to check that case",
    )
    parser.add_argument("--empty-repo", type=_full_name, help="a public repository with no commits")
    args = parser.parse_args()

    client_id = os.environ.get("GITHUB_CLIENT_ID", "")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        print("GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be set in the environment.")
        return 2
    token = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode("ascii")

    with httpx.Client() as client:
        smoke = Smoke(client, f"Basic {token}")
        try:
            run(smoke, args)
        except Exception as exc:
            # Print what was collected; the exception's type only, never its text.
            smoke.rows.append(Row("script stopped", type(exc).__name__, "-", "-", ""))

    widths = [max(len(getattr(r, f)) for r in smoke.rows) for f in ("label", "status", "rate")]
    for row in smoke.rows:
        print(
            f"{row.label:<{widths[0]}}  {row.status:<{widths[1]}}  {row.rate:<{widths[2]}}"
            f"  location={row.location}  {row.conclusion}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
