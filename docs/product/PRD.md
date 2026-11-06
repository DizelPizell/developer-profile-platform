# Product Requirements Document

## Product

**Developer Professional Profile Platform**

Core principle:

> Не рассказывай, что ты умеешь. Покажи.

The platform lets developers create structured professional profiles where real projects, live demos, GitHub evidence and personal contribution are more important than a static resume.

## Problem

A traditional resume mostly describes skills and experience. It is difficult for an employer to quickly verify what a developer actually built, what their role was, and how deeply they understand the project.

## Target users

- **Developer**: creates a professional profile and presents real work.
- **Recruiter / Employer**: quickly understands a candidate's experience and evidence.
- **Technical reviewer**: inspects code, architecture, tests and Git history. In V1 this means the project page and the GitHub data with its link to the repository; reading the code on the platform comes with the workspace, after V1.

## V1 value proposition

V1 is not a LinkedIn or HH replacement. It validates the hypothesis that a structured developer profile with real projects and evidence can communicate professional experience better than a static resume alone.

V1, as decided by the owner on 2026-11-04:

> Разработчик входит через GitHub, заполняет профиль с контактами, создаёт проекты с демо, скриншотами и привязанным репозиторием, публикует их; посетитель открывает страницу проекта, демо, данные GitHub и связывается с разработчиком. Всё работает в продакшене по HTTPS, с бэкапами и мониторингом.

Analytics follows as V1.1, right after the V1 launch. Candidate search, vacancies, matching and recruiter databases are V2.

## Profile

A public profile contains:
- photo
- name
- specialization
- short description
- up to 3 featured projects
- experience
- skills
- education
- GitHub
- contacts
- other projects

The developer controls which projects are featured and their order.

Contacts (ADR-020): one each of email, Telegram, LinkedIn and phone, and up to 3 other ways to reach the developer, each a name and a link. Telegram, LinkedIn and the others are on the public page; email and phone are shown to a visitor on a click.

Implemented so far (ADR-013): photo is the GitHub avatar, name is `display_name`, specialization is `headline`, short description is `bio` (plain text), plus `location`; GitHub is shown as `github_login`. A profile can be published only with a name and a headline. Projects and up to 3 featured projects come in Phase 3 (ADR-015); a profile can be published without projects. Contacts are part of V1 in a minimal form (DEVELOPMENT_PLAN, steps C.1–C.2). Experience, skills and education come after V1: projects matter more than a resume, and the question of skills in ADR-015 stays open until then.

## Project

A project can contain:
- name
- short/full description
- problem
- goals
- results
- role
- contribution
- technologies
- screenshots
- demo URL
- GitHub repository
- architecture
- highlights

A project does not require GitHub or a demo.

Phase 3 (ADR-015) defines `title` (name), `summary` (short description), `description` (full description), `problem`, `results`, `role`, `contribution` and technologies. Publishing a project requires the title, the short description, role, contribution and at least one technology. Goals, architecture, highlights, screenshots, the demo URL and the GitHub repository come in later phases.

A project is `DRAFT`, `PUBLISHED` or `ARCHIVED`. A published project is public or hidden. It is shown on the public profile only when it is published, public, and the profile itself is published.

## Evidence model

### GitHub is source of truth for technical evidence

Evidence scope (see ADR-010-github-evidence-data-model-v1.md). V1 reads only public repositories, with the platform's app credentials and no access granted by the user (ADR-016), and synchronizes only repository metadata and languages; README, file tree, contributors and commits are deferred until the public project page and a README display decision (ADR-018). GitHub data is shown on the cards of projects the developer linked to a repository they own or contributed to (ADR-017, ADR-019).

