// @vitest-environment node
// Server-side call: no window, so the client uses API_INTERNAL_URL.

import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import { getPublicProject } from "./public-profile";

const fetchMock = vi.fn<typeof fetch>();

const ID = "11111111-1111-4111-8111-111111111111";

const SHOT = {
  url: `/media/projects/${ID}/22222222-2222-4222-8222-222222222222.webp`,
  caption: "Корзина",
  width: 1280,
  height: 800,
};

const PAGE = {
  id: ID,
  title: "Shop",
  summary: "Payments",
  description: "Long text",
  problem: "Slow checkout",
  results: "Faster",
  role: "Backend",
  contribution: "The payment flow",
  technologies: ["Python", "FastAPI"],
  demo_url: "https://demo.example.com/shop",
  screenshots: [SHOT],
  github: null,
  owner: { slug: "ann", display_name: "Ann Lee", avatar_url: null },
};

const GITHUB = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: null,
  languages: [],
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  synced_at: "2026-11-01T00:00:00Z",
};

let warn: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.stubEnv("API_INTERNAL_URL", "http://backend.internal:8000");
  vi.stubGlobal("fetch", fetchMock);
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  warn.mockRestore();
});

function load(body: Record<string, unknown>) {
  fetchMock.mockResolvedValueOnce(Response.json({ ...PAGE, ...body }));
  return getPublicProject("ann", ID);
}

function errorResponse(status: number, code: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: "r-1" } },
    { status },
  );
}

describe("getPublicProject", () => {
  test("GET via API_INTERNAL_URL, not cached, with a timeout signal", async () => {
    await load({});

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://backend.internal:8000/api/v1/public/profiles/ann/projects/${ID}`);
    expect(init?.cache).toBe("no-store");
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  test("encodes the slug and the id in the path", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, "NOT_FOUND"));
    await getPublicProject("a/b", "c?d");

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://backend.internal:8000/api/v1/public/profiles/a%2Fb/projects/c%3Fd",
    );
  });

  test("reads the whitelisted fields and drops the rest", async () => {
    const page = await load({
      status: "PUBLISHED",
      visibility: "PUBLIC",
      featured_position: 1,
      owner: { ...PAGE.owner, id: "u-1" },
      screenshots: [{ ...SHOT, id: "s-1", storage_key: "projects/x.webp" }],
    });

    expect(page).toEqual({
      id: ID,
      title: "Shop",
      summary: "Payments",
      description: "Long text",
      problem: "Slow checkout",
      results: "Faster",
      role: "Backend",
      contribution: "The payment flow",
      technologies: ["Python", "FastAPI"],
      demo_url: "https://demo.example.com/shop",
      screenshots: [SHOT],
      github: null,
      owner: { slug: "ann", display_name: "Ann Lee" },
    });
    expect(warn).not.toHaveBeenCalled();
  });

  test("the nullable texts and no screenshots are read", async () => {
    const page = await load({ description: null, problem: null, results: null, demo_url: null, screenshots: [] });

    expect(page).toMatchObject({ description: null, problem: null, results: null, demo_url: null, screenshots: [] });
    expect(warn).not.toHaveBeenCalled();
  });

  test("404 returns null", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, "NOT_FOUND"));
    await expect(getPublicProject("ann", ID)).resolves.toBeNull();
  });

  test("5xx throws ApiError", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(500, "INTERNAL_ERROR"));
    await expect(getPublicProject("ann", ID)).rejects.toBeInstanceOf(ApiError);
  });

  test("a network failure throws NetworkError", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(getPublicProject("ann", ID)).rejects.toBeInstanceOf(NetworkError);
  });

  test.each<[string, Record<string, unknown>]>([
    ["no contribution", { contribution: undefined }],
    ["a null role", { role: null }],
    ["a number problem", { problem: 1 }],
    ["a number technology", { technologies: [1] }],
    ["no technologies", { technologies: undefined }],
    ["a number demo_url", { demo_url: 5 }],
    ["screenshots as an object", { screenshots: {} }],
    ["no screenshots", { screenshots: undefined }],
    ["no owner", { owner: undefined }],
    ["an owner without display_name", { owner: { slug: "ann", display_name: null } }],
  ])("an unexpected body (%s) throws ApiError", async (_name, body) => {
    await expect(load(body)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("the demo link", () => {
  test.each(["http://demo.example.com", "HTTPS://Demo.example.com/a?b=1"])("%s is kept", async (url) => {
    await expect(load({ demo_url: url })).resolves.toMatchObject({ demo_url: url });
    expect(warn).not.toHaveBeenCalled();
  });

  test.each(["javascript:alert(1)", "ftp://demo.example.com", "not a url", "//demo.example.com"])(
    "%s is dropped with one log line without the value",
    async (url) => {
      await expect(load({ demo_url: url })).resolves.toMatchObject({ demo_url: null });
      expect(warn).toHaveBeenCalledTimes(1);
      expect(warn).toHaveBeenCalledWith(`Public project ${ID}: invalid field demo_url`);
    },
  );
});

describe("screenshots", () => {
  test("keep the API order and a null caption", async () => {
    const second = { ...SHOT, url: "/media/projects/a/b.webp", caption: null };
    await expect(load({ screenshots: [SHOT, second] })).resolves.toMatchObject({ screenshots: [SHOT, second] });
  });

  test.each<[string, Record<string, unknown>, string]>([
    ["a foreign url", { url: "https://evil.example.com/x.webp" }, "screenshots.url"],
    ["a protocol-relative url", { url: "//evil.example.com/media/x.webp" }, "screenshots.url"],
    ["a way out of /media/", { url: "/media/../api/v1/profile" }, "screenshots.url"],
    ["a number caption", { caption: 1 }, "screenshots.caption"],
    ["a zero width", { width: 0 }, "screenshots.width"],
    ["a width over 2560", { width: 2561 }, "screenshots.width"],
    ["a fractional height", { height: 1.5 }, "screenshots.height"],
    ["a string height", { height: "800" }, "screenshots.height"],
  ])("one with %s is dropped, the others stay", async (_name, change, field) => {
    const good = { ...SHOT, url: "/media/projects/a/good.webp" };
    const page = await load({ screenshots: [{ ...SHOT, ...change }, good] });

    expect(page?.screenshots).toEqual([good]);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(`Public project ${ID}: invalid field ${field}`);
  });

  test("a screenshot that is not an object is dropped", async () => {
    await expect(load({ screenshots: ["/media/x.webp"] })).resolves.toMatchObject({ screenshots: [] });
    expect(warn).toHaveBeenCalledWith(`Public project ${ID}: invalid field screenshots`);
  });
});

describe("github", () => {
  test("is read through the card reader", async () => {
    await expect(load({ github: GITHUB })).resolves.toMatchObject({ github: GITHUB });
    expect(warn).not.toHaveBeenCalled();
  });

  test("a wrong one hides only the block, with one log line", async () => {
    const page = await load({ github: { ...GITHUB, relation: "BOSS" } });

    expect(page).toMatchObject({ github: null, title: "Shop" });
    expect(warn).toHaveBeenCalledWith(`Public project ${ID}: invalid field github.relation`);
  });
});
