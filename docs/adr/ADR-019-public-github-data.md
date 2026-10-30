# ADR-019: Public GitHub Data

## Status

Accepted. The README display policy is not decided (see "Open questions").

Amends ADR-013-profile-editing-and-origin-check.md and ADR-015-project-model.md: public project cards gain a `github` object. Builds on ADR-017 and ADR-018.

## Context

`docs/frontend/DESIGN.md` reserves a «Данные GitHub» block on the public profile, pending Phases 5–6, without saying what it holds. DEVELOPMENT_PLAN says Phase 6 shows GitHub data for projects that have a linked repository.

ADR-007 and CLAUDE.md forbid scores and rankings and require GitHub data to stay distinguishable from what the developer wrote. Totals across a profile (stars, commits, activity graphs) turn facts into a ranking signal, and V1 stores only metadata and languages (ADR-018).

## Decision

### Where GitHub data is shown

- On every public project card (`featured` and `other` in `GET /public/profiles/{slug}`) as a nullable `github` object, and on the public project page when it exists (Phase 4).
- The profile-level «Данные GitHub» block is not built in V1. It stays a placeholder in DESIGN.md; nothing aggregates GitHub data across a profile.

### The `github` object (whitelist)

Exactly these fields, nothing else:

| Field | Source |
|---|---|
| `full_name` | GitHub |
| `html_url` | GitHub, only `https://github.com/...` (ADR-017) |
| `description` | GitHub, nullable |
| `languages` | GitHub: `[{"name": "...", "bytes": n}]`, by bytes descending; may be empty |
| `pushed_at` | GitHub, nullable |
| `is_fork` | GitHub |
| `parent_full_name` | GitHub, nullable; set for a fork |
| `is_archived` | GitHub |
| `relation` | `OWNER` or `CONTRIBUTOR` (ADR-017) |
| `synced_at` | The platform: when this data was last read from GitHub |

Never returned publicly: internal ids (`id`, `github_repo_id`, `owner_github_id`), ETags, job states and errors, `unavailable_since`, `relation_checked_at`, the file tree, README.

### When `github` is `null`

`github` is `null` when the project has no linked repository, when the repository has never been synced successfully (`synced_at` would be `null`), when the repository is unavailable (`unavailable_since` is set), or when the relation is `NONE`. The project card itself is unaffected: a project does not require GitHub.

### Presentation rules

- The block carries «Источник: GitHub»; the developer's text keeps «От автора» (DESIGN.md).
- The relation is stated as a fact: «Владелец репозитория» or «В списке контрибьюторов (по данным GitHub)». The word «подтверждено» is not used.
- A fork always shows «Форк {parent_full_name}». An archived repository shows that it is archived.
- Languages may be shown as shares of bytes, labelled as such («доля кода в байтах, по данным GitHub»). They are not skills and are not levels.
- Not shown, on a card or the profile: totals of stars, forks or commits, activity graphs, contribution counts, any sorting by popularity.
- `synced_at` is shown as the date of the data, so stale data is visible as stale.

### Query cost

The public profile reads GitHub data for all its projects in one additional batched query, so the number of queries does not depend on the number of projects (as in step 3.3).

## Consequences

### Positive

- Every GitHub fact on a public page is tied to a project the developer chose to show and a repository they are related to.
- The whitelist is small and testable.

### Negative

- The «Данные GitHub» mockup block on the profile stays unbuilt in V1.
- Stars are not shown even for a single repository; a developer whose project is popular cannot show that through the platform in V1.

## Alternatives considered

- **A profile-level GitHub block with totals**: rejected — totals act as a ranking (ADR-007) and need data V1 does not store.
- **Showing the GitHub block for a lost relation or an unavailable repository with a warning**: rejected — the first is a claim GitHub no longer supports, the second may disclose a repository its owner made private.

## Open questions

- **README display policy**: whether README is shown as plain text or as rendered markdown, how HTML in markdown is treated, and whether images from other hosts are loaded (a tracking concern for visitors). Decided before README returns (ADR-018).
- Whether stars of a single repository are shown later.
