import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { getMe, githubLoginUrl, logout } from "./auth";
import { ApiError, NetworkError } from "./errors";

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

const me = {
  id: "0b6c7c1e-5d1f-4b8e-9a51-1d2f3e4a5b6c",
  github_login: "ann",
  email: null,
  profile_slug: "ann",
};

describe("getMe", () => {
  test("GET /auth/me with credentials returns the user", async () => {
    fetchMock.mockResolvedValue(Response.json(me));

    await expect(getMe()).resolves.toEqual(me);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/auth/me");
    expect(init?.method).toBeUndefined();
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  test("401 becomes ApiError UNAUTHORIZED", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        {
          error: {
            code: "UNAUTHORIZED",
            message: "Authentication required",
            details: {},
            request_id: "r-1",
          },
        },
        { status: 401 },
      ),
    );

    await expect(getMe()).rejects.toMatchObject({
      constructor: ApiError,
      status: 401,
      code: "UNAUTHORIZED",
      requestId: "r-1",
    });
  });

  test("passes the abort signal", async () => {
    fetchMock.mockResolvedValue(Response.json(me));
    const controller = new AbortController();

    await getMe({ signal: controller.signal });

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });
});

describe("logout", () => {
  test("POST /auth/logout with credentials and no body; 204 resolves", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await expect(logout()).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/auth/logout");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });

  test("a 500 becomes ApiError with the request id", async () => {
    fetchMock.mockResolvedValue(
      Response.json(
        {
          error: {
            code: "INTERNAL_ERROR",
            message: "Internal server error",
            details: {},
            request_id: "r-2",
          },
        },
        { status: 500 },
      ),
    );

    await expect(logout()).rejects.toMatchObject({ code: "INTERNAL_ERROR", requestId: "r-2" });
  });

  test("a fetch failure becomes NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(logout()).rejects.toBeInstanceOf(NetworkError);
  });
});

test("githubLoginUrl points at the API sign-in endpoint", () => {
  expect(githubLoginUrl()).toBe("http://api.test/api/v1/auth/github/login");
});
