import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, NetworkError } from "./errors";
import {
  archiveProject,
  createProject,
  deleteProject,
  featureProject,
  getProject,
  importRepository,
  linkRepository,
  listProjects,
  missingProjectFields,
  projectFieldErrors,
  publishProject,
  reorderFeatured,
  setProjectVisibility,
  unfeatureProject,
  unlinkRepository,
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
  github: null,
};
const github = {
  github_repo_id: 1296269,
  full_name: "octocat/Hello-World",
  html_url: "https://github.com/octocat/Hello-World",
  description: "My first repository",
  languages: [{ name: "Python", bytes: 1200 }],
  pushed_at: "2026-10-30T12:00:00Z",
  is_fork: true,
  parent_full_name: "github/Hello-World",
  is_archived: false,
  relation: "OWNER",
  unavailable: false,
  synced_at: null,
  sync: { status: "NOT_SYNCED", last_success_at: null, next_manual_sync_at: null },
};
const linked = { ...project, github };
const withoutGithub = Object.fromEntries(
  Object.entries(project).filter(([key]) => key !== "github"),
);
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
  [
    "linkRepository",
    () => linkRepository(ID, "octocat/Hello-World"),
    "POST",
    `${BASE}/projects/${ID}/repository`,
    { full_name: "octocat/Hello-World" },
    linked,
  ],
  [
    "unlinkRepository",
    () => unlinkRepository(ID),
    "DELETE",
    `${BASE}/projects/${ID}/repository`,
    undefined,
    project,
  ],
  [
    "importRepository",
    () => importRepository(1296269),
    "POST",
    `${BASE}/integrations/github/repositories/1296269/import`,
    undefined,
    linked,
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
  fetchMock.mockImplementation(async () => Response.json(project));
  await getProject("a/b?c");
  expect(lastCall().url).toBe(`${BASE}/projects/a%2Fb%3Fc`);
  await linkRepository("a/b?c", "octocat/x");
  expect(lastCall().url).toBe(`${BASE}/projects/a%2Fb%3Fc/repository`);
  await unlinkRepository("../x");
  expect(lastCall().url).toBe(`${BASE}/projects/..%2Fx/repository`);
});

test.each([0, -1, 1.5, Number.NaN, 2 ** 53])(
  "importRepository refuses id %s without a request",
  async (id) => {
    await expect(importRepository(id)).rejects.toBeInstanceOf(RangeError);
    expect(fetchMock).not.toHaveBeenCalled();
  },
);

describe("github in project responses", () => {
  test("a linked project keeps only the contract fields of github", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ ...project, github: { ...github, etag: "x", owner_id: 7 } }),
    );
    const result = await getProject(ID);
    expect(result.github).toEqual(github);
    expect(Object.keys(result.github!)).not.toContain("etag");
  });

  test.each([
    ["a missing github", withoutGithub],
    ["an unknown relation", { ...project, github: { ...github, relation: "MAINTAINER" } }],
    ["an unknown sync status", { ...project, github: { ...github, sync: { ...github.sync, status: "DONE" } } }],
    ["a string repository id", { ...project, github: { ...github, github_repo_id: "1296269" } }],
    ["an unsafe repository id", { ...project, github: { ...github, github_repo_id: 2 ** 53 } }],
    ["a malformed language", { ...project, github: { ...github, languages: [{ name: "Go" }] } }],
    ["github as a string", { ...project, github: "octocat/Hello-World" }],
    ["a body that is not an object", ["x"]],
  ])("%s is an unexpected body", async (_name, body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(getProject(ID)).rejects.toMatchObject({
      constructor: ApiError,
      code: "INVALID_RESPONSE",
    });
  });

  test("list items carry github: null or full_name and html_url only", async () => {
    const plain = { ...project, id: "p1" };
    const withRepo = {
      ...project,
      id: "p2",
      github: { full_name: "octocat/Hello-World", html_url: github.html_url, relation: "OWNER" },
    };
    fetchMock.mockResolvedValue(Response.json({ items: [withRepo, plain] }));

    const { items } = await listProjects();

    expect(items.map((item) => item.github)).toEqual([
      { full_name: "octocat/Hello-World", html_url: github.html_url },
      null,
    ]);
  });

  test.each([
    ["an item without github", { items: [withoutGithub] }],
    ["github without html_url", { items: [{ ...project, github: { full_name: "a/b" } }] }],
    ["items that are not an array", { items: {} }],
    ["no items", {}],
  ])("a list with %s is an unexpected body", async (_name, body) => {
    fetchMock.mockResolvedValue(Response.json(body));
    await expect(listProjects()).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
});

test("getProject and listProjects pass the abort signal", async () => {
  fetchMock.mockImplementation(async (url) =>
    Response.json(String(url).endsWith("/projects") ? { items: [] } : project),
  );
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
