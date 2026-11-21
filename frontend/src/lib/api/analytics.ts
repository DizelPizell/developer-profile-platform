import { apiFetch } from "./client";

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
