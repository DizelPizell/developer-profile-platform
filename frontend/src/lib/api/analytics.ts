import { apiFetch } from "./client";
import { invalidResponse } from "./github";
import type { ProjectStatus, ProjectVisibility } from "./projects";

// Events of the public pages (ADR-0029). The visitor is not identified: the body is
// the type, the slug and the project, and nothing else.

export const ANALYTICS_EVENT_TYPES = [
  "PROFILE_VIEW",
  "PROJECT_VIEW",
  "DEMO_CLICK",
  "GITHUB_CLICK",
  "CONTACT_CLICK",
] as const;

export type AnalyticsEventType = (typeof ANALYTICS_EVENT_TYPES)[number];

export function isAnalyticsEventType(value: unknown): value is AnalyticsEventType {
  return (ANALYTICS_EVENT_TYPES as readonly unknown[]).includes(value);
}

/**
 * POST /analytics/events, sent and forgotten: never awaited by a caller, never throws.
 * keepalive lets the request outlive the page when a link takes the tab away.
 */
export function trackEvent(type: AnalyticsEventType, slug: string, projectId: string | null): void {
  apiFetch("/analytics/events", {
    method: "POST",
    json: { type, slug, project_id: projectId },
    keepalive: true,
  }).catch(() => {
    // Analytics is not critical: a failed event is not shown and not logged.
  });
}

// The owner's counters (step 7.2). Every number is a sum of events, not of people.

export const ANALYTICS_PERIODS = [7, 30, 90] as const;
export type AnalyticsDays = (typeof ANALYTICS_PERIODS)[number];

/** UTC days as "YYYY-MM-DD", both included; today is the end. */
export type AnalyticsPeriod = { days: number; start: string; end: string };

export type ProjectCounts = { project_views: number; demo_clicks: number; github_clicks: number };

export type ProfileCounts = ProjectCounts & { profile_views: number; contact_clicks: number };

export type ProjectAnalyticsItem = {
  id: string;
  title: string | null;
  status: ProjectStatus;
  visibility: ProjectVisibility;
  counts: ProjectCounts;
};

export type ProfileAnalytics = {
  period: AnalyticsPeriod;
  totals: ProfileCounts;
  /** Every own project in the order of GET /projects, zeros included. */
  projects: ProjectAnalyticsItem[];
};

export type ProjectDay = { day: string; counts: ProjectCounts };

export type ProjectAnalytics = {
  period: AnalyticsPeriod;
  totals: ProjectCounts;
  /** Every day of the period, oldest first, zeros included. */
  daily: ProjectDay[];
};

const PROJECT_COUNT_KEYS = ["project_views", "demo_clicks", "github_clicks"] as const;
const PROFILE_COUNT_KEYS = [...PROJECT_COUNT_KEYS, "profile_views", "contact_clicks"] as const;
const DAY = /^\d{4}-\d{2}-\d{2}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasCounts(value: unknown, keys: readonly string[]): boolean {
  return (
    isRecord(value) &&
    keys.every((key) => Number.isSafeInteger(value[key]) && (value[key] as number) >= 0)
  );
}

function isPeriod(value: unknown): value is AnalyticsPeriod {
  return (
    isRecord(value) &&
    Number.isSafeInteger(value.days) &&
    typeof value.start === "string" &&
    DAY.test(value.start) &&
    typeof value.end === "string" &&
    DAY.test(value.end)
  );
}

function isProjectItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    (value.title === null || typeof value.title === "string") &&
    typeof value.status === "string" &&
    typeof value.visibility === "string" &&
    hasCounts(value.counts, PROJECT_COUNT_KEYS)
  );
}

function isProjectDay(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.day === "string" &&
    DAY.test(value.day) &&
    hasCounts(value.counts, PROJECT_COUNT_KEYS)
  );
}

/** GET /analytics/profile?days=N: the totals and every own project. */
export async function getProfileAnalytics(
  days: AnalyticsDays,
  init: { signal?: AbortSignal } = {},
) {
  const body = await apiFetch<unknown>(`/analytics/profile?days=${days}`, { signal: init.signal });
  if (
    !isRecord(body) ||
    !isPeriod(body.period) ||
    !hasCounts(body.totals, PROFILE_COUNT_KEYS) ||
    !Array.isArray(body.projects) ||
    !body.projects.every(isProjectItem)
  ) {
    throw invalidResponse("profile analytics");
  }
  return body as ProfileAnalytics;
}

/** GET /analytics/projects/{id}?days=N: one own project by UTC day. */
export async function getProjectAnalytics(
  id: string,
  days: AnalyticsDays,
  init: { signal?: AbortSignal } = {},
) {
  const path = `/analytics/projects/${encodeURIComponent(id)}?days=${days}`;
  const body = await apiFetch<unknown>(path, { signal: init.signal });
  if (
    !isRecord(body) ||
    !isPeriod(body.period) ||
    !hasCounts(body.totals, PROJECT_COUNT_KEYS) ||
    !Array.isArray(body.daily) ||
    !body.daily.every(isProjectDay)
  ) {
    throw invalidResponse("project analytics");
  }
  return body as ProjectAnalytics;
}
