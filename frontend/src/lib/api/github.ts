import { apiFetch } from "./client";
import { ApiError } from "./errors";

/*
 * GitHub data in the cabinet (API_CONTRACT.md, GitHub; ADR-016..ADR-018). Responses
 * are read through a whitelist: unknown fields are dropped, and a wrong shape or an
 * unknown enum value is an unexpected body (INVALID_RESPONSE).
 *
 * github_repo_id is a JS number. GitHub's ids are about 10^9 today, far below
 * Number.MAX_SAFE_INTEGER (2^53 - 1); an id above it would lose precision in
 * JSON.parse, so it is treated as an unexpected body rather than used.
 */

export const GITHUB_RELATIONS = ["OWNER", "CONTRIBUTOR", "NONE"] as const;
export type GitHubRelation = (typeof GITHUB_RELATIONS)[number];

export const GITHUB_SYNC_STATUSES = [
  "NOT_SYNCED",
  "QUEUED",
  "SYNCING",
  "SYNCED",
  "FAILED",
] as const;
export type GitHubSyncStatus = (typeof GITHUB_SYNC_STATUSES)[number];

export type GitHubLanguage = { name: string; bytes: number };

export type GitHubSync = {
  status: GitHubSyncStatus;
  /** ISO 8601 date-times, kept as strings. */
  last_success_at: string | null;
  next_manual_sync_at: string | null;
};

/** ProjectGitHub: the `github` object of ProjectResponse (cabinet only). */
export type ProjectGitHub = {
  github_repo_id: number;
  full_name: string;
  html_url: string;
  description: string | null;
  /** Ordered by bytes, descending; empty until the first successful sync. */
  languages: GitHubLanguage[];
  pushed_at: string | null;
  is_fork: boolean;
  parent_full_name: string | null;
  is_archived: boolean;
  relation: GitHubRelation;
  unavailable: boolean;
  synced_at: string | null;
  sync: GitHubSync;
};

/** ProjectSummaryGitHub: which repository a project links, in GET /projects. */
export type ProjectSummaryGitHub = { full_name: string; html_url: string };

/** An item of GitHubRepositoryListResponse. */
export type GitHubRepository = {
  github_repo_id: number;
  full_name: string;
  html_url: string;
  description: string | null;
  is_fork: boolean;
  is_archived: boolean;
  pushed_at: string | null;
  linked_project_id: string | null;
};

/** GitHubRepositoryListResponse: 100 per page; next_page is null on the last page. */
export type GitHubRepositoryPage = {
  items: GitHubRepository[];
  next_page: number | null;
};

/** Body of POST /projects/{id}/repository. */
export type RepositoryLinkRequest = { full_name: string };

export const REPOSITORY_PAGE_MAX = 100;

type Fields = Record<string, unknown>;

