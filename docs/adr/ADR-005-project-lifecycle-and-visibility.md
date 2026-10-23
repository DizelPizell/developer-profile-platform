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
