import { apiFetch } from "./client";
import { ApiError } from "./errors";

/** PublicProject from API_CONTRACT.md: a PUBLISHED + PUBLIC project (ADR-015). */
export type PublicProject = {
  id: string;
  title: string;
  summary: string;
  role: string;
  /** In the developer's order. */
  technologies: string[];
};

/** PublicFeaturedProject: a public project with its place 1..3. */
export type PublicFeaturedProject = PublicProject & { position: number };

/** PublicProfileResponse from API_CONTRACT.md: the whitelisted public fields. */
export type PublicProfile = {
  slug: string;
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
  /** Sorted by position. */
  featured: PublicFeaturedProject[];
  /** Newest first (API order). */
  other: PublicProject[];
};

export const PUBLIC_PROFILE_TIMEOUT_MS = 5000;

const NULLABLE_FIELDS = ["display_name", "headline", "bio", "location", "avatar_url"] as const;
const PROJECT_TEXT_FIELDS = ["id", "title", "summary", "role"] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Copies only the whitelisted project fields; null when the shape is wrong. */
function toPublicProject(value: unknown): PublicProject | null {
  if (!isRecord(value)) {
    return null;
  }
  for (const field of PROJECT_TEXT_FIELDS) {
    if (typeof value[field] !== "string") {
      return null;
    }
  }
  const { technologies } = value;
  if (!Array.isArray(technologies) || !technologies.every((name) => typeof name === "string")) {
    return null;
  }
  return {
    id: value.id as string,
    title: value.title as string,
    summary: value.summary as string,
    role: value.role as string,
    technologies: [...technologies],
  };
}

function toFeaturedProject(value: unknown): PublicFeaturedProject | null {
  const project = toPublicProject(value);
  if (!project || !isRecord(value)) {
    return null;
  }
  const { position } = value;
  if (typeof position !== "number" || !Number.isInteger(position) || position < 1 || position > 3) {
    return null;
  }
  return { ...project, position };
}

/** Every item converted, or null when the value is not an array or an item is wrong. */
function toList<T>(value: unknown, convert: (item: unknown) => T | null): T[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const items: T[] = [];
  for (const item of value) {
    const converted = convert(item);
    if (converted === null) {
      return null;
    }
    items.push(converted);
  }
  return items;
}

/** Copies only the known fields; anything else in the body is dropped. */
function toPublicProfile(body: unknown): PublicProfile | null {
  if (!isRecord(body)) {
    return null;
  }
  if (typeof body.slug !== "string" || typeof body.github_login !== "string") {
    return null;
  }
  const featured = toList(body.featured, toFeaturedProject);
  const other = toList(body.other, toPublicProject);
  if (featured === null || other === null) {
    return null;
  }
  const profile: PublicProfile = {
    slug: body.slug,
    github_login: body.github_login,
    display_name: null,
    headline: null,
    bio: null,
    location: null,
    avatar_url: null,
    // The contract orders them by position; the cards follow position even if not.
    featured: featured.sort((a, b) => a.position - b.position),
    other,
  };
  for (const field of NULLABLE_FIELDS) {
    const value = body[field];
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
