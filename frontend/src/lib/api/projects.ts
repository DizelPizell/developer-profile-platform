import { apiFetch } from "./client";
import { ApiError } from "./errors";

export type ProjectStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";
export type ProjectVisibility = "PUBLIC" | "PRIVATE";

/** Text fields of a project, in form order (ProjectWrite in API_CONTRACT.md). */
export const PROJECT_TEXT_FIELDS = [
  "title",
  "summary",
  "role",
  "contribution",
  "description",
  "problem",
  "results",
] as const;
export type ProjectTextField = (typeof PROJECT_TEXT_FIELDS)[number];

/** Every field the form edits, in form order; technologies sits after role. */
export const PROJECT_FIELDS = [
  "title",
  "summary",
  "role",
  "technologies",
  "contribution",
  "description",
  "problem",
  "results",
] as const;
export type ProjectField = (typeof PROJECT_FIELDS)[number];

/** API limits in characters (ADR-015). */
export const PROJECT_FIELD_MAX_LENGTH: Record<ProjectTextField, number> = {
  title: 100,
  summary: 300,
  role: 100,
  contribution: 2000,
  description: 5000,
  problem: 2000,
  results: 2000,
};
export const TECHNOLOGY_MAX_LENGTH = 50;
export const TECHNOLOGIES_MAX = 20;
export const PROJECTS_MAX = 50;
export const FEATURED_MAX = 3;

export type ProjectResponse = {
  id: string;
  status: ProjectStatus;
  visibility: ProjectVisibility;
  title: string | null;
  summary: string | null;
  description: string | null;
  problem: string | null;
  results: string | null;
  role: string | null;
  contribution: string | null;
  technologies: string[];
  featured_position: number | null;
};

export type ProjectSummary = Pick<
  ProjectResponse,
  "id" | "status" | "visibility" | "title" | "summary" | "technologies" | "featured_position"
>;

export type ProjectListResponse = { items: ProjectSummary[] };

/**
 * A present field changes; null clears a text field. technologies replaces the
 * whole list in the given order and cannot be null.
 */
export type ProjectWrite = Partial<Record<ProjectTextField, string | null>> & {
  technologies?: string[];
};

export type FeaturedProjectsResponse = {
  items: { project_id: string; position: number }[];
};

function projectPath(id: string, action = ""): string {
  return `/projects/${encodeURIComponent(id)}${action ? `/${action}` : ""}`;
}

export function listProjects(init: { signal?: AbortSignal } = {}) {
  return apiFetch<ProjectListResponse>("/projects", { signal: init.signal });
}

export function getProject(id: string, init: { signal?: AbortSignal } = {}) {
  return apiFetch<ProjectResponse>(projectPath(id), { signal: init.signal });
}

export function createProject(body: ProjectWrite) {
  return apiFetch<ProjectResponse>("/projects", { method: "POST", json: body });
}

export function updateProject(id: string, body: ProjectWrite) {
  return apiFetch<ProjectResponse>(projectPath(id), { method: "PATCH", json: body });
}

/** 204 without a body. */
export function deleteProject(id: string) {
  return apiFetch<void>(projectPath(id), { method: "DELETE" });
}

export function publishProject(id: string) {
  return apiFetch<ProjectResponse>(projectPath(id, "publish"), { method: "POST" });
}

export function archiveProject(id: string) {
  return apiFetch<ProjectResponse>(projectPath(id, "archive"), { method: "POST" });
}

export function setProjectVisibility(id: string, visibility: ProjectVisibility) {
  return apiFetch<ProjectResponse>(projectPath(id, "visibility"), {
    method: "POST",
    json: { visibility },
  });
}

export function featureProject(id: string) {
  return apiFetch<FeaturedProjectsResponse>(projectPath(id, "showcase"), { method: "POST" });
}

export function unfeatureProject(id: string) {
  return apiFetch<FeaturedProjectsResponse>(projectPath(id, "showcase"), { method: "DELETE" });
}

/** The complete current featured set in the new order. */
export function reorderFeatured(projectIds: string[]) {
  return apiFetch<FeaturedProjectsResponse>("/profile/featured-projects/reorder", {
    method: "POST",
    json: { project_ids: projectIds },
  });
}

function isProjectField(value: unknown): value is ProjectField {
  return (PROJECT_FIELDS as readonly unknown[]).includes(value);
}

/** Fields from a PROJECT_INCOMPLETE error (details.missing_fields), in form order. */
export function missingProjectFields(error: unknown): ProjectField[] {
  if (!(error instanceof ApiError) || error.code !== "PROJECT_INCOMPLETE") {
    return [];
  }
  const missing = error.details.missing_fields;
  if (!Array.isArray(missing)) {
    return [];
  }
  return PROJECT_FIELDS.filter((field) => missing.includes(field));
}

/** A field error from a VALIDATION_ERROR. item is set for one technology in the list. */
export type ProjectFieldError = { type: string; item: boolean };

/**
 * Errors per field from a VALIDATION_ERROR (details.fields). loc ["body", "<field>"]
 * is the field itself; ["body", "technologies", <index>] is one technology.
 * Entries for other locations are skipped; the first error of a field wins.
 */
export function projectFieldErrors(
  error: unknown,
): Partial<Record<ProjectField, ProjectFieldError>> {
  const result: Partial<Record<ProjectField, ProjectFieldError>> = {};
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
    if (!Array.isArray(loc) || loc[0] !== "body" || typeof type !== "string") {
      continue;
    }
    const field = loc[1];
    const item = field === "technologies" && loc.length === 3 && typeof loc[2] === "number";
    if (!isProjectField(field) || (loc.length !== 2 && !item) || field in result) {
      continue;
    }
    result[field] = { type, item };
  }
  return result;
}
