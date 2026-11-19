// @vitest-environment node
// Server components: rendered to static HTML, as a visitor without JS gets them.

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api";

import PublicProjectRoute, { generateMetadata } from "./page";

const navigation = vi.hoisted(() => ({
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
  permanentRedirect: vi.fn((url: string) => {
    throw new Error(`NEXT_REDIRECT ${url}`);
  }),
}));
vi.mock("next/navigation", () => navigation);

// headers() identifies the request; a new object per test is a new request.
const request = vi.hoisted(() => ({ current: {} as object }));
vi.mock("next/headers", () => ({ headers: async () => request.current }));

const fetchMock = vi.fn<typeof fetch>();

const ID = "a1b2c3d4-1111-4111-8111-11111111aaaa";
const MEDIA = `/media/projects/${ID}`;

const SHOTS = [
  { url: `${MEDIA}/a.webp`, caption: "Главный экран", width: 1280, height: 800 },
  { url: `${MEDIA}/b.webp`, caption: null, width: 1024, height: 768 },
  { url: `${MEDIA}/c.webp`, caption: "Отчёт", width: 800, height: 600 },
];

const PAGE = {
  id: ID,
  title: "Shop",
  summary: "Payments",
  description: "Подробности",
  problem: "Медленная оплата",
  results: "Быстрее",
  role: "Backend",
  contribution: "Первая строка\nВторая строка",
  technologies: ["Python", "FastAPI", "PostgreSQL", "Celery"],
  demo_url: "https://demo.example.com/shop",
  screenshots: SHOTS,
  github: null,
  owner: { slug: "ann", display_name: "Ann Lee", avatar_url: null },
};

const GITHUB = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: "A small shop",
  languages: [{ name: "Python", bytes: 100 }],
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  synced_at: "2026-11-01T00:00:00Z",
};

beforeEach(() => {
  request.current = {};
  vi.stubEnv("API_INTERNAL_URL", "http://backend.internal:8000");
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://browser.test");
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  fetchMock.mockReset();
  navigation.notFound.mockClear();
  navigation.permanentRedirect.mockClear();
});

function props(slug: string, id = ID) {
  return { params: Promise.resolve({ slug, id }), searchParams: Promise.resolve({}) };
}

async function renderPage(page: Record<string, unknown> = {}) {
  fetchMock.mockResolvedValueOnce(Response.json({ ...PAGE, ...page }));
  return renderToStaticMarkup(await PublicProjectRoute(props("ann")));
}

function errorResponse(status: number, code: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: "r-1" } },
    { status },
  );
}

// The view itself is tested in project-view.test.tsx; these check that the reader's
// decisions reach the HTML.
describe("the rendered page", () => {
  test("shows the project with its demo, screenshots, texts and GitHub data", async () => {
    const html = await renderPage({ github: GITHUB });

    expect(html).toContain("Shop</h1>");
    expect(html).toContain('href="https://demo.example.com/shop"');
    expect(html).toContain(`src="http://browser.test${MEDIA}/c.webp"`);
    expect(html).toContain("Медленная оплата");
    expect(html).toContain("ann/shop");
  });

  test("a demo link that is not http or https is not rendered", async () => {
    const html = await renderPage({ demo_url: "javascript:alert(1)" });

    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("Открыть демо");
    expect(html).toContain(`src="http://browser.test${MEDIA}/a.webp"`);
  });

  test("a screenshot with a foreign url is not rendered", async () => {
    const html = await renderPage({
      screenshots: [{ ...SHOTS[0], url: "https://evil.example.com/x.webp" }, SHOTS[1]],
    });

    expect(html).not.toContain("evil.example.com");
    expect(html).toContain(`src="http://browser.test${MEDIA}/b.webp"`);
  });

  test("a wrong github object hides only its section", async () => {
    const html = await renderPage({ github: { ...GITHUB, relation: "BOSS" } });

    expect(html).not.toContain("Данные GitHub");
    expect(html).toContain("Открыть демо");
  });

  test("escapes the text", async () => {
    const html = await renderPage({ title: "<script>alert(1)</script>" });

    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
  });
});

describe("address and errors", () => {
  test.each([
    ["ann_lee", ID],
    ["a", ID],
    ["ann", "123"],
    ["ann", ID.replaceAll("-", "")],
    ["ann", `{${ID}}`],
    ["ann", `${ID}0`],
  ])("malformed %j / %j is a 404 without an API call", async (slug, id) => {
    await expect(PublicProjectRoute(props(slug, id))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("a valid address reaches the API", async () => {
    await renderPage();
    expect(fetchMock.mock.calls[0][0]).toBe(
      `http://backend.internal:8000/api/v1/public/profiles/ann/projects/${ID}`,
    );
  });

  test.each([
    ["Ann", ID],
    ["ann", ID.toUpperCase()],
    ["ANN", ID.toUpperCase()],
  ])("uppercase in %j / %j redirects once to the lowercase address", async (slug, id) => {
    await expect(PublicProjectRoute(props(slug, id))).rejects.toThrow(
      `NEXT_REDIRECT /u/ann/projects/${ID}`,
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("an uppercase malformed address is a 404, not a redirect", async () => {
    await expect(PublicProjectRoute(props("Ann_Lee"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.permanentRedirect).not.toHaveBeenCalled();
  });

  test("an API 404 calls notFound()", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, "NOT_FOUND"));

    await expect(PublicProjectRoute(props("ann"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.notFound).toHaveBeenCalledTimes(1);
  });

  test.each([
    ["a 500", () => errorResponse(500, "INTERNAL_ERROR")],
    ["an unexpected body", () => Response.json({ ...PAGE, contribution: null })],
  ])("%s throws to the error page, not notFound()", async (_name, response) => {
    fetchMock.mockResolvedValueOnce(response());

    await expect(PublicProjectRoute(props("ann"))).rejects.toBeInstanceOf(ApiError);
    expect(navigation.notFound).not.toHaveBeenCalled();
  });

  test("metadata and page share one API call per request, also after a failure", async () => {
    fetchMock.mockResolvedValue(errorResponse(500, "INTERNAL_ERROR"));

    await expect(PublicProjectRoute(props("ann"))).rejects.toBeInstanceOf(ApiError);
    await generateMetadata(props("ann"));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    request.current = {};
    await generateMetadata(props("ann"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("generateMetadata", () => {
  test("title is «title — owner», description the summary", async () => {
    fetchMock.mockResolvedValueOnce(Response.json(PAGE));

    await expect(generateMetadata(props("ann"))).resolves.toEqual({
      title: "Shop — Ann Lee",
      description: "Payments",
    });
  });

  test("a malformed address gives the neutral title without an API call", async () => {
    await expect(generateMetadata(props("ann", "x"))).resolves.toEqual({
      title: "Developer Profile Platform",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test.each([
    ["a 404", () => errorResponse(404, "NOT_FOUND")],
    ["a 500", () => errorResponse(500, "INTERNAL_ERROR")],
  ])("%s gives the neutral title", async (_name, response) => {
    fetchMock.mockResolvedValueOnce(response());

    await expect(generateMetadata(props("ann"))).resolves.toEqual({
      title: "Developer Profile Platform",
    });
  });
});
