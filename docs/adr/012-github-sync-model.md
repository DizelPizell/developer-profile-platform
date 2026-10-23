# ADR-012: Normalize GitHub Data Locally

Status: **Accepted**

## Context
Public technical pages should not depend on GitHub API latency/rate limits for every request.

## Decision
Synchronize relevant GitHub data into PostgreSQL with explicit sync state and timestamps.

Synchronization must be idempotent.

## Tradeoff
Pages become predictable and less dependent on GitHub, but data may be temporarily stale.

## Note (2026-10-03)

The transport mechanism for synchronization was reconsidered: Kafka and the Outbox pattern were adopted (`ADR-002-kafka-and-outbox.md`, now superseded) and then rejected for V1 (`ADR-008-no-kafka-outbox-v1.md`). This ADR's core decision — normalize GitHub data into PostgreSQL with idempotent, explicit sync state — remains active. The detailed sync lifecycle (`NOT_SYNCED -> QUEUED -> SYNCING -> SYNCED/FAILED`) is documented in `docs/architecture/ARCHITECTURAL_DIALOGUE.md` section 9 and `docs/architecture/DOMAIN_MODEL.md`.
