import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { GitHubSync, ProjectGitHub, ProjectResponse } from "@/lib/api";

import { ProjectEditScreen } from "./project-edit-screen";

// The sync state of the repository block (DESIGN.md, "Sync status, languages and
// «Обновить данные»"): the message, «Обновить данные» with its pause and errors.

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";
const ID = "p1";
const REPO_ID = 1296269;
const GET = `GET /projects/${ID}`;
const SYNC = `POST /integrations/github/repositories/${REPO_ID}/sync`;
const NOW = new Date("2026-11-01T12:00:00Z");
// Midday UTC: the same date in every time zone the tests may run in.
const SYNCED_AT = "2026-11-01T11:30:00Z";

const SYNC_STATE: Record<string, GitHubSync> = {
  NOT_SYNCED: { status: "NOT_SYNCED", last_success_at: null, next_manual_sync_at: null },
  QUEUED: { status: "QUEUED", last_success_at: null, next_manual_sync_at: null },
  SYNCED: { status: "SYNCED", last_success_at: SYNCED_AT, next_manual_sync_at: null },
};

const GITHUB: ProjectGitHub = {
  github_repo_id: REPO_ID,
  full_name: "octocat/Hello-World",
  html_url: "https://github.com/octocat/Hello-World",
  description: "My first repository",
  languages: [{ name: "Python", bytes: 100 }],
  pushed_at: "2026-10-30T12:00:00Z",
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  unavailable: false,
  synced_at: SYNCED_AT,
  sync: SYNC_STATE.SYNCED,
};

const PROJECT: ProjectResponse = {
  id: ID,
  status: "DRAFT",
  visibility: "PRIVATE",
  title: "Payments",
  summary: "Card payments",
  description: null,
  problem: null,
  results: null,
  role: null,
  contribution: null,
  technologies: ["Python"],
  featured_position: null,
  github: GITHUB,
};

const PROFILE = {
  slug: "ann",
  status: "PRIVATE",
  display_name: "Ann",
  headline: null,
  bio: null,
  location: null,
  avatar_url: null,
  github_login: "ann-gh",
};

function withGitHub(fields: Partial<ProjectGitHub>, sync: Partial<GitHubSync> = {}): ProjectResponse {
  return { ...PROJECT, github: { ...GITHUB, ...fields, sync: { ...GITHUB.sync, ...sync } } };
}

function apiError(status: number, code: string, details = {}) {
  return Response.json({ error: { code, message: code, details, request_id: "r-7" } }, { status });
}

type Reply = Response | Promise<Response> | (() => Response | Promise<Response>);

/** Answers by "METHOD /path", in order, repeating the last reply. */
function routes(table: Record<string, Reply[]>) {
  const queues = new Map(Object.entries(table).map(([key, replies]) => [key, [...replies]]));
  fetchMock.mockImplementation(async (url, init) => {
    const key = `${init?.method ?? "GET"} ${String(url).replace(API, "")}`;
    const queue = queues.get(key);
    if (!queue) {
      throw new Error(`unexpected request ${key}`);
    }
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    const response = await (typeof reply === "function" ? reply() : reply);
    return response.clone();
  });
}

function calls(key: string) {
  return fetchMock.mock.calls.filter(
    ([url, init]) => `${init?.method ?? "GET"} ${String(url).replace(API, "")}` === key,
  );
}

function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  replace.mockReset();
});

/** The clock is faked before the render, so the pause starts from NOW. */
function fakeClock() {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(NOW);
}

function tick(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

async function renderEdit(project: ProjectResponse, extra: Record<string, Reply[]> = {}) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    [GET]: [Response.json(project)],
    ...extra,
  });
  const view = render(<ProjectEditScreen projectId={ID} />);
  await screen.findByRole("form", { name: "Проект" });
  return view;
}

const block = () => screen.getByRole("region", { name: "Репозиторий GitHub" });
const panel = () => screen.getByRole("group", { name: "Привязанный репозиторий" });
const status = () => within(panel()).getByRole("status");
const button = (name: string | RegExp, scope: HTMLElement = document.body) =>
  within(scope).getByRole<HTMLButtonElement>("button", { name });
const syncButton = () => button(/^Обновить|^Ставим/, block());
const title = () => screen.getByRole<HTMLInputElement>("textbox", { name: /Название/ });

