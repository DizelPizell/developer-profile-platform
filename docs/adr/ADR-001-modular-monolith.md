# ADR-001: Modular Monolith

## Status

Accepted

## Context

V1 contains several logical domains but does not require independent deployment or scaling of each domain.

## Decision

Use a modular monolith.

Logical contexts:

- Identity
- Profile
- Projects
- GitHub
- Analytics
- Files

## Consequences

### Positive

- simpler local development;
- simpler deployment;
- easier transactions;
- easier debugging;
- domain boundaries remain explicit;
- lower operational complexity than microservices.

### Negative

- modules share a deployment unit;
- boundaries must be protected by code conventions and review;
- future extraction into services would require additional work.

## Rejected

Microservices for V1.

Reason: no concrete requirement justifies their operational complexity.
