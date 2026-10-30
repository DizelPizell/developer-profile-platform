# ADR-003: Encrypted GitHub OAuth Token Storage

## Status

Accepted

Note (2026-10-30): not applied in V1. ADR-016-github-access-v1.md reads only public data with the app's credentials, so no user GitHub token is requested or stored. This ADR remains the rule if a GitHub token is ever stored (for example through a GitHub App).

## Context

The platform needs a GitHub OAuth token to perform authorized GitHub API operations on behalf of the user.

Plaintext storage would create an unnecessary high-impact secret exposure.

## Decision

Store the GitHub access token encrypted at application level.

The encryption key is provided through environment/secret-management infrastructure.

The token must never be:

- returned through API responses;
- logged;
- sent to the frontend;
- committed to Git.

## Consequences

The application needs encryption/decryption infrastructure and secure secret management.

The implementation must also consider future key rotation.
