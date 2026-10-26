import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { apiFetch } from "./client";
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

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

async function rejection(promise: Promise<unknown>): Promise<unknown> {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("expected the promise to reject");
}

describe("success", () => {
  test("returns the parsed body and sends credentials", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, { github_login: "ann" }));

    await expect(apiFetch("/auth/me")).resolves.toEqual({ github_login: "ann" });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/auth/me");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  test("sends a JSON body with Content-Type", async () => {
    fetchMock.mockResolvedValue(jsonResponse(200, {}));

    await apiFetch("/profile", { method: "PATCH", json: { headline: "Backend" } });

    const [, init] = fetchMock.mock.calls[0];
    expect(init?.method).toBe("PATCH");
    expect(init?.body).toBe('{"headline":"Backend"}');
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
  });

  test("returns undefined for 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});

describe("API errors", () => {
  test("parses the shared error format", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: "PROFILE_INCOMPLETE",
          message: "Profile is missing fields required for publication",
          details: { missing_fields: ["headline"] },
          request_id: "3f1c2a9e-8f7b-4c1d-9a7e-2b6f0c4d5e61",
        },
      }),
    );

    const error = await rejection(apiFetch("/profile/publish", { method: "POST" }));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: "PROFILE_INCOMPLETE",
      details: { missing_fields: ["headline"] },
      requestId: "3f1c2a9e-8f7b-4c1d-9a7e-2b6f0c4d5e61",
    });
  });

  test("a body outside the format gives UNKNOWN_ERROR with the header request id", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>Bad Gateway</html>", {
        status: 502,
        headers: { "X-Request-ID": "header-id" },
      }),
    );

    const error = await rejection(apiFetch("/auth/me"));

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 502, code: "UNKNOWN_ERROR", requestId: "header-id" });
  });
});

describe("network errors", () => {
  test("a fetch TypeError becomes NetworkError, not ApiError", async () => {
    const cause = new TypeError("Failed to fetch");
    fetchMock.mockRejectedValue(cause);

    const error = await rejection(apiFetch("/profile", { method: "PATCH", json: {} }));

    expect(error).toBeInstanceOf(NetworkError);
    expect(error).not.toBeInstanceOf(ApiError);
    expect((error as NetworkError).cause).toBe(cause);
  });

  test("an aborted request is rethrown as is", async () => {
    const abort = new DOMException("aborted", "AbortError");
    fetchMock.mockRejectedValue(abort);

    await expect(apiFetch("/auth/me")).rejects.toBe(abort);
  });
});
