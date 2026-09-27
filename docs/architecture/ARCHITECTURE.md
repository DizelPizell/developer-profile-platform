# Architecture

## Style

V1 uses a **modular monolith**. We have multiple domain areas but not enough operational complexity to justify microservices.

Principle: establish domain boundaries first; add infrastructure only when a concrete problem requires it.

## Stack

### Frontend
Next.js, TypeScript, Tailwind CSS, shadcn/ui, Vitest, React Testing Library, Playwright.

### Backend
Python, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, pytest.

### Infrastructure
Docker, Docker Compose, Nginx, GitHub Actions, S3-compatible object storage, MinIO locally.

### External
GitHub API.

Redis, Kafka and Kubernetes are not V1 requirements.

## Deployment

```text
Internet
   |
Nginx / Reverse Proxy
   |
   +--------------------+
   |                    |
Next.js              FastAPI
                         |
              +----------+----------+
              |          |          |
         PostgreSQL   Object     GitHub API
                      Storage
```

A background worker may be added for GitHub synchronization.

## Backend flow

```text
HTTP -> API/Controller -> Application/Use Case -> Domain -> Repository -> Infrastructure
```

Do not create abstractions without a reason.

## Bounded contexts

- Identity
- Profile
- Projects
- GitHub
- Analytics
- Files

## Aggregate roots

- User
- Profile
- Project
- Analytics

## Domain rules

- Registration creates User + Profile in one transaction.
- Profile slug is unique.
- Profile lifecycle: PRIVATE -> PUBLISHED -> UNPUBLISHED.
- Project lifecycle: DRAFT -> READY -> PUBLISHED -> ARCHIVED.
- Project may exist without GitHub or Demo.
- Maximum 3 featured projects.
- GitHub OAuth tokens are never stored plaintext.
- Repository import is not the same thing as a fully enriched Project.
- GitHub synchronization is idempotent.
- Analytics failures must not break core navigation.

## Public API

Never serialize domain entities directly. Use explicit DTOs.

Never expose:
- password hashes
- OAuth tokens
- secrets
- private settings
- private projects

## Security

Security is part of architecture:
- authentication
- authorization/ownership checks
- input validation
- secret management
- safe logging
- CSRF protection where applicable

## No arbitrary code execution

V1 only provides read-only repository inspection.
