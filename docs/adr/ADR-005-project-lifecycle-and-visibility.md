# ADR-005: Separate Project Lifecycle and Visibility

## Status

Accepted

## Context

Project publication state and public exposure answer different questions.

## Decision

Project lifecycle:

```text
DRAFT
PUBLISHED
ARCHIVED
```

Project visibility:

```text
PUBLIC
PRIVATE
```

The domain layer must reject invalid combinations.

Profile lifecycle is simpler:

```text
PRIVATE
PUBLISHED
```

Unpublishing a profile returns it to PRIVATE.

## Consequences

The model distinguishes preparation/publication state from exposure policy.

The exact allowed state combinations must be encoded in domain validation and tests.

## Amendment (ADR-015)

ADR-015-project-model.md fixes what this ADR left open:

- Allowed combinations: `DRAFT`+`PRIVATE`, `PUBLISHED`+`PUBLIC`, `PUBLISHED`+`PRIVATE`, `ARCHIVED`+`PRIVATE`. A new project is `DRAFT`+`PRIVATE`. The database repeats the rule with a CHECK.
- Transitions: publish (`DRAFT` or `ARCHIVED` → `PUBLISHED`+`PUBLIC`, with a completeness check), archive (`PUBLISHED` → `ARCHIVED`+`PRIVATE`), and a visibility change only while `PUBLISHED`. Forbidden transitions give 409 `PROJECT_TRANSITION_INVALID`.
- A project is public only when it is `PUBLISHED`+`PUBLIC` and its owner's profile is `PUBLISHED`.

The decision above (two separate concepts, the profile lifecycle) is unchanged.
