// The slug format of the database CHECK ck_profiles_slug_format (3–39
// characters, ADR-012). Anything else is a 404 without asking the API, which
// would answer 404 anyway (ADR-013).
export const SLUG_PATTERN = /^[a-z0-9][a-z0-9-]{1,37}[a-z0-9]$/;

// A canonical UUID in lowercase, as the API's parse_canonical_uuid takes it (step 4.3).
export const PROJECT_ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The title of pages without their own: 404s, errors, malformed addresses. */
export const SITE = "Developer Profile Platform";
