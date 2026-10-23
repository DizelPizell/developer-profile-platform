# ADR-001: Modular Monolith

Status: **Superseded by ADR-001-modular-monolith.md** (2026-10-03)

> Note: this decision has been reformalized with expanded context and consequences in `ADR-001-modular-monolith.md` (the current ADR-NNN numbering convention — see `docs/adr/README.md`). This document is retained for historical record and is not actively maintained.

## Context
V1 has multiple domains but not enough operational scale to justify microservices.

## Decision
Use a modular monolith.

## Consequences
Simpler deployment, local development and debugging, while domain boundaries can still be enforced.

The tradeoff is that future service extraction may require additional work.
