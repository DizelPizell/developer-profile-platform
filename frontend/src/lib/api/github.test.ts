import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import {
  GITHUB_ERROR_CODES,
  githubErrorCode,
  isRepositoryFullName,
  linkedProjectId,
  listRepositories,
  projectLimit,
  retryAfterSeconds,
} from "./github";
import { importRepository, linkRepository } from "./projects";

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

const BASE = "http://api.test/api/v1";
const PROJECT_ID = "7481db67-f105-4bfe-a2a4-79390b58a16e";

const repository = {
  github_repo_id: 1296269,
  full_name: "octocat/Hello-World",
  html_url: "https://github.com/octocat/Hello-World",
  description: null,
  is_fork: false,
  is_archived: true,
  pushed_at: "2026-10-30T12:00:00Z",
  linked_project_id: PROJECT_ID,
};

function errorResponse(status: number, code: string, details: Record<string, unknown> = {}) {
  return Response.json(
    { error: { code, message: code, details, request_id: "r-1" } },
    { status },
  );
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url, method: init?.method ?? "GET", credentials: init?.credentials, init };
}

async function caught(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected a rejection");
}

describe("listRepositories", () => {
  test("sends GET with the page, credentials and the signal, and returns the page", async () => {
    fetchMock.mockResolvedValue(Response.json({ items: [repository], next_page: 3 }));
    const controller = new AbortController();

    await expect(listRepositories(2, { signal: controller.signal })).resolves.toEqual({
      items: [repository],
      next_page: 3,
    });

    const sent = lastCall();
    expect(sent.url).toBe(`${BASE}/integrations/github/repositories?page=2`);
    expect(sent.method).toBe("GET");
    expect(sent.credentials).toBe("include");
    expect(sent.init?.body).toBeUndefined();
    expect(sent.init?.signal).toBe(controller.signal);
  });

  test("an empty last page", async () => {
    fetchMock.mockResolvedValue(Response.json({ items: [], next_page: null }));
    await expect(listRepositories(1)).resolves.toEqual({ items: [], next_page: null });
  });

  test("unknown fields are dropped", async () => {
    fetchMock.mockResolvedValue(
      Response.json({
        items: [{ ...repository, owner: { id: 1 }, stargazers_count: 99 }],
        next_page: null,
        cached_at: "x",
      }),
    );

    const page = await listRepositories(1);

    expect(page).toEqual({ items: [repository], next_page: null });
    expect(Object.keys(page.items[0])).not.toContain("stargazers_count");
  });

  test.each([
    ["items missing", { next_page: null }],
    ["next_page missing", { items: [] }],
    ["next_page as a string", { items: [], next_page: "2" }],
    ["a string repository id", { items: [{ ...repository, github_repo_id: "1" }], next_page: null }],
    ["an unsafe repository id", { items: [{ ...repository, github_repo_id: 2 ** 53 }], next_page: null }],
    ["a missing flag", { items: [{ ...repository, is_fork: undefined }], next_page: null }],
    ["a numeric description", { items: [{ ...repository, description: 1 }], next_page: null }],
    ["a body that is an array", [repository]],
  ])("%s is an unexpected body", async (_name, body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(listRepositories(1)).rejects.toMatchObject({
      constructor: ApiError,
      code: "INVALID_RESPONSE",
    });
  });

  test.each([0, 101, 1.5, Number.NaN])("page %s is refused without a request", async (page) => {
    await expect(listRepositories(page)).rejects.toBeInstanceOf(RangeError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("a fetch failure becomes NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(listRepositories(1)).rejects.toBeInstanceOf(NetworkError);
  });
});

describe("error codes", () => {
  // Each endpoint the code can come from (API_CONTRACT.md, GitHub).
  const calls = {
    list: () => listRepositories(1),
    link: () => linkRepository(PROJECT_ID, "octocat/Hello-World"),
    import: () => importRepository(1296269),
  };
  test.each([
    [409, "GITHUB_LOGIN_OUTDATED", "list"],
    [422, "GITHUB_RELATION_NOT_FOUND", "link"],
    [422, "GITHUB_RELATION_NOT_FOUND", "import"],
    [422, "GITHUB_REPOSITORY_NOT_FOUND", "link"],
    [409, "GITHUB_REPOSITORY_ALREADY_LINKED", "link"],
    [409, "GITHUB_REPOSITORY_ALREADY_LINKED", "import"],
    [429, "GITHUB_USER_LIMIT_REACHED", "list"],
    [503, "GITHUB_RATE_LIMITED", "import"],
    [502, "GITHUB_UNAVAILABLE", "link"],
    [409, "PROJECT_LIMIT_REACHED", "import"],
    [422, "VALIDATION_ERROR", "link"],
    [404, "NOT_FOUND", "import"],
    [500, "INTERNAL_ERROR", "list"],
  ] as const)("%s %s from %s", async (status, code, call) => {
    fetchMock.mockResolvedValue(errorResponse(status, code));

    const error = await caught(calls[call]());

    expect(error).toMatchObject({ constructor: ApiError, status, code, requestId: "r-1" });
    expect(githubErrorCode(error)).toBe(code);
  });

  test("every listed code is covered above", () => {
    expect(GITHUB_ERROR_CODES).toHaveLength(11);
  });

  test("an unknown code is OTHER", async () => {
    fetchMock.mockResolvedValue(errorResponse(418, "SOMETHING_NEW"));
    const error = await caught(listRepositories(1));
    expect(error).toMatchObject({ code: "SOMETHING_NEW" });
    expect(githubErrorCode(error)).toBe("OTHER");
  });

  test.each([
    ["not JSON", new Response("<html>bad gateway</html>", { status: 502 })],
    ["JSON without error", Response.json({ detail: "x" }, { status: 502 })],
    ["error without a code", Response.json({ error: { message: "x" } }, { status: 502 })],
  ])("an error body that is %s is OTHER with the header request id", async (_name, response) => {
    response.headers.set("X-Request-ID", "hdr-1");
    fetchMock.mockResolvedValue(response);

    const error = await caught(listRepositories(1));

    expect(error).toMatchObject({ status: 502, code: "UNKNOWN_ERROR", requestId: "hdr-1" });
    expect(githubErrorCode(error)).toBe("OTHER");
    expect(retryAfterSeconds(error)).toBeNull();
  });

  test("a network error and a plain error are OTHER", () => {
    expect(githubErrorCode(new NetworkError(new TypeError("x")))).toBe("OTHER");
    expect(githubErrorCode(new Error("GITHUB_UNAVAILABLE"))).toBe("OTHER");
    expect(githubErrorCode(undefined)).toBe("OTHER");
  });
});

function apiError(code: string, details: Record<string, unknown>, status = 429) {
  return new ApiError({ status, code, message: code, details, requestId: null });
}

describe("retryAfterSeconds", () => {
  test.each(["GITHUB_USER_LIMIT_REACHED", "GITHUB_RATE_LIMITED"])(
    "is read from details of %s, not from the header",
    async (code) => {
      const response = errorResponse(code === "GITHUB_RATE_LIMITED" ? 503 : 429, code, {
        retry_after_seconds: 125,
      });
      response.headers.set("Retry-After", "999");
      fetchMock.mockResolvedValue(response);

      expect(retryAfterSeconds(await caught(listRepositories(1)))).toBe(125);
    },
  );

  test("zero is a valid wait", () => {
    expect(retryAfterSeconds(apiError("GITHUB_RATE_LIMITED", { retry_after_seconds: 0 }))).toBe(0);
  });

  test.each([
    ["missing", {}],
    ["negative", { retry_after_seconds: -5 }],
    ["a string", { retry_after_seconds: "60" }],
    ["a fraction", { retry_after_seconds: 1.5 }],
    ["null", { retry_after_seconds: null }],
  ])("is null when %s", (_name, details) => {
    expect(retryAfterSeconds(apiError("GITHUB_USER_LIMIT_REACHED", details))).toBeNull();
  });

  test("is null for other codes", () => {
    expect(retryAfterSeconds(apiError("GITHUB_SYNC_TOO_SOON", { retry_after_seconds: 60 }))).toBeNull();
    expect(retryAfterSeconds(apiError("GITHUB_UNAVAILABLE", { retry_after_seconds: 60 }))).toBeNull();
    expect(retryAfterSeconds(new NetworkError(new TypeError("x")))).toBeNull();
  });
});

describe("linkedProjectId", () => {
  test("is read from details of ALREADY_LINKED", async () => {
    fetchMock.mockResolvedValue(
      errorResponse(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: PROJECT_ID }),
    );
    expect(linkedProjectId(await caught(importRepository(1)))).toBe(PROJECT_ID);
  });

  test.each([
    ["missing", "GITHUB_REPOSITORY_ALREADY_LINKED", {}],
    ["empty", "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "" }],
    ["a number", "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: 5 }],
    ["another code", "PROJECT_LIMIT_REACHED", { project_id: PROJECT_ID }],
  ])("is null when %s", (_name, code, details) => {
    expect(linkedProjectId(apiError(code, details, 409))).toBeNull();
  });
});

describe("projectLimit", () => {
  test("is read from details of PROJECT_LIMIT_REACHED", () => {
    expect(projectLimit(apiError("PROJECT_LIMIT_REACHED", { limit: 50 }, 409))).toBe(50);
  });

  test.each([
    ["missing", "PROJECT_LIMIT_REACHED", {}],
    ["a string", "PROJECT_LIMIT_REACHED", { limit: "50" }],
    ["another code", "FEATURED_LIMIT_REACHED", { limit: 3 }],
  ])("is null when %s", (_name, code, details) => {
    expect(projectLimit(apiError(code, details, 409))).toBeNull();
  });
});

describe("isRepositoryFullName", () => {
  test.each([
    "octocat/Hello-World",
    "a/b",
    `${"a".repeat(39)}/repo`,
    "my-org/my.repo_name-2",
    `o/${"n".repeat(100)}`,
    "o/.github",
  ])("accepts %s", (value) => {
    expect(isRepositoryFullName(value)).toBe(true);
  });

  test.each([
    "",
    "octocat",
    "octocat/",
    "/repo",
    "a/b/c",
    `${"a".repeat(40)}/repo`,
    "-octocat/repo",
    "octocat-/repo",
    "octo_cat/repo",
    "o/.",
    "o/..",
    `o/${"n".repeat(101)}`,
    "o/re po",
    " octocat/repo",
    "https://github.com/octocat/repo",
  ])("refuses %j", (value) => {
    expect(isRepositoryFullName(value)).toBe(false);
  });
});
