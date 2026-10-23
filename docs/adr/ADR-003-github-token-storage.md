# ADR-003: Encrypted GitHub OAuth Token Storage

## Status

Accepted

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
