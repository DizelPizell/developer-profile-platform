import { apiFetch } from "./client";
import { ApiError } from "./errors";

/** PublicProfileResponse from API_CONTRACT.md: the whitelisted public fields. */
export type PublicProfile = {
  slug: string;
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
};

export const PUBLIC_PROFILE_TIMEOUT_MS = 5000;

const NULLABLE_FIELDS = ["display_name", "headline", "bio", "location", "avatar_url"] as const;

/** Copies only the known fields; anything else in the body is dropped. */
function toPublicProfile(body: unknown): PublicProfile | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const record = body as Record<string, unknown>;
  if (typeof record.slug !== "string" || typeof record.github_login !== "string") {
    return null;
  }
  const profile: PublicProfile = {
    slug: record.slug,
    github_login: record.github_login,
    display_name: null,
    headline: null,
    bio: null,
    location: null,
    avatar_url: null,
  };
  for (const field of NULLABLE_FIELDS) {
    const value = record[field];
    if (value !== null && typeof value !== "string") {
      return null;
    }
    profile[field] = value;
  }
  return profile;
}

/**
 * Loads a published profile for server rendering (API_INTERNAL_URL, no
 * session, not cached). Returns null for a 404: the API answers the same for
 * a missing and an unpublished profile.
 *
 * Throws NetworkError when the API is unreachable or slower than the timeout,
 * ApiError for any other error status or an unexpected body.
 */
export async function getPublicProfile(
  slug: string,
  { timeoutMs = PUBLIC_PROFILE_TIMEOUT_MS }: { timeoutMs?: number } = {},
): Promise<PublicProfile | null> {
  let body: unknown;
  try {
    body = await apiFetch<unknown>(`/public/profiles/${encodeURIComponent(slug)}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
  const profile = toPublicProfile(body);
  if (!profile) {
    throw new ApiError({
      status: 200,
      code: "INVALID_RESPONSE",
      message: "Unexpected public profile body",
      details: {},
      requestId: null,
    });
  }
  return profile;
}
