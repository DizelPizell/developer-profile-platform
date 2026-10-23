# ADR-010: No Arbitrary Repository Execution in V1

Status: **Superseded by ADR-006-project-workspace-not-sandbox.md** (2026-10-03)

> Note: this decision has been reformalized in `ADR-006-project-workspace-not-sandbox.md` (the current ADR-NNN numbering convention — see `docs/adr/README.md`). This document is retained for historical record and is not actively maintained.

Running arbitrary repositories creates major security and infrastructure complexity.

V1 provides read-only repository inspection. It does not execute user code or deploy arbitrary repositories.
