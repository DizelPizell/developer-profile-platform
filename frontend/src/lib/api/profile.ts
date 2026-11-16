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

/** Contact types of ADR-020; one of each standard type, up to 3 OTHER. */
export const CONTACT_TYPES = ["EMAIL", "TELEGRAM", "LINKEDIN", "PHONE", "OTHER"] as const;
export type ContactType = (typeof CONTACT_TYPES)[number];

/** A stored contact: the normalized value and the link the server built. */
export type Contact = { type: ContactType; value: string; label: string | null; url: string };

/** An item of ProfileUpdate.contacts; label only for OTHER, never url. */
export type ContactWrite = { type: ContactType; value: string; label?: string };

export type OwnProfileResponse = {
  slug: string;
  status: ProfileStatus;
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
  /** In the order of position. */
  contacts: Contact[];
};

/** A present field changes; null clears it. contacts replaces the whole list. */
export type ProfileUpdate = Partial<Record<ProfileField, string | null>> & {
  contacts?: ContactWrite[];
};

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
  for (const { loc, type } of bodyErrors(error)) {
    const field = loc[1];
    if (loc.length === 2 && isProfileField(field) && !(field in result)) {
      result[field] = type;
    }
  }
  return result;
}

/** The entries of a VALIDATION_ERROR (details.fields) under "body". */
function bodyErrors(error: unknown): { loc: unknown[]; type: string }[] {
  if (!(error instanceof ApiError) || error.code !== "VALIDATION_ERROR") {
    return [];
  }
  const fields = error.details.fields;
  if (!Array.isArray(fields)) {
    return [];
  }
  return fields.filter((entry): entry is { loc: unknown[]; type: string } => {
    if (typeof entry !== "object" || entry === null) {
      return false;
    }
    const { loc, type } = entry as { loc?: unknown; type?: unknown };
    return Array.isArray(loc) && loc[0] === "body" && typeof type === "string";
  });
}

export type ContactItemError = { index: number; field: "value" | "label" | "type"; type: string };

/**
 * Contact errors of a VALIDATION_ERROR. loc ["body", "contacts", <index>, <field>]
 * is an item, where the index is the place in the list that was sent;
 * ["body", "contacts"] is the list itself (the first one wins).
 */
export function profileContactErrors(error: unknown): {
  items: ContactItemError[];
  list: string | null;
} {
  const items: ContactItemError[] = [];
  let list: string | null = null;
  for (const { loc, type } of bodyErrors(error)) {
    if (loc[1] !== "contacts") {
      continue;
    }
    const [, , index, field] = loc;
    if (loc.length === 2) {
      list ??= type;
    } else if (
      loc.length === 4 &&
      typeof index === "number" &&
      (field === "value" || field === "label" || field === "type")
    ) {
      items.push({ index, field, type });
    }
  }
  return { items, list };
}
