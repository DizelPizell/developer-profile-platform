# ADR-006: Read-only Project Workspace in V1

## Status

Accepted

Note (2026-11-04): the owner moved the workspace out of V1: it comes after V1 (PRD, "V1 scope"; DEVELOPMENT_PLAN, "V1 and the remaining work"). The decision below stands for when it returns: read-only, and no repository code is executed. Where the text says "V1", read the first version of the workspace.

## Context

The product should make technical project evidence easy to inspect.

Executing arbitrary repositories inside the platform introduces substantial security and infrastructure requirements.

## Decision

V1 Project Workspace is read-only.

It can display:

- file tree;
- source code;
- README;
- architecture;
- tests;
- Git history;
- documentation;
- technical analytics.

The platform does not execute arbitrary project code.

## Consequences

V1 is significantly safer and simpler.

The product still provides a technical inspection experience.

## Future

A managed sandbox may be considered separately.

Such a system would require isolated execution, resource limits, network controls, lifecycle management and security review.