function isRecord(value: unknown): value is Fields {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const isString = (value: unknown): value is string => typeof value === "string";
const isNullableString = (value: unknown): value is string | null =>
  value === null || typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";

function isRepoId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function isOneOf<T extends string>(values: readonly T[], value: unknown): value is T {
  return (values as readonly unknown[]).includes(value);
}

function toLanguage(value: unknown): GitHubLanguage | null {
  if (!isRecord(value) || !isString(value.name)) {
    return null;
  }
  const { bytes } = value;
  if (typeof bytes !== "number" || !Number.isSafeInteger(bytes) || bytes < 0) {
    return null;
  }
  return { name: value.name, bytes };
}

function toSync(value: unknown): GitHubSync | null {
  if (
    !isRecord(value) ||
    !isOneOf(GITHUB_SYNC_STATUSES, value.status) ||
    !isNullableString(value.last_success_at) ||
    !isNullableString(value.next_manual_sync_at)
  ) {
    return null;
  }
  return {
    status: value.status,
    last_success_at: value.last_success_at,
    next_manual_sync_at: value.next_manual_sync_at,
  };
}

/** Copies only the ProjectGitHub fields; undefined when the shape is wrong. */
function toProjectGitHub(value: unknown): ProjectGitHub | undefined {
  if (
    !isRecord(value) ||
    !isRepoId(value.github_repo_id) ||
    !isString(value.full_name) ||
    !isString(value.html_url) ||
    !isNullableString(value.description) ||
    !isNullableString(value.pushed_at) ||
    !isBoolean(value.is_fork) ||
    !isNullableString(value.parent_full_name) ||
    !isBoolean(value.is_archived) ||
    !isOneOf(GITHUB_RELATIONS, value.relation) ||
    !isBoolean(value.unavailable) ||
    !isNullableString(value.synced_at) ||
    !Array.isArray(value.languages)
  ) {
    return undefined;
  }
  const languages = value.languages.map(toLanguage);
  const sync = toSync(value.sync);
  if (languages.includes(null) || sync === null) {
    return undefined;
  }
  return {
    github_repo_id: value.github_repo_id,
    full_name: value.full_name,
    html_url: value.html_url,
    description: value.description,
    languages: languages as GitHubLanguage[],
    pushed_at: value.pushed_at,
    is_fork: value.is_fork,
    parent_full_name: value.parent_full_name,
    is_archived: value.is_archived,
    relation: value.relation,
    unavailable: value.unavailable,
    synced_at: value.synced_at,
    sync,
  };
}

function toProjectSummaryGitHub(value: unknown): ProjectSummaryGitHub | undefined {
  if (!isRecord(value) || !isString(value.full_name) || !isString(value.html_url)) {
    return undefined;
  }
  return { full_name: value.full_name, html_url: value.html_url };
}

/**
 * The `github` field of a project body: null, or the whitelisted object. Undefined
 * when the field is missing or has the wrong shape.
 */
export function readProjectGitHub(body: Fields): ProjectGitHub | null | undefined {
  return body.github === null ? null : toProjectGitHub(body.github);
}

/** The same for an item of GET /projects. */
export function readProjectSummaryGitHub(body: Fields): ProjectSummaryGitHub | null | undefined {
  return body.github === null ? null : toProjectSummaryGitHub(body.github);
}

function toRepository(value: unknown): GitHubRepository | null {
  if (
    !isRecord(value) ||
    !isRepoId(value.github_repo_id) ||
    !isString(value.full_name) ||
    !isString(value.html_url) ||
    !isNullableString(value.description) ||
    !isBoolean(value.is_fork) ||
    !isBoolean(value.is_archived) ||
    !isNullableString(value.pushed_at) ||
    !isNullableString(value.linked_project_id)
  ) {
    return null;
  }
  return {
    github_repo_id: value.github_repo_id,
    full_name: value.full_name,
    html_url: value.html_url,
    description: value.description,
    is_fork: value.is_fork,
    is_archived: value.is_archived,
    pushed_at: value.pushed_at,
    linked_project_id: value.linked_project_id,
  };
}

function toRepositoryPage(body: unknown): GitHubRepositoryPage | null {
  if (!isRecord(body) || !Array.isArray(body.items)) {
    return null;
  }
  const { next_page: nextPage } = body;
  if (nextPage !== null && !(typeof nextPage === "number" && Number.isSafeInteger(nextPage))) {
    return null;
  }
  const items = body.items.map(toRepository);
  if (items.includes(null)) {
    return null;
  }
  return { items: items as GitHubRepository[], next_page: nextPage };
}

/** The error for a 2xx body that does not match the contract. */
export function invalidResponse(what: string): ApiError {
  return new ApiError({
    status: 200,
    code: "INVALID_RESPONSE",
    message: `Unexpected ${what} body`,
    details: {},
    requestId: null,
  });
}

/**
 * One page of the user's own public repositories (1..100), read from GitHub by the
 * backend; a page is cached there for 5 minutes.
 */
export async function listRepositories(
  page: number,
  init: { signal?: AbortSignal } = {},
): Promise<GitHubRepositoryPage> {
  if (!Number.isSafeInteger(page) || page < 1 || page > REPOSITORY_PAGE_MAX) {
    throw new RangeError("page must be an integer from 1 to 100");
  }
  const query = new URLSearchParams({ page: String(page) });
  const body = await apiFetch<unknown>(`/integrations/github/repositories?${query}`, {
    signal: init.signal,
  });
  const result = toRepositoryPage(body);
  if (!result) {
    throw invalidResponse("repository list");
  }
  return result;
}

const OWNER_PATTERN = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/;
const NAME_PATTERN = /^[A-Za-z0-9._-]{1,100}$/;

/**
 * Whether a value is "owner/name" as RepositoryLinkRequest accepts it. The client
 * check spares a request; the API stays the source of truth (422 VALIDATION_ERROR).
 */
export function isRepositoryFullName(value: string): boolean {
  const parts = value.split("/");
  if (parts.length !== 2) {
    return false;
  }
  const [owner, name] = parts;
  return OWNER_PATTERN.test(owner) && NAME_PATTERN.test(name) && name !== "." && name !== "..";
}

/** Error codes of the GitHub endpoints that the cabinet tells apart (DESIGN.md). */
export const GITHUB_ERROR_CODES = [
  "GITHUB_LOGIN_OUTDATED",
  "GITHUB_RELATION_NOT_FOUND",
  "GITHUB_REPOSITORY_NOT_FOUND",
  "GITHUB_REPOSITORY_ALREADY_LINKED",
  "GITHUB_USER_LIMIT_REACHED",
  "GITHUB_RATE_LIMITED",
  "GITHUB_UNAVAILABLE",
  "PROJECT_LIMIT_REACHED",
  "VALIDATION_ERROR",
  "NOT_FOUND",
  "INTERNAL_ERROR",
] as const;
export type GitHubErrorCode = (typeof GITHUB_ERROR_CODES)[number];

/**
 * The code of an API error from a GitHub endpoint. "OTHER" for any other code
 * (including an unreadable error body) and for anything that is not an ApiError;
 * NetworkError stays a separate case for the caller.
 */
export function githubErrorCode(error: unknown): GitHubErrorCode | "OTHER" {
  if (error instanceof ApiError && isOneOf(GITHUB_ERROR_CODES, error.code)) {
    return error.code;
  }
  return "OTHER";
}

/**
 * Seconds to wait from details.retry_after_seconds of a 429 GITHUB_USER_LIMIT_REACHED
 * or 503 GITHUB_RATE_LIMITED. The Retry-After header is not used: CORS exposes only
 * X-Request-ID to the browser. Null when missing or not a non-negative integer.
 */
export function retryAfterSeconds(error: unknown): number | null {
  const code = githubErrorCode(error);
  if (code !== "GITHUB_USER_LIMIT_REACHED" && code !== "GITHUB_RATE_LIMITED") {
    return null;
  }
  const value = (error as ApiError).details.retry_after_seconds;
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;
}

/** The project that already links the repository: details.project_id of ALREADY_LINKED. */
export function linkedProjectId(error: unknown): string | null {
  if (githubErrorCode(error) !== "GITHUB_REPOSITORY_ALREADY_LINKED") {
    return null;
  }
  const value = (error as ApiError).details.project_id;
  return typeof value === "string" && value !== "" ? value : null;
}

/** details.limit of PROJECT_LIMIT_REACHED. */
export function projectLimit(error: unknown): number | null {
  if (githubErrorCode(error) !== "PROJECT_LIMIT_REACHED") {
    return null;
  }
  const value = (error as ApiError).details.limit;
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0 ? value : null;
}
