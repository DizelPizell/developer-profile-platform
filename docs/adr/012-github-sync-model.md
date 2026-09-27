# ADR-012: Normalize GitHub Data Locally

Status: **Accepted**

## Context
Public technical pages should not depend on GitHub API latency/rate limits for every request.

## Decision
Synchronize relevant GitHub data into PostgreSQL with explicit sync state and timestamps.

Synchronization must be idempotent.

## Tradeoff
Pages become predictable and less dependent on GitHub, but data may be temporarily stale.
