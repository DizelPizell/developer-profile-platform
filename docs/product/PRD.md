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
- **Technical reviewer**: inspects code, architecture, tests and Git history.

## V1 value proposition

V1 is not a LinkedIn or HH replacement. It validates the hypothesis that a structured developer profile with real projects and evidence can communicate professional experience better than a static resume alone.

Candidate search, vacancies, matching and recruiter databases are V2.

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

## Evidence model

### GitHub is source of truth for technical evidence

- repository
- README
- languages
- file tree
- commits
- pull requests
- releases
- contributors
- dependencies/configuration
- Docker configuration
- tests where verifiable

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

If a project has a live demo, the demo is the first major element. Then the visitor can read a concise explanation and inspect code/technical details.

If embedding is blocked by CSP/X-Frame-Options, show a preview and an external "Open live demo" action.

V1 does not execute arbitrary GitHub repositories.

## Interactive Project Workspace

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

V1 events:
- profile views
- project views
- demo clicks
- GitHub clicks
- contact clicks
- CV downloads

Funnel:

`Profile -> Project -> Demo/GitHub -> Contact`

Analytics must not block core actions.

## Authentication and privacy

Authentication:
- registration
- login
- logout
- current user
- recovery
- GitHub OAuth as a separate integration

Cookies:
- HTTP-only
- Secure in production
- appropriate SameSite policy
- CSRF protection where applicable

Developer controls:
- profile visibility
- project visibility
- contact visibility
- selected GitHub repositories

## V1 scope

Included:
- authentication
- profile/public profile
- projects
- showcase
- max 3 featured projects
- demos/screenshots
- GitHub OAuth/import/sync
- technical workspace
- analytics
- privacy
- tests
- CI
- Docker
- documentation
- production-oriented security

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

A developer can register, create a profile, connect GitHub, import/enrich a repository, configure a showcase, publish a profile and receive useful analytics.

A visitor can understand the developer, inspect projects, open a demo, inspect technical evidence and contact the developer.
