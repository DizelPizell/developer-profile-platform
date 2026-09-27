# Domain Model and Use Cases

## Bounded contexts

### Identity
Registration, login, logout, sessions, current user.

### Profile
Professional profile, slug, publication state, experience, education, skills, featured projects.

### Projects
Project lifecycle, context, technologies, screenshots, demo, repository association, showcase.

### GitHub
OAuth connection, repository listing, import, synchronization, normalized technical data.

### Analytics
Event collection, profile metrics, project metrics and funnel metrics.

### Files
Object storage, uploads and access policy.

## Main workflow

```text
Registration -> Profile -> Connect GitHub -> Repository list
-> Import repository -> Create/enrich project -> Showcase
-> Featured project -> Publish profile
```

## Use cases

Identity:
- RegisterUser
- LoginUser
- LogoutUser
- GetCurrentUser

Profile:
- GetOwnProfile
- UpdateProfile
- PublishProfile
- UnpublishProfile
- ReorderFeaturedProjects
- GetPublicProfile

Projects:
- CreateProject
- UpdateProject
- DeleteProject
- PublishProject
- ArchiveProject
- ConfigureProjectShowcase

GitHub:
- ConnectGitHub
- DisconnectGitHub
- ListRepositories
- ImportRepository
- SynchronizeRepository

Analytics:
- TrackEvent
- GetProfileAnalytics
- GetProjectAnalytics

## GitHub sync

```text
NOT_SYNCED -> SYNCING -> SYNCED
                     \-> FAILED
```

Persist:
- sync_status
- last_synced_at
- sync_error

External GitHub identifiers are unique.

## Project import

Importing a repository creates an Imported Project. The developer enriches it with role, contribution, description and other context.

## Publish validation

Minimum:
- name
- description
- role
- contribution
- at least one technology

Demo, GitHub and screenshots are optional.
