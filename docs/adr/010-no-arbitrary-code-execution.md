# ADR-010: No Arbitrary Repository Execution in V1

Status: **Accepted**

Running arbitrary repositories creates major security and infrastructure complexity.

V1 provides read-only repository inspection. It does not execute user code or deploy arbitrary repositories.
