import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { isAnalyticsEventType, trackEvent } from "./analytics";

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