- repository (metadata)
- README
- languages
- file tree (metadata only — file content is not synced in V1)
- contributors (GitHub's own reported data, no derived scores)
- commits (up to 100 most recent per sync)

Not part of the required V1 scope: pull requests, releases, CI/CD as a separate entity, Docker configuration as a separate entity (represented, if at all, through file tree). Dependencies are deferred pending a separate review of GitHub API behavior, not rejected outright.

### Developer is source of truth for context

- role
- personal contribution
- business problem/context
- results
- screenshots
- demo URL

The UI should distinguish these sources.

Do not create artificial skill scores or contribution percentages.

## Demo-first project page

If a project has a live demo, the demo is the first major element. Then the visitor can read a concise explanation and inspect the technical details: the GitHub data in V1, the code with the workspace after V1.

If embedding is blocked by CSP/X-Frame-Options, show a preview and an external "Open live demo" action.

V1 does not execute arbitrary GitHub repositories.

## Interactive Project Workspace

After V1 (decided by the owner on 2026-11-04). The description stays for when it returns.

A read-only IDE/VS Code-like viewer:
- file explorer
- code viewer
- Overview
- Architecture
- Tests
- Git
- Documentation
- Analytics

It is not a full IDE.

## GitHub integration

GitHub OAuth connects an account.

The platform can:
- list repositories
- import repositories
- synchronize repository data
- expose normalized technical information

GitHub data is cached/normalized in PostgreSQL. Public pages should not call GitHub live on every request.

## Analytics

V1.1: released right after the V1 launch (DEVELOPMENT_PLAN, Phase 7). V1 sends no analytics events, `CONTACT_CLICK` included.

V1.1 events:
- profile views
- project views
- demo clicks
- GitHub clicks
- contact clicks

Deferred: CV downloads. V1 does not yet define a CV generation/storage feature, so this event is not part of the active V1 analytics contract until that feature is specified (see docs/architecture/ARCHITECTURAL_DIALOGUE.md section 21).

Funnel:

`Profile -> Project -> Demo/GitHub -> Contact`

Analytics must not block core actions.

## Authentication and privacy

Authentication:
- login via GitHub OAuth (registration and login unified; account created automatically on first login)
- logout
- current user

Cookies:
- HTTP-only
- Secure in production
- appropriate SameSite policy
- CSRF protection where applicable (V1: Origin check on state-changing requests, ADR-013)

Developer controls:
- profile visibility
- project visibility
- contact visibility (in V1: adding or removing a contact and hiding the profile; there is no switch per contact, ADR-020)
- selected GitHub repositories

## V1 scope

Included:
- authentication
- profile/public profile
- contacts, in a minimal form (US-025)
- projects
- public project page
- showcase
- max 3 featured projects
- demos/screenshots
- GitHub OAuth/import/sync
- privacy
- tests
- CI
- Docker
- documentation
- production-oriented security

Required for the V1 launch (DEVELOPMENT_PLAN, "V1 and the remaining work"):
- rate limiting (ADR-013)
- account deletion and a data policy
- a security review
- deployment over HTTPS
- backups
- monitoring

V1.1, right after the V1 launch:
- analytics: events, profile and project analytics, the funnel

After V1:
- the read-only project workspace
- experience, skills and education on the profile

Excluded:
- recruiter candidate search
- vacancies
- matching
- messaging
- AI candidate scoring
- microservices
- Kubernetes
- Kafka
- arbitrary code execution

## V2

Potential:
- recruiter accounts
- candidate search/filters
- saved candidates
- vacancies
- applications
- messaging
- matching/recommendations
- AI-assisted profile/project analysis

AI must not produce an unjustified overall candidate score.

## Success criteria

V1:

A developer can sign in with GitHub, create a profile with contacts, import or link a repository and enrich the project, add a demo and screenshots, configure a showcase and publish a profile.

A visitor can understand the developer, open a project page, open a demo, see the GitHub data and contact the developer.

All of it works in production over HTTPS, with backups and monitoring.

V1.1:

A developer receives useful analytics.

After V1:

A visitor inspects the code and the technical details of a project in the workspace.
