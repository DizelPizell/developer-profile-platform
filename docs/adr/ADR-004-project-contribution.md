# ADR-004: Project Contribution as Project Fields in V1

## Status

Accepted

## Context

The initial conceptual model contained a separate `PROJECT_CONTRIBUTION` entity.

V1 only needs to describe the current developer's role and contribution to a project.

## Decision

Store:

```text
projects.role
projects.contribution
```

directly on the Project entity.

## Consequences

The V1 data model remains smaller and easier to understand.

A future multi-contributor model can introduce a separate contributor relationship if the product requires it.

## Rejected

A separate contribution entity in V1.

Reason: it models future collaboration functionality before the product requires it.
