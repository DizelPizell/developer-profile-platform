# ADR-008: No Microservices in V1

Status: **Superseded by ADR-001-modular-monolith.md** (2026-10-03)

> Note: this decision is consolidated into `ADR-001-modular-monolith.md`, which includes "reject microservices" as part of the modular-monolith decision (the current ADR-NNN numbering convention — see `docs/adr/README.md`). This document is retained for historical record and is not actively maintained.

Do not split V1 into microservices. A modular monolith provides the required separation with lower deployment and debugging complexity.

Consider services later only when a concrete scaling, ownership or deployment problem justifies them.
