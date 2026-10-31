import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { ProjectGitHub, ProjectResponse } from "@/lib/api";

import { ProjectEditScreen } from "./project-edit-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";
const ID = "p1";
const LINK = `POST /projects/${ID}/repository`;
const UNLINK = `DELETE /projects/${ID}/repository`;

const GITHUB: ProjectGitHub = {
  github_repo_id: 1296269,
  full_name: "octocat/Hello-World",
  html_url: "https://github.com/octocat/Hello-World",
  description: "My first repository",
  languages: [],
  pushed_at: "2026-10-30T12:00:00Z",
  is_fork: true,
  parent_full_name: "github/Hello-World",
  is_archived: true,
  relation: "OWNER",
  unavailable: false,
  synced_at: null,
  sync: { status: "NOT_SYNCED", last_success_at: null, next_manual_sync_at: null },
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
  github: null,
};

const LINKED: ProjectResponse = { ...PROJECT, github: GITHUB };

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

const body = (key: string, index = 0) => JSON.parse(calls(key)[index][1]!.body as string);

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

async function renderEdit(project: ProjectResponse = PROJECT, extra: Record<string, Reply[]> = {}) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    [`GET /projects/${ID}`]: [Response.json(project)],
    ...extra,
  });
  const view = render(<ProjectEditScreen projectId={ID} />);
  await screen.findByRole("form", { name: "Проект" });
  return view;
}

const block = () => screen.getByRole("region", { name: "Репозиторий GitHub" });
const repoInput = () => screen.getByRole<HTMLInputElement>("textbox", { name: "Репозиторий GitHub" });
const button = (name: string, scope: HTMLElement = document.body) =>
  within(scope).getByRole<HTMLButtonElement>("button", { name });
const title = () => screen.getByRole<HTMLInputElement>("textbox", { name: /Название/ });
const panel = () => screen.getByRole("group", { name: "Привязанный репозиторий" });

function typeName(value: string) {
  fireEvent.change(repoInput(), { target: { value } });
}

