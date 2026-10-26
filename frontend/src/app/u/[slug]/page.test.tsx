// @vitest-environment node
// Server components: rendered to static HTML, as a visitor without JS gets them.

import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "@/lib/api";

import PublicProfilePage, { generateMetadata } from "./page";

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

const PROFILE = {
  slug: "ann",
  display_name: "Ann Lee",
  headline: "Backend-разработчик",
  bio: "Первая строка\nВторая строка",
  location: "Berlin",
  avatar_url: "https://avatars.githubusercontent.com/u/1",
  github_login: "ann-gh",
};

beforeEach(() => {
  request.current = {};
  vi.stubEnv("API_INTERNAL_URL", "http://backend.internal:8000");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  navigation.notFound.mockClear();
  navigation.permanentRedirect.mockClear();
});

function props(slug: string) {
  return { params: Promise.resolve({ slug }), searchParams: Promise.resolve({}) };
}

async function renderPage(profile: Record<string, unknown> = {}, slug = "ann") {
  fetchMock.mockResolvedValueOnce(Response.json({ ...PROFILE, ...profile }));
  return renderToStaticMarkup(await PublicProfilePage(props(slug)));
}

function errorResponse(status: number, code: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: "r-1" } },
    { status },
  );
}

describe("profile", () => {
  test("renders every public field on the server", async () => {
    const html = await renderPage({ email: "ann@example.com", status: "PUBLISHED" });

    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://backend.internal:8000/api/v1/public/profiles/ann",
    );
    expect(html).toContain("Ann Lee");
    expect(html).toContain("@ann-gh");
    expect(html).toContain("Класс");
    expect(html).toContain("Backend-разработчик");
    expect(html).toContain("Локация: Berlin");
    expect(html).toContain("О себе");
    expect(html).toContain("От автора");
    expect(html).toContain('src="https://avatars.githubusercontent.com/u/1"');
    expect(html.match(/Источник: GitHub/g)).toHaveLength(2);
    expect(html).toContain('href="/login"');
    expect(html).not.toContain("ann@example.com");
    expect(html).not.toContain("PUBLISHED");
  });

  test("the GitHub button opens the login on github.com without referrer or opener", async () => {
    const html = await renderPage();

    expect(html).toMatch(
      /<a href="https:\/\/github.com\/ann-gh" target="_blank" rel="noopener noreferrer"[^>]*>GitHub<\/a>/,
    );
  });

  test("empty location and bio are hidden", async () => {
    const html = await renderPage({ location: null, bio: null });

    expect(html).not.toContain("Локация");
    expect(html).not.toContain("О себе");
    expect(html).not.toContain("От автора");
  });

  test.each([
    ["http", "http://avatars.example/1.png"],
    ["javascript", "javascript:alert(1)"],
    ["null", null],
  ])("an avatar_url that is %s shows the pixel avatar", async (_name, avatarUrl) => {
    const html = await renderPage({ avatar_url: avatarUrl });

    expect(html).not.toContain("<img");
    expect(html).toContain('viewBox="0 0 16 16"');
  });

  test("markup in the fields is shown as text", async () => {
    const html = await renderPage({
      display_name: "<b>Ann</b>",
      headline: "<script>alert(1)</script>",
      bio: '<img src=x onerror="alert(1)"> **bold**',
      location: "<i>Berlin</i>",
    });

    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img src=x");
    expect(html).not.toContain("<b>Ann");
    expect(html).toContain("&lt;b&gt;Ann&lt;/b&gt;");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).toContain("&lt;img src=x onerror=&quot;alert(1)&quot;&gt; **bold**");
    expect(html).toContain("&lt;i&gt;Berlin&lt;/i&gt;");
  });

  test("line breaks in bio are kept", async () => {
    const html = await renderPage();

    expect(html).toMatch(/class="[^"]*whitespace-pre-line[^"]*">Первая строка\nВторая строка</);
  });
});

describe("slug and errors", () => {
  test.each(["a", "-ann", "ann-", "ann_lee", "a".repeat(40), "ann%2F..", ""])(
    "malformed slug %j is a 404 without an API call",
    async (slug) => {
      await expect(PublicProfilePage(props(slug))).rejects.toThrow("NEXT_NOT_FOUND");
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  test("an uppercase slug redirects to the lowercase address without an API call", async () => {
    await expect(PublicProfilePage(props("Ann-Lee"))).rejects.toThrow("NEXT_REDIRECT /u/ann-lee");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("an uppercase malformed slug is a 404, not a redirect", async () => {
    await expect(PublicProfilePage(props("Ann_Lee"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.permanentRedirect).not.toHaveBeenCalled();
  });

  test("an API 404 calls notFound()", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(404, "NOT_FOUND"));

    await expect(PublicProfilePage(props("ann"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(navigation.notFound).toHaveBeenCalledTimes(1);
  });

  test("an API 500 throws to the error page, not notFound()", async () => {
    fetchMock.mockResolvedValueOnce(errorResponse(500, "INTERNAL_ERROR"));

    await expect(PublicProfilePage(props("ann"))).rejects.toBeInstanceOf(ApiError);
    expect(navigation.notFound).not.toHaveBeenCalled();
  });

  test("metadata and page share one API call per request, also after a failure", async () => {
    fetchMock.mockResolvedValue(errorResponse(500, "INTERNAL_ERROR"));

    await expect(PublicProfilePage(props("ann"))).rejects.toBeInstanceOf(ApiError);
    await generateMetadata(props("ann"));
    await generateMetadata(props("ann"));

    expect(fetchMock).toHaveBeenCalledTimes(1);

    request.current = {};
    await generateMetadata(props("ann"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("generateMetadata", () => {
  test("title is «display_name — headline», description the headline", async () => {
    fetchMock.mockResolvedValueOnce(Response.json(PROFILE));

    await expect(generateMetadata(props("ann"))).resolves.toEqual({
      title: "Ann Lee — Backend-разработчик",
      description: "Backend-разработчик",
    });
  });

  test("a malformed slug gives the neutral title without an API call", async () => {
    await expect(generateMetadata(props("ann_lee"))).resolves.toEqual({
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

  test("a network failure gives the neutral title", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));

    await expect(generateMetadata(props("ann"))).resolves.toEqual({
      title: "Developer Profile Platform",
    });
  });
});