/** «01.11.2026, HH:MM», the time read without Intl in the local zone. */
function shownAt(iso: string) {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `01.11.2026, ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

describe("the sync message", () => {
  test.each(["QUEUED", "SYNCING"] as const)(
    "%s: one message «Получаем данные с GitHub…», the button disabled",
    async (state) => {
      await renderEdit(withGitHub({}, { status: state }));
      expect(status().textContent).toBe("Получаем данные с GitHub…");
      expect(status().querySelector('[aria-hidden="true"]')).not.toBeNull();
      expect(syncButton().textContent).toBe("Обновить данные");
      expect(syncButton().disabled).toBe(true);
    },
  );

  test("NOT_SYNCED says so, with the placeholder and an active button", async () => {
    await renderEdit(withGitHub({ synced_at: null, languages: [] }, SYNC_STATE.NOT_SYNCED));
    expect(status().textContent).toBe("Ещё не синхронизирован с GitHub.");
    expect(status().querySelector('[aria-hidden="true"]')).toBeNull();
    expect(within(panel()).getByText(/появятся после первой синхронизации/)).toBeTruthy();
    expect(syncButton().disabled).toBe(false);
  });

  test("SYNCED has no message: the data date says it", async () => {
    await renderEdit(PROJECT);
    expect(status().textContent).toBe("");
    expect(within(panel()).getByText(`Данные GitHub от ${shownAt(SYNCED_AT)}`)).toBeTruthy();
  });

  test("FAILED with data keeps the data and names its date", async () => {
    await renderEdit(withGitHub({}, { status: "FAILED" }));
    expect(status().textContent).toBe(
      `Не удалось обновить данные с GitHub. Показаны данные от ${shownAt(SYNCED_AT)}.`,
    );
    expect(within(panel()).getByText(`Данные GitHub от ${shownAt(SYNCED_AT)}`)).toBeTruthy();
    expect(within(panel()).getByRole("list", { name: "Языки" })).toBeTruthy();
    expect(syncButton().disabled).toBe(false);
  });

  test("FAILED without data asks to try later, with the placeholder", async () => {
    await renderEdit(
      withGitHub({ synced_at: null, languages: [] }, { status: "FAILED", last_success_at: null }),
    );
    expect(status().textContent).toBe(
      "Не удалось получить данные с GitHub. Попробуйте обновить позже.",
    );
    expect(within(panel()).getByText(/появятся после первой синхронизации/)).toBeTruthy();
    expect(within(panel()).queryByText(/Данные GitHub от/)).toBeNull();
  });

  test.each([
    ["an unavailable repository", { unavailable: true }, /Репозиторий недоступен/],
    ["relation NONE", { relation: "NONE" as const }, /вы сейчас не владелец/],
  ])("%s shows its warning with the message, and can be synced", async (_name, fields, warning) => {
    await renderEdit(withGitHub(fields, { status: "FAILED" }));
    expect(status().textContent).toMatch(/^Не удалось обновить данные/);
    expect(within(panel()).getByText(warning)).toBeTruthy();
    expect(syncButton().disabled).toBe(false);
  });
});

describe("«Обновить данные»", () => {
  test("sends the sync, disables the form meanwhile, takes the answer and keeps edits", async () => {
    const answer = deferred();
    await renderEdit(PROJECT, { [SYNC]: [() => answer.promise] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });

    fireEvent.click(syncButton());

    expect(syncButton().textContent).toBe("Ставим в очередь…");
    expect(syncButton().disabled).toBe(true);
    expect(button("Сохранить").disabled).toBe(true);
    expect(button("Заменить репозиторий").disabled).toBe(true);
    expect(button("Отвязать").disabled).toBe(true);
    const [url, init] = calls(SYNC)[0];
    expect(String(url)).toBe(`${API}/integrations/github/repositories/${REPO_ID}/sync`);
    expect(init?.body).toBeUndefined();

    await act(async () => {
      answer.resolve(Response.json({ ...SYNC_STATE.QUEUED, last_success_at: SYNCED_AT }, { status: 202 }));
    });

    expect(status().textContent).toBe("Получаем данные с GitHub…");
    expect(syncButton().textContent).toBe("Обновить данные");
    expect(syncButton().disabled).toBe(true);
    expect(document.activeElement).toBe(panel());
    expect(title().value).toBe("Unsaved title");
    expect(button("Сохранить").disabled).toBe(false);
    expect(button("Заменить репозиторий").disabled).toBe(false);
  });

  test("a second click during the request sends nothing", async () => {
    const answer = deferred();
    await renderEdit(PROJECT, { [SYNC]: [() => answer.promise] });
    const first = syncButton();
    fireEvent.click(first);
    fireEvent.click(first);
    expect(calls(SYNC)).toHaveLength(1);
    await act(async () => {
      answer.resolve(Response.json(SYNC_STATE.QUEUED, { status: 202 }));
    });
  });

  test("the pause: «Обновить через N мин» with the hint, then active without a request", async () => {
    fakeClock();
    await renderEdit(withGitHub({}, { next_manual_sync_at: "2026-11-01T12:08:30Z" }));
    expect(syncButton().textContent).toBe("Обновить через 9 мин");
    expect(syncButton().disabled).toBe(true);
    expect(within(block()).getByText("Данные одного репозитория можно обновлять раз в 10 минут.")).toBeTruthy();
    expect(block().textContent).not.toMatch(/\bвы\b|\bвас\b/i);

    tick(509_000);
    expect(syncButton().textContent).toBe("Обновить через 1 мин");
    tick(1_000);
    expect(syncButton().textContent).toBe("Обновить данные");
    expect(syncButton().disabled).toBe(false);
    expect(within(block()).queryByText(/можно обновлять раз в 10 минут/)).toBeNull();
    expect(calls(SYNC)).toHaveLength(0);
  });

  test("a passed next_manual_sync_at is no pause", async () => {
    fakeClock();
    await renderEdit(withGitHub({}, { next_manual_sync_at: "2026-11-01T11:59:59Z" }));
    expect(syncButton().textContent).toBe("Обновить данные");
    expect(syncButton().disabled).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("a running job shows no pause, only the disabled button", async () => {
    fakeClock();
    await renderEdit(withGitHub({}, { status: "QUEUED", next_manual_sync_at: "2026-11-01T12:08:30Z" }));
    expect(syncButton().textContent).toBe("Обновить данные");
    expect(syncButton().disabled).toBe(true);
    expect(within(block()).queryByText(/можно обновлять раз в 10 минут/)).toBeNull();
  });

  test("429 GITHUB_SYNC_TOO_SOON counts down in the message, then «Повторить» closes it", async () => {
    await renderEdit(PROJECT, {
      [SYNC]: [apiError(429, "GITHUB_SYNC_TOO_SOON", { retry_after_seconds: 125 })],
    });
    fakeClock();
    fireEvent.click(syncButton());
    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Данные недавно обновлялись")).toBeTruthy();
    expect(alert.textContent).toContain(
      "Этот репозиторий недавно синхронизировался. Обновить можно через 3 мин.",
    );
    expect(alert.textContent).not.toMatch(/\bвы\b/i);
    expect(button("Повторить через 3 мин", alert).disabled).toBe(true);
    expect(syncButton().textContent).toBe("Обновить данные");
    expect(syncButton().disabled).toBe(true);

    tick(125_000);
    expect(syncButton().disabled).toBe(false);
    fireEvent.click(button("Повторить", alert));
    expect(within(block()).queryByRole("alert")).toBeNull();
    expect(calls(SYNC)).toHaveLength(1);
  });

  test("TOO_SOON without retry_after_seconds: «Попробуйте позже.» and no countdown", async () => {
    await renderEdit(PROJECT, { [SYNC]: [apiError(429, "GITHUB_SYNC_TOO_SOON")] });
    fireEvent.click(syncButton());
    const alert = await within(block()).findByRole("alert");
    expect(alert.textContent).toContain("Этот репозиторий недавно синхронизировался. Попробуйте позже.");
    expect(syncButton().disabled).toBe(false);
  });

  test("429 GITHUB_USER_LIMIT_REACHED counts down", async () => {
    await renderEdit(PROJECT, {
      [SYNC]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 60 })],
    });
    fakeClock();
    fireEvent.click(syncButton());
    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Слишком много обращений к GitHub")).toBeTruthy();
    expect(syncButton().disabled).toBe(true);
    tick(60_000);
    expect(syncButton().disabled).toBe(false);
  });

  test("404: the repository is no longer linked, the project is read once, no message", async () => {
    await renderEdit(PROJECT, { [SYNC]: [apiError(404, "NOT_FOUND")] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    routes({
      [SYNC]: [apiError(404, "NOT_FOUND")],
      [GET]: [Response.json({ ...PROJECT, title: "Server title", github: null })],
    });
    fireEvent.click(syncButton());
    expect(await screen.findByRole("textbox", { name: "Репозиторий GitHub" })).toBeTruthy();
    expect(calls(GET)).toHaveLength(2);
    expect(within(block()).queryByRole("alert")).toBeNull();
    expect(title().value).toBe("Unsaved title");
  });

  test("404, then the project's 404: «Проект не найден»", async () => {
    await renderEdit(PROJECT);
    routes({ [SYNC]: [apiError(404, "NOT_FOUND")], [GET]: [apiError(404, "NOT_FOUND")] });
    fireEvent.click(syncButton());
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
  });

  test("401 leaves for /login", async () => {
    await renderEdit(PROJECT, { [SYNC]: [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(syncButton());
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("500 shows the cabinet text with the request code; a network error its text", async () => {
    await renderEdit(PROJECT, { [SYNC]: [apiError(500, "INTERNAL_ERROR")] });
    fireEvent.click(syncButton());
    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Код запроса: r-7")).toBeTruthy();
    expect(syncButton().disabled).toBe(false);

    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fireEvent.click(syncButton());
    expect(await within(block()).findByText("Не удалось связаться с сервером.")).toBeTruthy();
  });
});