describe("the block's states", () => {
  test("a new project shows only the hint to save first", async () => {
    routes({ "GET /profile": [Response.json(PROFILE)] });
    render(<ProjectEditScreen />);
    await screen.findByRole("form", { name: "Проект" });
    expect(within(block()).getByText("Репозиторий можно привязать после первого сохранения.")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Репозиторий GitHub" })).toBeNull();
    expect(within(block()).queryByRole("button")).toBeNull();
  });

  test("not linked: the text, the input, the list link and the note", async () => {
    await renderEdit();
    const region = block();
    expect(within(region).getByText("Источник: GitHub")).toBeTruthy();
    expect(within(region).getByText("Необязательно")).toBeTruthy();
    expect(within(region).getByText(/Привяжите репозиторий, и в проекте появятся факты из GitHub/)).toBeTruthy();
    expect(repoInput().placeholder).toBe("владелец/репозиторий");
    expect(button("Привязать", region).disabled).toBe(true);
    expect(within(region).getByRole("link", { name: "выберите из своего списка" }).getAttribute("href")).toBe(
      "/me/repositories",
    );
    expect(within(region).getByText(/Привязка и отвязка работают сразу и не зависят от кнопки «Сохранить»/)).toBeTruthy();
    expect(screen.getByText("Демо и скриншоты добавим в следующих версиях.")).toBeTruthy();
    expect(screen.queryByText(/репозиторий GitHub добавим/)).toBeNull();
  });

  test("linked: GitHub data only, the relation as a fact and the placeholder for languages", async () => {
    await renderEdit(LINKED);
    const linked = panel();
    const name = within(linked).getByRole("link", { name: "octocat/Hello-World" });
    expect(name.getAttribute("href")).toBe("https://github.com/octocat/Hello-World");
    expect(name.getAttribute("target")).toBe("_blank");
    expect(name.getAttribute("rel")).toBe("noopener noreferrer");
    expect(linked.textContent).toBe(
      "octocat/Hello-WorldОбновлён: 30.10.2026My first repository" +
        "Владелец репозиторияФорк github/Hello-WorldВ архиве на GitHub" +
        "Языки и другие данные появятся после первой синхронизации с GitHub. Сейчас данные ещё не загружены.",
    );
    expect(block().textContent).not.toMatch(/подтвержд|провер|верифиц/i);
    expect(button("Заменить репозиторий")).toBeTruthy();
    expect(button("Отвязать")).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Репозиторий GitHub" })).toBeNull();
  });

  test("a contributor, a fork without a parent, no date and no description", async () => {
    await renderEdit({
      ...PROJECT,
      github: {
        ...GITHUB,
        relation: "CONTRIBUTOR",
        parent_full_name: null,
        is_archived: false,
        pushed_at: null,
        description: null,
      },
    });
    const linked = panel();
    expect(within(linked).getByText("В списке контрибьюторов (по данным GitHub)")).toBeTruthy();
    expect(within(linked).getByText("Форк")).toBeTruthy();
    expect(within(linked).getByText("У этого репозитория нет описания на GitHub")).toBeTruthy();
    expect(within(linked).queryByText(/Обновлён/)).toBeNull();
    expect(within(linked).queryByText("В архиве на GitHub")).toBeNull();
  });

  test("relation NONE has no label, only its warning", async () => {
    await renderEdit({ ...PROJECT, github: { ...GITHUB, relation: "NONE" } });
    const linked = panel();
    expect(within(linked).queryByText("Владелец репозитория")).toBeNull();
    expect(within(linked).queryByText(/В списке контрибьюторов/)).toBeNull();
    expect(
      within(linked).getByText(/По данным GitHub вы сейчас не владелец репозитория и не в списке его контрибьюторов/),
    ).toBeTruthy();
    expect(within(linked).queryByText(/Репозиторий недоступен/)).toBeNull();
  });

  test("an unavailable repository shows its warning and the stored data", async () => {
    await renderEdit({ ...PROJECT, github: { ...GITHUB, unavailable: true } });
    const linked = panel();
    expect(
      within(linked).getByText(
        "Репозиторий недоступен: удалён или стал приватным. Публично данные GitHub не показываются.",
      ),
    ).toBeTruthy();
    expect(within(linked).getByText("My first repository")).toBeTruthy();
  });

  test("a synced repository has no placeholder", async () => {
    await renderEdit({ ...PROJECT, github: { ...GITHUB, synced_at: "2026-10-30T12:00:00Z" } });
    expect(within(panel()).queryByText(/появятся после первой синхронизации/)).toBeNull();
  });

  test("a non-GitHub URL is plain text, markup is text", async () => {
    await renderEdit({
      ...PROJECT,
      github: { ...GITHUB, html_url: "javascript:alert(1)", description: "<img src=x onerror=alert(1)>" },
    });
    const linked = panel();
    expect(within(linked).queryByRole("link")).toBeNull();
    expect(within(linked).getByText("<img src=x onerror=alert(1)>")).toBeTruthy();
    expect(linked.querySelector("img")).toBeNull();
  });
});

describe("link", () => {
  test("an invalid name shows the format hint without a request", async () => {
    await renderEdit();
    typeName("not a name");
    fireEvent.click(button("Привязать"));
    expect(within(block()).getByText("Формат: владелец/репозиторий.")).toBeTruthy();
    expect(repoInput().getAttribute("aria-invalid")).toBe("true");
    expect(calls(LINK)).toHaveLength(0);

    typeName("octocat/");
    expect(within(block()).queryByText("Формат: владелец/репозиторий.")).toBeNull();
    fireEvent.keyDown(repoInput(), { key: "Enter" });
    expect(within(block()).getByText("Формат: владелец/репозиторий.")).toBeTruthy();
    expect(calls(LINK)).toHaveLength(0);
  });

  test("a trimmed name is sent; unsaved edits and «Сохранить» stay; the panel takes the focus", async () => {
    await renderEdit(PROJECT, { [LINK]: [Response.json({ ...LINKED, title: "Server title" })] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    expect(button("Сохранить").disabled).toBe(false);

    typeName("  octocat/Hello-World  ");
    fireEvent.click(button("Привязать"));

    await waitFor(() => expect(panel()).toBeTruthy());
    expect(body(LINK)).toEqual({ full_name: "octocat/Hello-World" });
    expect(title().value).toBe("Unsaved title");
    expect(button("Сохранить").disabled).toBe(false);
    expect(calls(`PATCH /projects/${ID}`)).toHaveLength(0);
    expect(document.activeElement).toBe(panel());
  });

  test("Enter in the input links and does not submit the form", async () => {
    await renderEdit(PROJECT, { [LINK]: [Response.json(LINKED)] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    typeName("octocat/Hello-World");
    // jsdom does not submit a form on Enter; the browser does unless the key is cancelled.
    expect(fireEvent.keyDown(repoInput(), { key: "Enter" })).toBe(false);
    await waitFor(() => expect(panel()).toBeTruthy());
    expect(calls(LINK)).toHaveLength(1);
    expect(calls(`PATCH /projects/${ID}`)).toHaveLength(0);
  });

  test("the form is disabled while a link runs, and a double click sends once", async () => {
    const reply = deferred();
    await renderEdit(PROJECT, { [LINK]: [reply.promise] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    typeName("octocat/Hello-World");
    const target = button("Привязать");

    act(() => {
      target.click();
      target.click();
    });

    expect(calls(LINK)).toHaveLength(1);
    expect(button("Проверяем на GitHub…").disabled).toBe(true);
    expect(button("Сохранить").disabled).toBe(true);
    expect(repoInput().readOnly).toBe(true);
    await act(async () => reply.resolve(Response.json(LINKED)));
    expect(button("Сохранить").disabled).toBe(false);
  });

  test("a save in flight disables the block", async () => {
    const reply = deferred();
    await renderEdit(PROJECT, { [`PATCH /projects/${ID}`]: [reply.promise] });
    fireEvent.change(title(), { target: { value: "New" } });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Сохранить"));
    expect(button("Привязать").disabled).toBe(true);
    await act(async () => reply.resolve(Response.json({ ...PROJECT, title: "New" })));
    expect(button("Привязать").disabled).toBe(false);
  });

  test.each([
    [
      "GITHUB_REPOSITORY_NOT_FOUND",
      apiError(422, "GITHUB_REPOSITORY_NOT_FOUND"),
      "Репозиторий не найден",
      /Такого публичного репозитория нет. Проверьте написание/,
    ],
    [
      "GITHUB_RELATION_NOT_FOUND",
      apiError(422, "GITHUB_RELATION_NOT_FOUND"),
      "Связь с репозиторием не найдена",
      /Вы не владелец этого репозитория/,
    ],
    [
      "GITHUB_UNAVAILABLE",
      apiError(502, "GITHUB_UNAVAILABLE"),
      "GitHub сейчас недоступен",
      /Не получилось связаться с GitHub/,
    ],
  ])("%s shows its message in the block; the form keeps its edits", async (_code, reply, heading, text) => {
    await renderEdit(PROJECT, { [LINK]: [reply] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));

    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText(heading)).toBeTruthy();
    expect(within(alert).getByText(text)).toBeTruthy();
    expect(alert.textContent).not.toMatch(/GITHUB_/);
    expect(button("Привязать").disabled).toBe(false);
    expect(repoInput().value).toBe("octocat/Hello-World");
    expect(title().value).toBe("Unsaved title");
  });

  test("422 VALIDATION_ERROR from the API is the format hint", async () => {
    await renderEdit(PROJECT, { [LINK]: [apiError(422, "VALIDATION_ERROR")] });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    expect(await within(block()).findByText("Формат: владелец/репозиторий.")).toBeTruthy();
    expect(within(block()).queryByRole("alert")).toBeNull();
  });

  test("ALREADY_LINKED reads GET /projects to name the project and opens it", async () => {
    await renderEdit(PROJECT, {
      [LINK]: [apiError(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "p2" })],
      "GET /projects": [
        Response.json({
          items: [{ ...PROJECT, id: "p2", title: "Other", github: { full_name: "octocat/Hello-World", html_url: GITHUB.html_url } }],
        }),
      ],
    });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));

    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Репозиторий уже привязан")).toBeTruthy();
    expect(alert.textContent).toContain("уже привязан к вашему проекту «Other»");
    expect(within(alert).getByRole("link", { name: "Открыть проект" }).getAttribute("href")).toBe(
      "/me/projects/p2",
    );
    expect(calls("GET /projects")).toHaveLength(1);
  });

  test("ALREADY_LINKED without the project list says «к другому вашему проекту»", async () => {
    await renderEdit(PROJECT, {
      [LINK]: [apiError(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "p2" })],
      "GET /projects": [apiError(500, "INTERNAL_ERROR")],
    });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    const alert = await within(block()).findByRole("alert");
    expect(alert.textContent).toContain("уже привязан к другому вашему проекту.");
    expect(within(alert).getByRole("link", { name: "Открыть проект" })).toBeTruthy();
  });

  test("other errors read no project list", async () => {
    await renderEdit(PROJECT, { [LINK]: [apiError(422, "GITHUB_RELATION_NOT_FOUND")] });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    await within(block()).findByRole("alert");
    expect(calls("GET /projects")).toHaveLength(0);
  });

  test("502 «Повторить» sends the same name again, even after the input changed", async () => {
    await renderEdit(PROJECT, {
      [LINK]: [apiError(502, "GITHUB_UNAVAILABLE"), Response.json(LINKED)],
    });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    await within(block()).findByText("GitHub сейчас недоступен");
    await new Promise((resolve) => setTimeout(resolve, 30));
    expect(calls(LINK)).toHaveLength(1);

    typeName("someone/else");
    fireEvent.click(button("Повторить"));
    await waitFor(() => expect(panel()).toBeTruthy());
    expect(calls(LINK)).toHaveLength(2);
    expect(body(LINK, 1)).toEqual({ full_name: "octocat/Hello-World" });
  });

  test("INTERNAL_ERROR shows the request code", async () => {
    await renderEdit(PROJECT, { [LINK]: [apiError(500, "INTERNAL_ERROR")] });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Что-то пошло не так. Попробуйте ещё раз.")).toBeTruthy();
    expect(within(alert).getByText("Код запроса: r-7")).toBeTruthy();
  });

  test("the project's 404 shows «Проект не найден»", async () => {
    await renderEdit(PROJECT, { [LINK]: [apiError(404, "NOT_FOUND")] });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
  });

  test("401 leaves for /login", async () => {
    await renderEdit(PROJECT, { [LINK]: [apiError(401, "UNAUTHORIZED")] });
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("waiting (fake timers)", () => {
  function fakeClock() {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  }

  function tick(ms: number) {
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  }

  async function failLink(reply: Response) {
    await renderEdit(PROJECT, { [LINK]: [reply] });
    fakeClock();
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    return within(block()).findByRole("alert");
  }

  test("429 keeps «Привязать» disabled until the countdown ends, then «Повторить» closes it", async () => {
    const alert = await failLink(
      apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 125 }),
    );
    expect(within(alert).getByText("Слишком много обращений к GitHub")).toBeTruthy();
    expect(alert.textContent).toContain("Повторите через 3 мин.");
    expect(button("Повторить через 3 мин", alert).disabled).toBe(true);
    expect(button("Привязать").disabled).toBe(true);

    tick(124_000);
    expect(button("Привязать").disabled).toBe(true);
    fireEvent.keyDown(repoInput(), { key: "Enter" });
    expect(calls(LINK)).toHaveLength(1);

    tick(1_000);
    expect(button("Привязать").disabled).toBe(false);
    fireEvent.click(button("Повторить", alert));
    expect(within(block()).queryByRole("alert")).toBeNull();
    expect(calls(LINK)).toHaveLength(1);
  });

  test("503 GITHUB_RATE_LIMITED: 30 seconds is «1 мин»", async () => {
    const alert = await failLink(apiError(503, "GITHUB_RATE_LIMITED", { retry_after_seconds: 30 }));
    expect(alert.textContent).toContain("Это не ваша вина: лимит общий на всех. Попробуйте через 1 мин.");
    expect(button("Привязать").disabled).toBe(true);
    tick(30_000);
    expect(button("Привязать").disabled).toBe(false);
  });

  test("without retry_after_seconds there is no countdown", async () => {
    const alert = await failLink(apiError(429, "GITHUB_USER_LIMIT_REACHED"));
    expect(alert.textContent).toContain("Попробуйте позже.");
    expect(alert.textContent).not.toMatch(/через/);
    expect(button("Привязать").disabled).toBe(false);
    expect(vi.getTimerCount()).toBe(0);
  });

  test("the countdown timer is cleared when the form unmounts", async () => {
    const view = await renderEdit(PROJECT, {
      [LINK]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 600 })],
    });
    fakeClock();
    typeName("octocat/Hello-World");
    fireEvent.click(button("Привязать"));
    await within(block()).findByRole("alert");
    expect(vi.getTimerCount()).toBe(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("replace and unlink", () => {
  test("«Заменить репозиторий» shows the input with «Отмена»; a link replaces the panel", async () => {
    const other = { ...GITHUB, github_repo_id: 2, full_name: "ann/other", html_url: "https://github.com/ann/other" };
    await renderEdit(LINKED, { [LINK]: [Response.json({ ...PROJECT, github: other })] });
    fireEvent.click(button("Заменить репозиторий"));
    expect(document.activeElement).toBe(repoInput());
    expect(button("Отмена", block())).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Отвязать" })).toBeNull();

    fireEvent.click(button("Отмена", block()));
    expect(screen.queryByRole("textbox", { name: "Репозиторий GitHub" })).toBeNull();
    expect(button("Отвязать")).toBeTruthy();

    fireEvent.click(button("Заменить репозиторий"));
    typeName("ann/other");
    fireEvent.click(button("Привязать"));
    await waitFor(() => expect(within(panel()).getByRole("link", { name: "ann/other" })).toBeTruthy());
    expect(body(LINK)).toEqual({ full_name: "ann/other" });
    expect(screen.queryByRole("textbox", { name: "Репозиторий GitHub" })).toBeNull();
  });

  test("«Отвязать» asks first with the focus on «Отмена»; Escape and «Отмена» send nothing", async () => {
    await renderEdit(LINKED);
    fireEvent.click(button("Отвязать"));
    let dialog = await screen.findByRole("alertdialog", { name: "Отвязать репозиторий?" });
    expect(dialog.textContent).toContain(
      "Проект и его тексты останутся. Пропадёт только связь с octocat/Hello-World. Привязать можно снова.",
    );
    await waitFor(() => expect(document.activeElement).toBe(button("Отмена", dialog)));
    fireEvent.keyDown(dialog, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());

    fireEvent.click(button("Отвязать"));
    dialog = await screen.findByRole("alertdialog");
    fireEvent.click(button("Отмена", dialog));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(calls(UNLINK)).toHaveLength(0);
    expect(panel()).toBeTruthy();
  });

  test("a confirmed unlink returns the input and keeps unsaved edits", async () => {
    await renderEdit(LINKED, { [UNLINK]: [Response.json({ ...PROJECT, title: "Server title" })] });
    fireEvent.change(title(), { target: { value: "Unsaved title" } });
    fireEvent.click(button("Отвязать"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(button("Отвязать", dialog));

    await waitFor(() => expect(repoInput()).toBeTruthy());
    expect(calls(UNLINK)).toHaveLength(1);
    expect(screen.queryByRole("group", { name: "Привязанный репозиторий" })).toBeNull();
    expect(title().value).toBe("Unsaved title");
    expect(button("Сохранить").disabled).toBe(false);
    await waitFor(() => expect(document.activeElement).toBe(repoInput()));
  });

  test("an unlink error shows the cabinet text with the request code; no countdown", async () => {
    await renderEdit(LINKED, { [UNLINK]: [apiError(500, "INTERNAL_ERROR")] });
    fireEvent.click(button("Отвязать"));
    fireEvent.click(button("Отвязать", await screen.findByRole("alertdialog")));
    const alert = await within(block()).findByRole("alert");
    expect(within(alert).getByText("Код запроса: r-7")).toBeTruthy();
    expect(within(alert).queryByRole("button")).toBeNull();
    expect(panel()).toBeTruthy();
    expect(button("Отвязать").disabled).toBe(false);
  });

  test("the project's 404 on unlink shows «Проект не найден»; 401 leaves", async () => {
    await renderEdit(LINKED, { [UNLINK]: [apiError(404, "NOT_FOUND")] });
    fireEvent.click(button("Отвязать"));
    fireEvent.click(button("Отвязать", await screen.findByRole("alertdialog")));
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
  });

  test("401 on unlink leaves for /login", async () => {
    await renderEdit(LINKED, { [UNLINK]: [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(button("Отвязать"));
    fireEvent.click(button("Отвязать", await screen.findByRole("alertdialog")));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
