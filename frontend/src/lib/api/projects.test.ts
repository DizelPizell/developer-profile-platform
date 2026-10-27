import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import {
  archiveProject,
  createProject,
  deleteProject,
  featureProject,
  getProject,
  listProjects,
  missingProjectFields,
  projectFieldErrors,
  publishProject,
  reorderFeatured,
  setProjectVisibility,
  unfeatureProject,
  updateProject,
} from "./projects";

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

const ID = "7481db67-f105-4bfe-a2a4-79390b58a16e";
const BASE = "http://api.test/api/v1";

const project = {
  id: ID,
  status: "DRAFT",
  visibility: "PRIVATE",
  title: "Payments",
  summary: null,
  description: null,
  problem: null,
  results: null,
  role: null,
  contribution: null,
  technologies: ["Python"],
  featured_position: null,
};
const featured = { items: [{ project_id: ID, position: 1 }] };

function errorResponse(status: number, code: string, details: Record<string, unknown> = {}) {
  return Response.json(
    { error: { code, message: code, details, request_id: "r-1" } },
    { status },
  );
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return {
    url,
    method: init?.method ?? "GET",
    credentials: init?.credentials,
    body: init?.body === undefined ? undefined : JSON.parse(init.body as string),
    contentType: new Headers(init?.headers).get("Content-Type"),
  };
}

describe.each([
  ["listProjects", () => listProjects(), "GET", `${BASE}/projects`, undefined, { items: [] }],
  ["getProject", () => getProject(ID), "GET", `${BASE}/projects/${ID}`, undefined, project],
  [
    "createProject",
    () => createProject({ title: "Payments", technologies: ["Python"] }),
    "POST",
    `${BASE}/projects`,
    { title: "Payments", technologies: ["Python"] },
    project,
  ],
  [
    "updateProject",
    () => updateProject(ID, { summary: null, technologies: ["Go", "Python"] }),
    "PATCH",
    `${BASE}/projects/${ID}`,
    { summary: null, technologies: ["Go", "Python"] },
    project,
  ],
  ["publishProject", () => publishProject(ID), "POST", `${BASE}/projects/${ID}/publish`, undefined, project],
  ["archiveProject", () => archiveProject(ID), "POST", `${BASE}/projects/${ID}/archive`, undefined, project],
  [
    "setProjectVisibility",
    () => setProjectVisibility(ID, "PRIVATE"),
    "POST",
    `${BASE}/projects/${ID}/visibility`,
    { visibility: "PRIVATE" },
    project,
  ],
  ["featureProject", () => featureProject(ID), "POST", `${BASE}/projects/${ID}/showcase`, undefined, featured],
  [
    "unfeatureProject",
    () => unfeatureProject(ID),
    "DELETE",
    `${BASE}/projects/${ID}/showcase`,
    undefined,
    featured,
  ],
  [
    "reorderFeatured",
    () => reorderFeatured(["b", "a"]),
    "POST",
    `${BASE}/profile/featured-projects/reorder`,
    { project_ids: ["b", "a"] },
    featured,
  ],
])("%s", (_name, call, method, url, body, response) => {
  test("sends the method, URL, body and credentials and returns the response", async () => {
    fetchMock.mockResolvedValue(Response.json(response));

    await expect(call()).resolves.toEqual(response);

    const sent = lastCall();
    expect(sent.url).toBe(url);
    expect(sent.method).toBe(method);
    expect(sent.credentials).toBe("include");
    expect(sent.body).toEqual(body);
    expect(sent.contentType).toBe(body === undefined ? null : "application/json");
  });

  test("an error response becomes ApiError with its code and request id", async () => {
    fetchMock.mockResolvedValue(errorResponse(409, "SOME_CONFLICT", { limit: 3 }));

    await expect(call()).rejects.toMatchObject({
      constructor: ApiError,
      status: 409,
      code: "SOME_CONFLICT",
      details: { limit: 3 },
      requestId: "r-1",
    });
  });

  test("a fetch failure becomes NetworkError", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(call()).rejects.toBeInstanceOf(NetworkError);
  });
});

test("deleteProject sends DELETE and resolves on 204", async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

  await expect(deleteProject(ID)).resolves.toBeUndefined();

  const sent = lastCall();
  expect(sent.url).toBe(`${BASE}/projects/${ID}`);
  expect(sent.method).toBe("DELETE");
  expect(sent.credentials).toBe("include");
  expect(sent.body).toBeUndefined();
});

test("ids are encoded into the path", async () => {
  fetchMock.mockResolvedValue(Response.json(project));
  await getProject("a/b?c");
  expect(lastCall().url).toBe(`${BASE}/projects/a%2Fb%3Fc`);
});

test("getProject and listProjects pass the abort signal", async () => {
  fetchMock.mockImplementation(async () => Response.json({ items: [] }));
  const controller = new AbortController();
  await listProjects({ signal: controller.signal });
  await getProject(ID, { signal: controller.signal });
  expect(fetchMock.mock.calls.map(([, init]) => init?.signal)).toEqual([
    controller.signal,
    controller.signal,
  ]);
});

function apiError(code: string, details: Record<string, unknown>) {
  return new ApiError({ status: 422, code, message: code, details, requestId: null });
}

describe("missingProjectFields", () => {
  test("returns the known fields in form order", () => {
    const error = apiError("PROJECT_INCOMPLETE", {
      missing_fields: ["technologies", "contribution", "unknown", "title"],
    });
    expect(missingProjectFields(error)).toEqual(["title", "technologies", "contribution"]);
  });

  test.each([
    ["another code", apiError("PROFILE_INCOMPLETE", { missing_fields: ["title"] })],
    ["malformed details", apiError("PROJECT_INCOMPLETE", { missing_fields: "title" })],
    ["a network error", new NetworkError(new TypeError("x"))],
  ])("is empty for %s", (_name, error) => {
    expect(missingProjectFields(error)).toEqual([]);
  });
});

describe("projectFieldErrors", () => {
  test("maps fields and single technologies to their first error", () => {
    const error = apiError("VALIDATION_ERROR", {
      fields: [
        { loc: ["body", "title"], type: "string_too_long" },
        { loc: ["body", "title"], type: "control_characters" },
        { loc: ["body", "technologies", 2], type: "string_too_long" },
        { loc: ["body", "technologies"], type: "duplicate_technology" },
        { loc: ["body", "status"], type: "extra_forbidden" },
        { loc: ["body", "summary", "x"], type: "weird" },
        { loc: ["query", "role"], type: "missing" },
        { loc: ["body"], type: "json_invalid" },
        "garbage",
      ],
    });

    expect(projectFieldErrors(error)).toEqual({
      title: { type: "string_too_long", item: false },
      technologies: { type: "string_too_long", item: true },
    });
  });

  test("a list error on technologies", () => {
    const error = apiError("VALIDATION_ERROR", {
      fields: [{ loc: ["body", "technologies"], type: "duplicate_technology" }],
    });
    expect(projectFieldErrors(error)).toEqual({
      technologies: { type: "duplicate_technology", item: false },
    });
  });

  test.each([
    ["another code", apiError("PROJECT_INCOMPLETE", { fields: [] })],
    ["malformed details", apiError("VALIDATION_ERROR", { fields: {} })],
    ["a plain error", new Error("x")],
  ])("is empty for %s", (_name, error) => {
    expect(projectFieldErrors(error)).toEqual({});
  });
});
