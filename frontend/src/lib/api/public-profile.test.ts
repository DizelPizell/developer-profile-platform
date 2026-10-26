// @vitest-environment node
// Server-side call: no window, so the client uses API_INTERNAL_URL.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import { getPublicProfile, PUBLIC_PROFILE_TIMEOUT_MS } from "./public-profile";

const fetchMock = vi.fn<typeof fetch>();

const PROFILE = {
  slug: "ann",
  display_name: "Ann",
  headline: "Backend",
  bio: "Hello",
  location: null,
  avatar_url: "https://avatars.githubusercontent.com/u/1",
  github_login: "ann",
};

beforeEach(() => {
  vi.stubEnv("API_INTERNAL_URL", "http://backend.internal:8000");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://browser.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

function errorResponse(status: number, code: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: "r-1" } },
    { status },
  );
}

describe("getPublicProfile", () => {
  test("GET via API_INTERNAL_URL, not cached, with a timeout signal", async () => {
    fetchMock.mockResolvedValue(Response.json(PROFILE));

    await expect(getPublicProfile("ann")).resolves.toEqual(PROFILE);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://backend.internal:8000/api/v1/public/profiles/ann");
    expect(init?.method).toBeUndefined();
    expect(init?.cache).toBe("no-store");
    expect(init?.body).toBeUndefined();
    expect(init?.signal).toBeInstanceOf(AbortSignal);
    expect(new Headers(init?.headers).has("Cookie")).toBe(false);
    expect(PUBLIC_PROFILE_TIMEOUT_MS).toBe(5000);
  });

  test("encodes the slug in the path", async () => {
    fetchMock.mockResolvedValue(Response.json(PROFILE));

    await getPublicProfile("a/../b?c#d");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://backend.internal:8000/api/v1/public/profiles/a%2F..%2Fb%3Fc%23d",
    );
  });

  test("drops fields outside the public whitelist", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...PROFILE, email: "ann@example.com", status: "PUBLISHED", id: "1" }),
    );

    const profile = await getPublicProfile("ann");

    expect(profile).toEqual(PROFILE);
    expect(Object.keys(profile!).sort()).toEqual(Object.keys(PROFILE).sort());
  });

  test("404 returns null", async () => {
    fetchMock.mockResolvedValue(errorResponse(404, "NOT_FOUND"));
    await expect(getPublicProfile("ann")).resolves.toBeNull();
  });

  test("5xx throws ApiError", async () => {
    fetchMock.mockResolvedValue(errorResponse(500, "INTERNAL_ERROR"));
    await expect(getPublicProfile("ann")).rejects.toMatchObject({
      constructor: ApiError,
      status: 500,
      code: "INTERNAL_ERROR",
    });
  });

  test("a network failure throws NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    await expect(getPublicProfile("ann")).rejects.toBeInstanceOf(NetworkError);
  });

  test("a slow API is cut off by the timeout as NetworkError", async () => {
    fetchMock.mockImplementation(
      (_url, init) =>
        new Promise((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
        }),
    );

    await expect(getPublicProfile("ann", { timeoutMs: 10 })).rejects.toBeInstanceOf(NetworkError);
  });

  test.each([
    ["not JSON", new Response("<html>", { status: 200 })],
    ["an array", Response.json([PROFILE])],
    ["no github_login", Response.json({ ...PROFILE, github_login: undefined })],
    ["a number for bio", Response.json({ ...PROFILE, bio: 5 })],
    ["an empty body", new Response(null, { status: 200 })],
  ])("an unexpected body (%s) throws ApiError", async (_name, response) => {
    fetchMock.mockResolvedValue(response);
    await expect(getPublicProfile("ann")).rejects.toBeInstanceOf(ApiError);
  });
});
