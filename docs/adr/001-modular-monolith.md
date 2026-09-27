# ADR-001: Modular Monolith

Status: **Accepted**

## Context
V1 has multiple domains but not enough operational scale to justify microservices.

## Decision
Use a modular monolith.

## Consequences
Simpler deployment, local development and debugging, while domain boundaries can still be enforced.

The tradeoff is that future service extraction may require additional work.
