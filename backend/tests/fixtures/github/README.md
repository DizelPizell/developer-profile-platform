# GitHub API fixtures

Собрано вручную по документации GitHub REST API (docs.github.com: repositories,
repository languages, repository contributors, user repositories), не снято с API.

Only the fields the client reads are kept; everything else GitHub returns is
dropped by the client anyway. The values follow the documentation's examples
(`octocat/Hello-World`, id 1296269, owner id 583231); the fork, archived and empty
repositories are made-up variations of it.

- `repository.json` — `GET /repos/{owner}/{repo}` and `GET /repositories/{id}`
- `repository_fork.json` — a fork, with `parent`
- `repository_archived.json` — `archived: true`
- `repository_empty.json` — no commits: `pushed_at` is null, no description
- `user_repositories.json` — `GET /users/{username}/repos`
- `languages.json` — `GET /repos/{owner}/{repo}/languages`
- `contributors.json` — `GET /repos/{owner}/{repo}/contributors`

An empty repository answers the contributors request with `204 No Content` and no
body; the tests build that response directly, so there is no file for it.

When the manual smoke check (`scripts/github_smoke.py`) shows a difference from
these shapes, the fixtures follow GitHub.
