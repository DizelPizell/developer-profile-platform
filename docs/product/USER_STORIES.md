# User Stories

## Authentication
- **US-001** Login with GitHub: authenticate via GitHub OAuth; an account and profile are created automatically on first login.
- **US-002** Logout: invalidate the session.
- **US-003** _(удалена — email-регистрация не поддерживается в V1, см. ADR-012)_

## Profile
- **US-004** Edit profile.
- **US-005** Publish profile.
- **US-006** Unpublish profile.
- **US-007** Select and order up to three featured projects.

## GitHub
- **US-008** Connect GitHub using OAuth. Not in V1: login is the only GitHub consent, and repository data is public (ADR-016).
- **US-009** View available repositories (own public repositories).
- **US-010** Import a repository as a project.
- **US-011** Synchronize repository data.

## Projects
- **US-012** Create project.
- **US-013** Edit project.
- **US-014** Add technologies.
- **US-015** Add screenshots.
- **US-016** Add demo.
- **US-017** Associate GitHub repository (as its owner or a contributor, ADR-017).
- **US-018** Publish project.

## Showcase
- **US-019** Configure project showcase.
- **US-020** Reorder featured projects.
- **US-021** Replace a featured project.

## Public profile
- **US-022** View public profile.
- **US-023** Inspect project.
- **US-024** Open demo/GitHub.
- **US-025** Contact developer.

## Analytics
- **US-026** Track profile views.
- **US-027** Track project views.
- **US-028** Track demo clicks.
- **US-029** Track GitHub/contact clicks.
- **US-030** View profile-to-contact funnel.
