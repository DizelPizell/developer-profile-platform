# ADR-006: Read-only Project Workspace in V1

## Status

Accepted

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
