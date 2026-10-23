# ADR-009: Analytics as a First-Class Domain

Status: **Accepted**

Analytics is its own domain.

Core events:
- PROFILE_VIEW
- PROJECT_VIEW
- DEMO_CLICK
- GITHUB_CLICK
- CONTACT_CLICK
- CV_DOWNLOAD (deferred, see note below)

Analytics failures must not break core navigation or publishing.

## Note (2026-10-03)

`CV_DOWNLOAD` is deferred. V1 does not yet define a CV generation/storage feature, so this event is not part of the active V1 analytics contract until that feature is specified. See `docs/architecture/ARCHITECTURAL_DIALOGUE.md` sections 21-22. The rest of this ADR (analytics as its own domain, the other core events, non-blocking failure behavior) remains active.
