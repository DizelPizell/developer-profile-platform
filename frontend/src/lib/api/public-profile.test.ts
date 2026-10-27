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
  featured: [],
  other: [],
};

const PROJECT = {
  id: "11111111-1111-4111-8111-111111111111",
  title: "Shop",
  summary: "Payments",
  role: "Backend",
  technologies: ["Python", "FastAPI"],
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

  test("reads featured and other, sorts featured by position", async () => {
    const first = { ...PROJECT, id: "a", title: "First", position: 1 };
    const second = { ...PROJECT, id: "b", title: "Second", position: 2 };
    fetchMock.mockResolvedValue(
      Response.json({ ...PROFILE, featured: [second, first], other: [{ ...PROJECT, id: "c" }] }),
    );

    const profile = await getPublicProfile("ann");

    expect(profile?.featured).toEqual([first, second]);
    expect(profile?.other).toEqual([{ ...PROJECT, id: "c" }]);
  });

  test("drops project fields outside the whitelist", async () => {
    const extra = { status: "PUBLISHED", visibility: "PUBLIC", contribution: "secret" };
    fetchMock.mockResolvedValue(
      Response.json({
        ...PROFILE,
        featured: [{ ...PROJECT, ...extra, position: 1 }],
        other: [{ ...PROJECT, ...extra }],
      }),
    );

    const profile = await getPublicProfile("ann");

    expect(profile?.featured).toEqual([{ ...PROJECT, position: 1 }]);
    expect(profile?.other).toEqual([PROJECT]);
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
    ["no featured", Response.json({ ...PROFILE, featured: undefined })],
    ["no other", Response.json({ ...PROFILE, other: undefined })],
    ["featured as an object", Response.json({ ...PROFILE, featured: {} })],
    ["other as null", Response.json({ ...PROFILE, other: null })],
    ["a project without role", Response.json({ ...PROFILE, other: [{ ...PROJECT, role: undefined }] })],
    ["a null summary", Response.json({ ...PROFILE, other: [{ ...PROJECT, summary: null }] })],
    ["a number technology", Response.json({ ...PROFILE, other: [{ ...PROJECT, technologies: [1] }] })],
    ["a featured project without position", Response.json({ ...PROFILE, featured: [PROJECT] })],
    ["position 4", Response.json({ ...PROFILE, featured: [{ ...PROJECT, position: 4 }] })],
    ["position 1.5", Response.json({ ...PROFILE, featured: [{ ...PROJECT, position: 1.5 }] })],
    ["a string project", Response.json({ ...PROFILE, other: ["Shop"] })],
  ])("an unexpected body (%s) throws ApiError", async (_name, response) => {
    fetchMock.mockResolvedValue(response);
    await expect(getPublicProfile("ann")).rejects.toBeInstanceOf(ApiError);
  });
});
