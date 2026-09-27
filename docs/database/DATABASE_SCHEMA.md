# Database Schema V1

## Entities

```text
USER
PROFILE
EXPERIENCE
EDUCATION
SKILL
PROJECT
PROJECT_SHOWCASE
TECHNOLOGY
PROJECT_TECHNOLOGY
PROJECT_SCREENSHOT
PROJECT_REPOSITORY
PROJECT_DEMO
PROJECT_CONTRIBUTION
GITHUB_ACCOUNT
GITHUB_REPOSITORY
ANALYTICS_EVENT
```

## Relationships

```text
USER 1:1 PROFILE
USER 1:N EXPERIENCE
USER 1:N EDUCATION
USER 1:N SKILL
USER 1:N GITHUB_ACCOUNT

PROFILE 1:N PROJECT_SHOWCASE
PROJECT 1:0/1 PROJECT_SHOWCASE

PROJECT 1:N PROJECT_TECHNOLOGY
TECHNOLOGY 1:N PROJECT_TECHNOLOGY
PROJECT 1:N PROJECT_SCREENSHOT
PROJECT 1:N PROJECT_CONTRIBUTION
PROJECT 0/1 PROJECT_DEMO
PROJECT 0/1 PROJECT_REPOSITORY

GITHUB_ACCOUNT 1:N GITHUB_REPOSITORY
GITHUB_REPOSITORY 0/1 PROJECT_REPOSITORY

PROFILE/PROJECT 1:N ANALYTICS_EVENT
```

## Constraints

- user.email unique
- profile.user_id unique
- profile.slug unique
- project belongs to an owner
- featured project count <= 3
- GitHub user/repository external IDs unique
- GitHub token encrypted at rest
- timestamps on mutable entities

## Analytics

Events should include:
- event type
- profile/project reference when applicable
- timestamp
- privacy-safe session/context metadata

## Indexing priorities

Consider indexes for:
- profile.slug
- project.owner_id
- project.status
- showcase profile + order
- GitHub external IDs
- analytics profile/project + timestamp

Exact SQLAlchemy models and indexes must be reviewed before migrations.
