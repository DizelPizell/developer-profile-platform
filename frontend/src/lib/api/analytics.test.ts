import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  getProfileAnalytics,
  getProjectAnalytics,
  isAnalyticsEventType,
  trackEvent,
} from "./analytics";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

const PROJECT_ID = "0b6c7c1e-5d1f-4b8e-9a51-1d2f3e4a5b6c";

describe("trackEvent", () => {
  test("POST /analytics/events with the body, keepalive and credentials", () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 202 }));

    trackEvent("DEMO_CLICK", "ann", PROJECT_ID);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/analytics/events");
    expect(init?.method).toBe("POST");
    expect(init?.keepalive).toBe(true);
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init?.body as string)).toEqual({
      type: "DEMO_CLICK",
      slug: "ann",
      project_id: PROJECT_ID,
    });
  });

  test("a profile event sends project_id null", () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 202 }));

    trackEvent("PROFILE_VIEW", "ann", null);

    expect(JSON.parse(fetchMock.mock.calls[0][1]?.body as string)).toEqual({
      type: "PROFILE_VIEW",
      slug: "ann",
      project_id: null,
    });
  });

  test.each([
    ["a network error", () => fetchMock.mockRejectedValue(new TypeError("Failed to fetch"))],
    [
      "429",
      () =>
        fetchMock.mockResolvedValue(
          Response.json({ error: { code: "RATE_LIMITED", message: "Too many" } }, { status: 429 }),
        ),
    ],
  ])("%s is swallowed: nothing thrown, nothing rejected", async (_, arrange) => {
    arrange();
    const unhandled = vi.fn();
    process.on("unhandledRejection", unhandled);

    expect(() => trackEvent("PROFILE_VIEW", "ann", null)).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));

    process.off("unhandledRejection", unhandled);
    expect(unhandled).not.toHaveBeenCalled();
  });
});

describe("isAnalyticsEventType", () => {
  test("only the five types", () => {
    expect(isAnalyticsEventType("CONTACT_CLICK")).toBe(true);
    expect(isAnalyticsEventType("contact_click")).toBe(false);
    expect(isAnalyticsEventType(undefined)).toBe(false);
  });
});

const PERIOD = { days: 7, start: "2026-11-15", end: "2026-11-21" };
const COUNTS = { project_views: 3, demo_clicks: 1, github_clicks: 0 };

describe("getProfileAnalytics", () => {
  const body = {
    period: PERIOD,
    totals: { ...COUNTS, profile_views: 9, contact_clicks: 2 },
    projects: [{ id: PROJECT_ID, title: null, status: "DRAFT", visibility: "PRIVATE", counts: COUNTS }],
  };

  test("GET /analytics/profile?days=N with credentials returns the body", async () => {
    fetchMock.mockResolvedValue(Response.json(body));

    await expect(getProfileAnalytics(7)).resolves.toEqual(body);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/analytics/profile?days=7");
    expect(init?.credentials).toBe("include");
  });

  test.each([
    ["a missing period", { ...body, period: undefined }],
    ["a negative counter", { ...body, totals: { ...body.totals, profile_views: -1 } }],
    ["a project without counts", { ...body, projects: [{ ...body.projects[0], counts: undefined }] }],
    ["a date that is not a day", { ...body, period: { ...PERIOD, end: "21.11.2026" } }],
  ])("%s is INVALID_RESPONSE", async (_, wrong) => {
    fetchMock.mockResolvedValue(Response.json(wrong));

    await expect(getProfileAnalytics(30)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

describe("getProjectAnalytics", () => {
  const body = { period: PERIOD, totals: COUNTS, daily: [{ day: "2026-11-21", counts: COUNTS }] };

  test("GET /analytics/projects/{id}?days=N returns the body", async () => {
    fetchMock.mockResolvedValue(Response.json(body));

    await expect(getProjectAnalytics(PROJECT_ID, 90)).resolves.toEqual(body);

    expect(fetchMock.mock.calls[0][0]).toBe(`http://api.test/api/v1/analytics/projects/${PROJECT_ID}?days=90`);
  });

  test("a 404 stays an ApiError NOT_FOUND", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "NOT_FOUND", message: "Not found" } }, { status: 404 }),
    );

    await expect(getProjectAnalytics(PROJECT_ID, 30)).rejects.toMatchObject({ status: 404, code: "NOT_FOUND" });
  });

  test("a day without counts is INVALID_RESPONSE", async () => {
    fetchMock.mockResolvedValue(Response.json({ ...body, daily: [{ day: "2026-11-21" }] }));

    await expect(getProjectAnalytics(PROJECT_ID, 30)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});
