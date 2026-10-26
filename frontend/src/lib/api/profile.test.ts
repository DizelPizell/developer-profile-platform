import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import {
  getProfile,
  missingProfileFields,
  profileFieldErrors,
  publishProfile,
  unpublishProfile,
  updateProfile,
} from "./profile";

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

const profile = {
  slug: "ann",
  status: "PRIVATE",
  display_name: "Ann",
  headline: null,
  bio: null,
  location: null,
  avatar_url: null,
  github_login: "ann",
};

function errorResponse(status: number, code: string, details: Record<string, unknown>) {
  return Response.json(
    { error: { code, message: code, details, request_id: "r-1" } },
    { status },
  );
}

describe("getProfile", () => {
  test("GET /profile with credentials returns the profile", async () => {
    fetchMock.mockResolvedValue(Response.json(profile));

    await expect(getProfile()).resolves.toEqual(profile);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/profile");
    expect(init?.method).toBeUndefined();
    expect(init?.credentials).toBe("include");
    expect(init?.body).toBeUndefined();
  });

  test("passes the abort signal", async () => {
    fetchMock.mockResolvedValue(Response.json(profile));
    const controller = new AbortController();

    await getProfile({ signal: controller.signal });

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  test("401 becomes ApiError UNAUTHORIZED", async () => {
    fetchMock.mockResolvedValue(errorResponse(401, "UNAUTHORIZED", {}));
    await expect(getProfile()).rejects.toMatchObject({ status: 401, code: "UNAUTHORIZED" });
  });
});

describe("updateProfile", () => {
  test("PATCH /profile sends exactly the given fields as JSON", async () => {
    fetchMock.mockResolvedValue(Response.json(profile));

    await expect(updateProfile({ display_name: "Ann", location: null })).resolves.toEqual(profile);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/profile");
    expect(init?.method).toBe("PATCH");
    expect(init?.credentials).toBe("include");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init?.body as string)).toEqual({ display_name: "Ann", location: null });
  });

  test("a 422 keeps the details for the form", async () => {
    const details = { fields: [{ loc: ["body", "headline"], type: "string_too_long" }] };
    fetchMock.mockResolvedValue(errorResponse(422, "VALIDATION_ERROR", details));

    await expect(updateProfile({ headline: "x" })).rejects.toMatchObject({
      constructor: ApiError,
      status: 422,
      code: "VALIDATION_ERROR",
      details,
      requestId: "r-1",
    });
  });

  test("a fetch failure becomes NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(updateProfile({ bio: "x" })).rejects.toBeInstanceOf(NetworkError);
  });
});

describe.each([
  ["publishProfile", publishProfile, "http://api.test/api/v1/profile/publish"],
  ["unpublishProfile", unpublishProfile, "http://api.test/api/v1/profile/unpublish"],
])("%s", (_name, call, expectedUrl) => {
  test("POST with credentials and no body returns the profile", async () => {
    fetchMock.mockResolvedValue(Response.json(profile));

    await expect(call()).resolves.toEqual(profile);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(expectedUrl);
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
  });
});

test("publishProfile turns PROFILE_INCOMPLETE into ApiError with missing_fields", async () => {
  fetchMock.mockResolvedValue(
    errorResponse(422, "PROFILE_INCOMPLETE", { missing_fields: ["display_name", "headline"] }),
  );

  await expect(publishProfile()).rejects.toMatchObject({
    code: "PROFILE_INCOMPLETE",
    details: { missing_fields: ["display_name", "headline"] },
  });
});

function apiError(code: string, details: Record<string, unknown>) {
  return new ApiError({ status: 422, code, message: code, details, requestId: null });
}

describe("missingProfileFields", () => {
  test("returns the known fields in form order", () => {
    const error = apiError("PROFILE_INCOMPLETE", {
      missing_fields: ["headline", "unknown", "display_name"],
    });
    expect(missingProfileFields(error)).toEqual(["display_name", "headline"]);
  });

  test.each([
    ["another code", apiError("VALIDATION_ERROR", { missing_fields: ["headline"] })],
    ["malformed details", apiError("PROFILE_INCOMPLETE", { missing_fields: "headline" })],
    ["a network error", new NetworkError(new TypeError("x"))],
  ])("is empty for %s", (_name, error) => {
    expect(missingProfileFields(error)).toEqual([]);
  });
});

describe("profileFieldErrors", () => {
  test("maps body fields to their first error type", () => {
    const error = apiError("VALIDATION_ERROR", {
      fields: [
        { loc: ["body", "display_name"], type: "string_too_long" },
        { loc: ["body", "display_name"], type: "control_characters" },
        { loc: ["body", "bio"], type: "control_characters" },
        { loc: ["body", "slug"], type: "extra_forbidden" },
        { loc: ["query", "headline"], type: "missing" },
        { loc: ["body"], type: "json_invalid" },
        "garbage",
      ],
    });

    expect(profileFieldErrors(error)).toEqual({
      display_name: "string_too_long",
      bio: "control_characters",
    });
  });

  test.each([
    ["another code", apiError("PROFILE_INCOMPLETE", { fields: [] })],
    ["malformed details", apiError("VALIDATION_ERROR", { fields: {} })],
    ["a plain error", new Error("x")],
  ])("is empty for %s", (_name, error) => {
    expect(profileFieldErrors(error)).toEqual({});
  });
});
