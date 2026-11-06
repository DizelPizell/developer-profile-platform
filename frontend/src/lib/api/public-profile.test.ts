// @vitest-environment node
// Server-side call: no window, so the client uses API_INTERNAL_URL.

import { afterAll, afterEach, beforeEach, describe, expect, test, vi } from "vitest";

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

/** The fields the page keeps; the API also sends pushed_at. */
const GITHUB_READ = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: "A small shop",
  languages: [
    { name: "Python", bytes: 750 },
    { name: "Shell", bytes: 250 },
  ],
  is_fork: true,
  parent_full_name: "org/shop",
  is_archived: false,
  relation: "CONTRIBUTOR",
  synced_at: "2026-11-01T00:00:00Z",
};
const GITHUB = { ...GITHUB_READ, pushed_at: "2026-10-30T10:00:00Z" };

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

    expect(profile?.featured).toEqual([
      { ...first, github: null },
      { ...second, github: null },
    ]);
    expect(profile?.other).toEqual([{ ...PROJECT, id: "c", github: null }]);
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

    expect(profile?.featured).toEqual([{ ...PROJECT, github: null, position: 1 }]);
    expect(profile?.other).toEqual([{ ...PROJECT, github: null }]);
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

describe("github on a public project", () => {
  const warn = vi.spyOn(console, "warn");

  beforeEach(() => {
    warn.mockReset();
    warn.mockImplementation(() => {});
  });

  afterAll(() => {
    warn.mockRestore();
  });

  function read(github: unknown) {
    fetchMock.mockResolvedValue(
      Response.json({ ...PROFILE, other: [{ ...PROJECT, github }] }),
    );
    return getPublicProfile("ann");
  }

  test("is read in featured and other, without a log", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        ...PROFILE,
        featured: [{ ...PROJECT, github: GITHUB, position: 1 }],
        other: [{ ...PROJECT, github: GITHUB }],
      }),
    );

    const profile = await getPublicProfile("ann");

    expect(profile?.featured[0].github).toEqual(GITHUB_READ);
    expect(profile?.other[0].github).toEqual(GITHUB_READ);
    expect(warn).not.toHaveBeenCalled();
  });

  test("the nullable fields and an empty language list are read", async () => {
    const github = { ...GITHUB, description: null, parent_full_name: null, languages: [] };

    const profile = await read(github);

    expect(profile?.other[0].github).toMatchObject({
      description: null,
      parent_full_name: null,
      languages: [],
    });
    expect(warn).not.toHaveBeenCalled();
  });

  test("pushed_at and unknown fields are not copied", async () => {
    const profile = await read({ ...GITHUB, github_repo_id: 7, stars: 100 });

    expect(Object.keys(profile?.other[0].github ?? {}).sort()).toEqual(
      Object.keys(GITHUB_READ).sort(),
    );
  });

  test("pushed_at is not read, so a wrong one changes nothing", async () => {
    const profile = await read({ ...GITHUB, pushed_at: 7 });

    expect(profile?.other[0].github).toEqual(GITHUB_READ);
    expect(warn).not.toHaveBeenCalled();
  });

  test("null is a card without the block and without a log", async () => {
    const profile = await read(null);

    expect(profile?.other[0].github).toBeNull();
    expect(warn).not.toHaveBeenCalled();
  });

  test("a missing field is a card without the block and without a log", async () => {
    fetchMock.mockResolvedValue(Response.json({ ...PROFILE, other: [PROJECT] }));

    const profile = await getPublicProfile("ann");

    expect(profile?.other[0].github).toBeNull();
    expect(warn).not.toHaveBeenCalled();
  });

  test.each<[string, unknown, string]>([
    ["a string", "ann/shop", "github"],
    ["a number", 7, "github"],
    ["a boolean", true, "github"],
    ["an array", [GITHUB], "github"],
    ["full_name of a wrong type", { ...GITHUB, full_name: 7 }, "github.full_name"],
    ["full_name missing", { ...GITHUB, full_name: undefined }, "github.full_name"],
    ["html_url null", { ...GITHUB, html_url: null }, "github.html_url"],
    ["description of a wrong type", { ...GITHUB, description: 7 }, "github.description"],
    ["languages not a list", { ...GITHUB, languages: "Python" }, "github.languages"],
    ["languages null", { ...GITHUB, languages: null }, "github.languages"],
    ["a language without a name", { ...GITHUB, languages: [{ bytes: 1 }] }, "github.languages"],
    [
      "a language with negative bytes",
      { ...GITHUB, languages: [{ name: "Python", bytes: -1 }] },
      "github.languages",
    ],
    [
      "a language with fractional bytes",
      { ...GITHUB, languages: [{ name: "Python", bytes: 1.5 }] },
      "github.languages",
    ],
    ["is_fork of a wrong type", { ...GITHUB, is_fork: "true" }, "github.is_fork"],
    ["parent of a wrong type", { ...GITHUB, parent_full_name: 7 }, "github.parent_full_name"],
    ["is_archived null", { ...GITHUB, is_archived: null }, "github.is_archived"],
    ["relation NONE", { ...GITHUB, relation: "NONE" }, "github.relation"],
    ["an unknown relation", { ...GITHUB, relation: "ADMIN" }, "github.relation"],
    ["synced_at null", { ...GITHUB, synced_at: null }, "github.synced_at"],
    ["synced_at not a date", { ...GITHUB, synced_at: "not-a-date" }, "github.synced_at"],
    ["synced_at impossible", { ...GITHUB, synced_at: "2026-13-45T00:00:00Z" }, "github.synced_at"],
    ["synced_at without an offset", { ...GITHUB, synced_at: "2026-11-01T00:00:00" }, "github.synced_at"],
    ["synced_at without a time", { ...GITHUB, synced_at: "2026-11-01" }, "github.synced_at"],
  ])("%s hides the block, keeps the card and logs the field", async (_, github, field) => {
    const profile = await read(github);

    expect(profile?.other[0]).toEqual({ ...PROJECT, github: null });
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(`Public project ${PROJECT.id}: invalid field ${field}`);
  });

  test("a date with an offset is a date", async () => {
    const profile = await read({ ...GITHUB, synced_at: "2026-11-01T03:00:00.123+03:00" });

    expect(profile?.other[0].github?.synced_at).toBe("2026-11-01T03:00:00.123+03:00");
    expect(warn).not.toHaveBeenCalled();
  });

  test("the log has no values", async () => {
    await read({ ...GITHUB, full_name: ["SECRET-NAME"], relation: "SECRET-RELATION" });

    expect(JSON.stringify(warn.mock.calls)).not.toContain("SECRET");
  });

  test("several wrong fields of a project are one line", async () => {
    await read({ ...GITHUB, full_name: 7, html_url: 7, relation: "NONE", synced_at: 7 });

    expect(warn).toHaveBeenCalledTimes(1);
  });

  test("one line per project, featured included; a good neighbour keeps its block", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        ...PROFILE,
        featured: [{ ...PROJECT, id: "a", github: "wrong", position: 1 }],
        other: [
          { ...PROJECT, id: "b", github: { ...GITHUB, relation: "NONE" } },
          { ...PROJECT, id: "c", github: GITHUB },
        ],
      }),
    );

    const profile = await getPublicProfile("ann");

    expect(warn.mock.calls).toEqual([
      ["Public project a: invalid field github"],
      ["Public project b: invalid field github.relation"],
    ]);
    expect(profile?.featured[0].github).toBeNull();
    expect(profile?.other[0].github).toBeNull();
    expect(profile?.other[1].github).toEqual(GITHUB_READ);
  });
});
