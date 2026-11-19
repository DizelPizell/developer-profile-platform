import { apiFetch } from "./client";
import { isMediaPath } from "./config";
import { ApiError } from "./errors";
import { type PublicGitHub, readPublicGitHub } from "./github";
import { CONTACT_TYPES, type ContactType } from "./profile";

/**
 * A contact of the public profile (ADR-020). EMAIL and PHONE only say that they
 * exist: their value comes from revealContact on a click.
 */
export type PublicContact = {
  type: ContactType;
  value: string | null;
  label: string | null;
  url: string | null;
};

/** The answer of the reveal endpoint, checked against the requested type. */
export type RevealedContact = { type: "EMAIL" | "PHONE"; value: string; url: string };

/** PublicProject from API_CONTRACT.md: a PUBLISHED + PUBLIC project (ADR-015). */
export type PublicProject = {
  id: string;
  title: string;
  summary: string;
  role: string;
  /** In the developer's order. */
  technologies: string[];
  /** ADR-019; null hides the block. */
  github: PublicGitHub | null;
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
  /** In API order; [] when the field is missing or wrong. */
  contacts: PublicContact[];
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
  const { github, fault } = readPublicGitHub(value.github);
  if (fault !== null) {
    // One line per project per request: the first wrong field, never a value.
    console.warn(`Public project ${value.id as string}: invalid field ${fault}`);
  }
  return {
    id: value.id as string,
    title: value.title as string,
    summary: value.summary as string,
    role: value.role as string,
    technologies: [...technologies],
    github,
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

/**
 * The `contacts` field, like `github` of a project: a wrong shape gives no contacts,
 * names the first wrong field and leaves the profile working. A missing field is not
 * a fault. EMAIL and PHONE never keep a value, whatever the body holds, so it cannot
 * reach the HTML or the props of a client component.
 */
function readContacts(value: unknown): { contacts: PublicContact[]; fault: string | null } {
  if (value === undefined) {
    return { contacts: [], fault: null };
  }
  if (!Array.isArray(value)) {
    return { contacts: [], fault: "contacts" };
  }
  const contacts: PublicContact[] = [];
  for (const item of value) {
    const type = isRecord(item) ? CONTACT_TYPES.find((known) => known === item.type) : undefined;
    if (!isRecord(item) || type === undefined) {
      return { contacts: [], fault: "contacts.type" };
    }
    if (type === "EMAIL" || type === "PHONE") {
      contacts.push({ type, value: null, label: null, url: null });
      continue;
    }
    const { value: text, label, url } = item;
    if (typeof text !== "string") {
      return { contacts: [], fault: "contacts.value" };
    }
    if (typeof url !== "string") {
      return { contacts: [], fault: "contacts.url" };
    }
    if (type === "OTHER" && typeof label !== "string") {
      return { contacts: [], fault: "contacts.label" };
    }
    contacts.push({ type, value: text, label: type === "OTHER" ? (label as string) : null, url });
  }
  return { contacts, fault: null };
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
  const { contacts, fault } = readContacts(body.contacts);
  if (fault !== null) {
    // One line per profile per request: the first wrong field, never a value.
    console.warn(`Public profile ${body.slug}: invalid field ${fault}`);
  }
  const profile: PublicProfile = {
    slug: body.slug,
    github_login: body.github_login,
    contacts,
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
    throw invalidResponse("Unexpected public profile body");
  }
  return profile;
}

/** A screenshot of PublicProjectPage, with a path checked by isMediaPath. */
export type PublicScreenshot = {
  url: string;
  caption: string | null;
  width: number;
  height: number;
};

/** PublicProjectPage from API_CONTRACT.md (step 4.3), the fields the page shows. */
export type PublicProjectPage = {
  id: string;
  title: string;
  summary: string;
  description: string | null;
  problem: string | null;
  results: string | null;
  role: string;
  contribution: string;
  /** In the developer's order. */
  technologies: string[];
  /** An http or https URL; anything else is null (DESIGN.md, «Demo block»). */
  demo_url: string | null;
  /** In the developer's order, without the ones that fail the check. */
  screenshots: PublicScreenshot[];
  github: PublicGitHub | null;
  /** The owner's avatar is not read: the page does not show it. */
  owner: { slug: string; display_name: string };
};

/** The side cap of the re-encoded screenshot (SCREENSHOT_MAX_SIDE, ADR-0022). */
const SCREENSHOT_MAX_SIDE = 2560;

const PAGE_TEXT_FIELDS = ["id", "title", "summary", "role", "contribution"] as const;
const PAGE_NULLABLE_FIELDS = ["description", "problem", "results"] as const;

function isSide(value: unknown): value is number {
  return Number.isInteger(value) && (value as number) >= 1 && (value as number) <= SCREENSHOT_MAX_SIDE;
}

/** A link the demo button may open: it parses and is http or https. */
function isDemoUrl(value: string): boolean {
  try {
    const { protocol } = new URL(value);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

/** The first wrong field of a screenshot, or null when it can be shown. */
function screenshotFault(value: unknown): string | null {
  if (!isRecord(value)) {
    return "screenshots";
  }
  if (typeof value.url !== "string" || !isMediaPath(value.url)) {
    return "screenshots.url";
  }
  if (value.caption !== null && typeof value.caption !== "string") {
    return "screenshots.caption";
  }
  if (!isSide(value.width)) {
    return "screenshots.width";
  }
  if (!isSide(value.height)) {
    return "screenshots.height";
  }
  return null;
}

/**
 * Copies only the known fields. A wrong project field is null (an unexpected body);
 * a wrong demo link, screenshot or `github` is left out with one log line each,
 * naming the project and the field, never the value.
 */
function toPublicProjectPage(body: unknown): PublicProjectPage | null {
  if (!isRecord(body)) {
    return null;
  }
  for (const field of PAGE_TEXT_FIELDS) {
    if (typeof body[field] !== "string") {
      return null;
    }
  }
  for (const field of PAGE_NULLABLE_FIELDS) {
    if (body[field] !== null && typeof body[field] !== "string") {
      return null;
    }
  }
  const { technologies, demo_url: demoUrl, screenshots, owner } = body;
  if (!Array.isArray(technologies) || !technologies.every((name) => typeof name === "string")) {
    return null;
  }
  if (demoUrl !== null && typeof demoUrl !== "string") {
    return null;
  }
  if (!Array.isArray(screenshots)) {
    return null;
  }
  if (!isRecord(owner) || typeof owner.slug !== "string" || typeof owner.display_name !== "string") {
    return null;
  }

  const id = body.id as string;
  const warn = (field: string) => console.warn(`Public project ${id}: invalid field ${field}`);
  let demo: string | null = demoUrl;
  if (demo !== null && !isDemoUrl(demo)) {
    warn("demo_url");
    demo = null;
  }
  const shown: PublicScreenshot[] = [];
  for (const item of screenshots) {
    const fault = screenshotFault(item);
    if (fault !== null) {
      warn(fault);
      continue;
    }
    const { url, caption, width, height } = item as PublicScreenshot;
    shown.push({ url, caption, width, height });
  }
  const { github, fault } = readPublicGitHub(body.github);
  if (fault !== null) {
    warn(fault);
  }

  return {
    id,
    title: body.title as string,
    summary: body.summary as string,
    description: body.description as string | null,
    problem: body.problem as string | null,
    results: body.results as string | null,
    role: body.role as string,
    contribution: body.contribution as string,
    technologies: [...technologies],
    demo_url: demo,
    screenshots: shown,
    github,
    owner: { slug: owner.slug, display_name: owner.display_name },
  };
}

/**
 * Loads a PUBLISHED + PUBLIC project of a published profile for server rendering,
 * like getPublicProfile. Returns null for a 404: the API answers the same for a
 * private profile, another user's project and a draft, hidden or archived one.
 */
export async function getPublicProject(
  slug: string,
  id: string,
  { timeoutMs = PUBLIC_PROFILE_TIMEOUT_MS }: { timeoutMs?: number } = {},
): Promise<PublicProjectPage | null> {
  let body: unknown;
  try {
    body = await apiFetch<unknown>(
      `/public/profiles/${encodeURIComponent(slug)}/projects/${encodeURIComponent(id)}`,
      { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) },
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
    }
    throw error;
  }
  const page = toPublicProjectPage(body);
  if (!page) {
    throw invalidResponse("Unexpected public project body");
  }
  return page;
}

function invalidResponse(message: string): ApiError {
  return new ApiError({ status: 200, code: "INVALID_RESPONSE", message, details: {}, requestId: null });
}

/**
 * Asks for the email or the phone of a published profile, from the browser on a click
 * (ADR-020). The answer must be of the requested type with the link the server builds
 * from the value; anything else is an ApiError, so a wrong body is never shown or linked.
 */
export async function revealContact(
  slug: string,
  type: RevealedContact["type"],
): Promise<RevealedContact> {
  const body = await apiFetch<unknown>(
    `/public/profiles/${encodeURIComponent(slug)}/contacts?type=${type}`,
    { cache: "no-store" },
  );
  const scheme = type === "EMAIL" ? "mailto:" : "tel:";
  if (
    !isRecord(body) ||
    body.type !== type ||
    typeof body.value !== "string" ||
    body.value === "" ||
    body.url !== scheme + body.value
  ) {
    throw invalidResponse("Unexpected contact body");
  }
  return { type, value: body.value, url: body.url };
}
