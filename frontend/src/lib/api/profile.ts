import { apiFetch } from "./client";
import { ApiError } from "./errors";

export type ProfileStatus = "PRIVATE" | "PUBLISHED";

/** The fields the developer edits (ProfileUpdate in API_CONTRACT.md). */
export const PROFILE_FIELDS = ["display_name", "headline", "bio", "location"] as const;
export type ProfileField = (typeof PROFILE_FIELDS)[number];

/** API limits for each field, in characters. */
export const PROFILE_FIELD_MAX_LENGTH: Record<ProfileField, number> = {
  display_name: 100,
  headline: 160,
  bio: 2000,
  location: 100,
};

export type OwnProfileResponse = {
  slug: string;
  status: ProfileStatus;
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
};

/** A present field changes; null clears it. */
export type ProfileUpdate = Partial<Record<ProfileField, string | null>>;

export function getProfile(init: { signal?: AbortSignal } = {}) {
  return apiFetch<OwnProfileResponse>("/profile", { signal: init.signal });
}

export function updateProfile(update: ProfileUpdate) {
  return apiFetch<OwnProfileResponse>("/profile", { method: "PATCH", json: update });
}

export function publishProfile() {
  return apiFetch<OwnProfileResponse>("/profile/publish", { method: "POST" });
}

export function unpublishProfile() {
  return apiFetch<OwnProfileResponse>("/profile/unpublish", { method: "POST" });
}

function isProfileField(value: unknown): value is ProfileField {
  return (PROFILE_FIELDS as readonly unknown[]).includes(value);
}

/** Fields from a PROFILE_INCOMPLETE error (details.missing_fields), in form order. */
export function missingProfileFields(error: unknown): ProfileField[] {
  if (!(error instanceof ApiError) || error.code !== "PROFILE_INCOMPLETE") {
    return [];
  }
  const missing = error.details.missing_fields;
  if (!Array.isArray(missing)) {
    return [];
  }
  return PROFILE_FIELDS.filter((field) => missing.includes(field));
}

/**
 * Error types per field from a VALIDATION_ERROR (details.fields with
 * loc ["body", "<field>"]). Entries for other locations are skipped; the
 * first error of a field wins.
 */
export function profileFieldErrors(error: unknown): Partial<Record<ProfileField, string>> {
  const result: Partial<Record<ProfileField, string>> = {};
  if (!(error instanceof ApiError) || error.code !== "VALIDATION_ERROR") {
    return result;
  }
  const fields = error.details.fields;
  if (!Array.isArray(fields)) {
    return result;
  }
  for (const entry of fields) {
    if (typeof entry !== "object" || entry === null) {
      continue;
    }
    const { loc, type } = entry as { loc?: unknown; type?: unknown };
    if (!Array.isArray(loc) || loc.length !== 2 || loc[0] !== "body") {
      continue;
    }
    const field = loc[1];
    if (isProfileField(field) && typeof type === "string" && !(field in result)) {
      result[field] = type;
    }
  }
  return result;
}
