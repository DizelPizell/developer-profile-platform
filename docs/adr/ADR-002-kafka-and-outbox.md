# ADR-002: Kafka and Outbox for Asynchronous GitHub Synchronization

## Status

Superseded by ADR-008-no-kafka-outbox-v1.md (2026-10-03)

> **Note:** Kafka and the Outbox pattern described in this ADR were reconsidered and rejected for V1. See `ADR-008-no-kafka-outbox-v1.md` for the current decision and the reasoning for the reversal. This document is retained as the historical record of the original adoption.

## Context

GitHub synchronization can take longer than a normal HTTP request and should run asynchronously.

A simple HTTP request followed by direct Kafka publication creates a dual-write problem between PostgreSQL and Kafka.

## Decision

Use:

- PostgreSQL for durable job and application state;
- Outbox table for durable event publication;
- Kafka as asynchronous event transport;
- GitHub Sync Worker as consumer.

Flow:

```text
PostgreSQL transaction
    ├── sync job
    └── outbox event
            ↓
       Outbox Relay
            ↓
          Kafka
            ↓
      GitHub Worker
```

## Event

```text
github.sync.requested.v1
```

## Consequences

### Positive

- reliable event publication;
- asynchronous processing;
- retryable worker;
- clear event-driven boundary;
- useful production architecture learning.

### Negative

- Kafka adds operational complexity;
- outbox relay is another component;
- duplicate delivery must be handled;
- monitoring becomes more important.

## Scope limitation

Kafka is not used for every CRUD operation.

Analytics remains synchronous in V1.

## Rejected

Using Kafka as the database or replacing REST CRUD with events.

## Future

Additional event-driven workflows may be introduced only when a concrete problem justifies them.
