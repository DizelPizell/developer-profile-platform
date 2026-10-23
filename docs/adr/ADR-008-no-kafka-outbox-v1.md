# ADR-008: No Kafka or Outbox in V1

## Status

Accepted

## Context

ADR-002 adopted Kafka and the Outbox pattern to make GitHub synchronization asynchronous and to avoid a dual-write failure between PostgreSQL and Kafka.

On reconsideration, the operational complexity Kafka and an Outbox relay add — a broker, consumer groups, an additional relay component, additional failure modes, additional monitoring surface — is disproportionate to the current V1 requirement. CLAUDE.md's own guidance is that Redis, Kafka and Kubernetes are not part of V1 unless a concrete requirement appears. The requirement used to justify Kafka in ADR-002 (reliable asynchronous delivery) can be met directly against PostgreSQL, which is already the system's durable source of truth.

## Decision

V1 does not use Kafka.

V1 does not use the Outbox pattern.

GitHub synchronization remains asynchronous, but V1 implements it without a message broker or an outbox relay.

The exact worker/queue mechanism (for example: a database-backed job table polled by a worker process, `LISTEN/NOTIFY`, or another approach) is not decided by this ADR and is an open implementation decision — see Open Decisions in `docs/adr/README.md`.

The following lifecycle is accepted regardless of transport mechanism:

```text
NOT_SYNCED -> QUEUED -> SYNCING -> SYNCED / FAILED -> QUEUED (retry)
```

Synchronization must remain idempotent.

## Consequences

### Positive

- Removes an entire infrastructure component (Kafka) and its operational burden from V1.
- Removes the Outbox relay component and its failure modes.
- Keeps V1 deployable with only PostgreSQL and application processes, consistent with the modular monolith.
- Reduces the number of moving parts a single developer needs to operate, monitor and debug.

### Negative

- The durability/retry guarantees Kafka+Outbox would have provided must instead be implemented directly against PostgreSQL (for example, a job table with status, retry count and timestamps).
- If GitHub sync volume or fan-out grows significantly, this decision may need to be revisited.

## Rejected alternatives

- **Kafka + Outbox (ADR-002):** rejected for V1 as disproportionate to the current scale and requirements.
- **Synchronous GitHub sync inside the HTTP request:** rejected — sync can exceed a reasonable request time and must not block the API (established in ADR-002 and `docs/architecture/ARCHITECTURAL_DIALOGUE.md` section 9).

## Conditions under which Kafka may be introduced later

Kafka, or another message broker, may be reconsidered if a concrete, observed requirement appears. No specific future scenario is assumed or prescribed by this ADR. Reintroducing Kafka requires a new ADR with a concrete justification, not a silent reversal of this decision.

## Supersedes

`ADR-002-kafka-and-outbox.md` (status changed to Superseded by this ADR; content retained for historical record).
