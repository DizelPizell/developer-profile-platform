import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { parsePage } from "./page-param";
import { RepositoriesScreen } from "./repositories-screen";

const { push, replace, router } = vi.hoisted(() => {
  const push = vi.fn();
  const replace = vi.fn();
  return { push, replace, router: { push, replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";

type Repository = {
  github_repo_id: number;
  full_name: string;
  html_url: string;
  description: string | null;
  is_fork: boolean;
  is_archived: boolean;
  pushed_at: string | null;
  linked_project_id: string | null;
};

function repo(id: number, name: string, fields: Partial<Repository> = {}): Repository {
  return {
    github_repo_id: id,
    full_name: `ann/${name}`,
    html_url: `https://github.com/ann/${name}`,
    description: `${name} description`,
    is_fork: false,
    is_archived: false,
    pushed_at: "2026-10-30T12:00:00Z",
    linked_project_id: null,
    ...fields,
  };
}

type Summary = {
  id: string;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  visibility: "PUBLIC" | "PRIVATE";
  title: string | null;
  summary: string | null;
  technologies: string[];
  featured_position: number | null;
  github: { full_name: string; html_url: string } | null;
};

function summary(id: string, title: string | null, fields: Partial<Summary> = {}): Summary {
  return {
    id,
    status: "PUBLISHED",
    visibility: "PUBLIC",
    title,
    summary: null,
    technologies: [],
    featured_position: null,
    github: null,
    ...fields,
  };
}

const ONE = repo(101, "one");
const FORK = repo(102, "fork", { is_fork: true, description: null, pushed_at: null });
const ARCHIVED = repo(103, "archived", { is_archived: true });
const OLD = repo(104, "old", { linked_project_id: "b" });
const REPOS = [ONE, FORK, ARCHIVED, OLD];

const ALPHA = summary("a", "Alpha", { status: "DRAFT", visibility: "PRIVATE" });
const BETA = summary("b", "Beta", {
  github: { full_name: "ann/old", html_url: "https://github.com/ann/old" },
});
const PROJECTS = [ALPHA, BETA];

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

function listKey(page: number) {
  return `GET /integrations/github/repositories?page=${page}`;
}

function importKey(id: number) {
  return `POST /integrations/github/repositories/${id}/import`;
}

function linkKey(projectId: string) {
  return `POST /projects/${projectId}/repository`;
}

function page(items: Repository[], nextPage: number | null = null) {
  return Response.json({ items, next_page: nextPage });
}

function projectList(items: Summary[]) {
  return Response.json({ items });
}

function apiError(status: number, code: string, details = {}) {
  return Response.json({ error: { code, message: code, details, request_id: "r-9" } }, { status });
}

/** A ProjectResponse as link and import answer it. */
function projectResponse(project: Summary, repository: Repository) {
  return {
    ...project,
    description: null,
    problem: null,
    results: null,
    role: null,
    contribution: null,
    github: {
      github_repo_id: repository.github_repo_id,
      full_name: repository.full_name,
      html_url: repository.html_url,
      description: repository.description,
      languages: [],
      pushed_at: repository.pushed_at,
      is_fork: repository.is_fork,
      parent_full_name: null,
      is_archived: repository.is_archived,
      relation: "OWNER",
      unavailable: false,
      synced_at: null,
      sync: { status: "NOT_SYNCED", last_success_at: null, next_manual_sync_at: null },
    },
  };
}

type Reply = Response | Promise<Response> | (() => Response | Promise<Response>);

/**
 * Answers by "METHOD /path?query". Each route answers its replies in order and
 * then repeats the last one. Unknown routes fail the test.
 */
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

async function renderScreen(
  table: Record<string, Reply[]> = {},
  { pageNumber = 1, wait = true } = {},
) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    "GET /projects": [projectList(PROJECTS)],
    [listKey(pageNumber)]: [page(REPOS, 2)],
    ...table,
  });
  const view = render(<RepositoriesScreen page={pageNumber} />);
  if (wait) {
    await waitFor(() => expect(screen.queryByText("Загрузка…")).toBeNull());
  }
  return view;
}

function card(fullName: string) {
  // hidden: the page behind an open modal is aria-hidden.
  return screen.getByRole("heading", { name: fullName, hidden: true }).closest("li")!;
}

function button(name: string, within_: HTMLElement = document.body) {
  return within(within_).getByRole<HTMLButtonElement>("button", { name });
}

function importButton(fullName: string) {
  return within(card(fullName)).getByRole<HTMLButtonElement>("button", {
    name: /Импортировать как проект|Импортируем…/,
  });
}

function linkButton(fullName: string) {
  return button("Привязать к проекту…", card(fullName));
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
  push.mockReset();
  replace.mockReset();
});

describe("parsePage", () => {
  test.each([
    [undefined, 1],
    ["1", 1],
    ["2", 2],
    ["100", 100],
    ["101", 1],
    ["0", 1],
    ["-1", 1],
    ["02", 1],
    ["2.0", 1],
    ["1e1", 1],
    [" 2", 1],
    ["abc", 1],
    ["", 1],
    [["2", "3"], 1],
  ])("?page=%j is page %i", (value, expected) => {
    expect(parsePage(value)).toBe(expected);
  });
});

describe("the list", () => {
  test("shows the top panel, the source mark and «Назад к проектам»", async () => {
    await renderScreen();
    expect(screen.getByRole("heading", { level: 1, name: "Репозитории GitHub" })).toBeTruthy();
    expect(screen.getByText("Источник: GitHub", { selector: "main span" })).toBeTruthy();
    expect(
      screen.getByText(/Список обновляется раз в 5 минут: новый репозиторий появится не сразу/),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Назад к проектам" }).getAttribute("href")).toBe(
      "/me/projects",
    );
    expect(calls(listKey(1))).toHaveLength(1);
  });

  test("a card links the name to GitHub in a new tab with rel noopener noreferrer", async () => {
    await renderScreen();
    const link = within(card("ann/one")).getByRole("link", { name: "ann/one" });
    expect(link.getAttribute("href")).toBe("https://github.com/ann/one");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  test("a card shows only the name, the date, the description and its actions", async () => {
    await renderScreen();
    const one = card("ann/one");
    expect(within(one).getByText("Обновлён: 30.10.2026")).toBeTruthy();
    expect(within(one).getByText("one description")).toBeTruthy();
    expect(one.textContent).toBe(
      "ann/oneОбновлён: 30.10.2026one description" +
        "Импортировать как проектПривязать к проекту…" +
        "Импорт создаёт черновик с названием репозитория. Остальное вы заполняете сами.",
    );
  });

  test("fork and archive labels, the empty description text, no date for pushed_at null", async () => {
    await renderScreen();
    const fork = card("ann/fork");
    expect(within(fork).getByText("Форк")).toBeTruthy();
    expect(within(fork).getByText("У этого репозитория нет описания на GitHub")).toBeTruthy();
    expect(within(fork).queryByText(/Обновлён/)).toBeNull();
    expect(within(fork).queryByText("В архиве на GitHub")).toBeNull();

    const archived = card("ann/archived");
    expect(within(archived).getByText("В архиве на GitHub")).toBeTruthy();
    expect(within(archived).queryByText("Форк")).toBeNull();
    expect(within(card("ann/one")).queryByText("Форк")).toBeNull();
  });

  test("a name with a non-GitHub URL is plain text, and markup is shown as text", async () => {
    await renderScreen({
      [listKey(1)]: [
        page([
          repo(1, "odd", {
            html_url: "javascript:alert(1)",
            description: "<b>bold</b><img src=x onerror=alert(1)>",
          }),
        ]),
      ],
    });
    const odd = card("ann/odd");
    expect(within(odd).queryByRole("link")).toBeNull();
    expect(within(odd).getByText("<b>bold</b><img src=x onerror=alert(1)>")).toBeTruthy();
    expect(odd.querySelector("b, img")).toBeNull();
  });

  test("an unlinked card has import and link; a linked one has the badge and the project", async () => {
    await renderScreen();
    expect(within(card("ann/one")).queryByText("Привязан")).toBeNull();
    expect(importButton("ann/one")).toBeTruthy();
    expect(linkButton("ann/one")).toBeTruthy();

    const old = card("ann/old");
    expect(within(old).getByText("Привязан")).toBeTruthy();
    expect(old.textContent).toContain("Проект: Beta");
    expect(within(old).getByRole("link", { name: "Beta" }).getAttribute("href")).toBe(
      "/me/projects/b",
    );
    expect(within(old).queryAllByRole("button")).toHaveLength(0);
  });

  test("a linked project missing from GET /projects is a neutral link; null title is [Без названия]", async () => {
    await renderScreen({
      [listKey(1)]: [
        page([
          repo(1, "lost", { linked_project_id: "gone" }),
          repo(2, "untitled", { linked_project_id: "u" }),
        ]),
      ],
      "GET /projects": [projectList([summary("u", null)])],
    });
    const lost = card("ann/lost");
    expect(within(lost).getByText("Привязан")).toBeTruthy();
    expect(within(lost).getByRole("link", { name: "Открыть проект" }).getAttribute("href")).toBe(
      "/me/projects/gone",
    );
    expect(lost.textContent).not.toContain("Проект:");
    expect(within(card("ann/untitled")).getByRole("link", { name: "[Без названия]" })).toBeTruthy();
  });

  test("shows «Загрузка…» until both the projects and the list arrive", async () => {
    const list = deferred();
    await renderScreen({ [listKey(1)]: [list.promise] }, { wait: false });
    await waitFor(() => expect(calls("GET /projects")).toHaveLength(1));
    expect(screen.getByText("Загрузка…")).toBeTruthy();
    await act(async () => list.resolve(page(REPOS)));
    expect(screen.queryByText("Загрузка…")).toBeNull();
    expect(card("ann/one")).toBeTruthy();
  });

  test("an empty page 1 shows the panel with «Создать проект вручную» and no paging", async () => {
    await renderScreen({ [listKey(1)]: [page([])] });
    expect(screen.getByText(/На вашем аккаунте GitHub нет публичных репозиториев/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Создать проект вручную" }).getAttribute("href")).toBe(
      "/me/projects/new",
    );
    expect(screen.queryByRole("navigation", { name: "Страницы списка" })).toBeNull();
  });

  test("an empty later page says so and keeps «Назад»", async () => {
    await renderScreen({ [listKey(3)]: [page([])] }, { pageNumber: 3 });
    expect(screen.getByText("На этой странице репозиториев нет.")).toBeTruthy();
    expect(screen.queryByText(/На вашем аккаунте GitHub/)).toBeNull();
    expect(button("Назад").disabled).toBe(false);
    expect(button("Вперёд").disabled).toBe(true);
  });
});

describe("pagination", () => {
  test("page 1: «Назад» is disabled, «Вперёд» goes to next_page in the address", async () => {
    await renderScreen();
    expect(screen.getByText("Страница 1")).toBeTruthy();
    expect(button("Назад").disabled).toBe(true);
    expect(button("Вперёд").disabled).toBe(false);
    fireEvent.click(button("Вперёд"));
    expect(push).toHaveBeenCalledWith("/me/repositories?page=2");
  });

  test("the page comes from the prop; «Вперёд» is disabled when next_page is null", async () => {
    await renderScreen({ [listKey(2)]: [page([ONE], null)] }, { pageNumber: 2 });
    expect(calls(listKey(2))).toHaveLength(1);
    expect(screen.getByText("Страница 2")).toBeTruthy();
    expect(button("Вперёд").disabled).toBe(true);
    fireEvent.click(button("Назад"));
    expect(push).toHaveBeenCalledWith("/me/repositories?page=1");
  });

  test("«Вперёд» stays disabled past page 100", async () => {
    await renderScreen({ [listKey(100)]: [page([ONE], 101)] }, { pageNumber: 100 });
    expect(button("Вперёд").disabled).toBe(true);
  });

  test("a page change loads only the repository list", async () => {
    const view = await renderScreen({ [listKey(2)]: [page([ARCHIVED], null)] });
    view.rerender(<RepositoriesScreen page={2} />);
    await waitFor(() => expect(card("ann/archived")).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "ann/one" })).toBeNull();
    expect(calls(listKey(1))).toHaveLength(1);
    expect(calls(listKey(2))).toHaveLength(1);
    expect(calls("GET /projects")).toHaveLength(1);
    expect(calls("GET /profile")).toHaveLength(1);
  });
});

describe("import", () => {
  test("sends the repository's own id and moves to the form with the import marker", async () => {
    const reply = deferred();
    await renderScreen({ [importKey(103)]: [reply.promise] });

    fireEvent.click(importButton("ann/archived"));

    expect(calls(importKey(103))).toHaveLength(1);
    expect(calls(importKey(101))).toHaveLength(0);
    expect(importButton("ann/archived").textContent).toBe("Импортируем…");

    await act(async () =>
      reply.resolve(
        Response.json(projectResponse(summary("new-id", "archived", { status: "DRAFT", visibility: "PRIVATE" }), ARCHIVED), {
          status: 201,
        }),
      ),
    );

    expect(push).toHaveBeenCalledWith("/me/projects/new-id?imported=1");
    // Leaving: the button keeps waiting instead of becoming active again.
    expect(importButton("ann/archived").disabled).toBe(true);
  });

  test("every action is disabled while an import runs", async () => {
    const reply = deferred();
    await renderScreen({ [importKey(101)]: [reply.promise] });
    fireEvent.click(importButton("ann/one"));

    expect(importButton("ann/one").disabled).toBe(true);
    expect(importButton("ann/fork").disabled).toBe(true);
    expect(linkButton("ann/one").disabled).toBe(true);
    expect(linkButton("ann/fork").disabled).toBe(true);
    expect(button("Вперёд").disabled).toBe(true);

    await act(async () => reply.resolve(apiError(422, "GITHUB_RELATION_NOT_FOUND")));
    expect(importButton("ann/one").disabled).toBe(false);
    expect(button("Вперёд").disabled).toBe(false);
  });

  test("a double click sends one import", async () => {
    const reply = deferred();
    await renderScreen({ [importKey(101)]: [reply.promise] });
    const target = importButton("ann/one");

    // Both clicks reach the handler before React re-renders the disabled button.
    act(() => {
      target.click();
      target.click();
    });

    expect(calls(importKey(101))).toHaveLength(1);
    await act(async () => reply.resolve(apiError(422, "GITHUB_RELATION_NOT_FOUND")));
  });

  test("at 50 projects import is disabled with the limit text and sends nothing; link stays", async () => {
    const many = Array.from({ length: 50 }, (_, i) => summary(`p${i}`, `P${i}`));
    await renderScreen({ "GET /projects": [projectList(many)] });

    const target = importButton("ann/one");
    expect(target.disabled).toBe(true);
    expect(within(card("ann/one")).getByText("Можно создать не больше 50 проектов.")).toBeTruthy();
    expect(linkButton("ann/one").disabled).toBe(false);
    fireEvent.click(target);
    expect(calls(importKey(101))).toHaveLength(0);
  });

  test.each([
    [
      "GITHUB_RELATION_NOT_FOUND",
      apiError(422, "GITHUB_RELATION_NOT_FOUND"),
      "Связь с репозиторием не найдена",
      /Вы не владелец этого репозитория и не входите в список его контрибьюторов/,
    ],
    [
      "NOT_FOUND",
      apiError(404, "NOT_FOUND"),
      "Репозиторий не найден",
      /GitHub больше не отдаёт этот репозиторий: его могли удалить или сделать приватным/,
    ],
    [
      "PROJECT_LIMIT_REACHED",
      apiError(409, "PROJECT_LIMIT_REACHED", { limit: 50 }),
      "Достигнут лимит проектов",
      /У вас уже 50 проектов, это максимум/,
    ],
    [
      "GITHUB_UNAVAILABLE",
      apiError(502, "GITHUB_UNAVAILABLE"),
      "GitHub сейчас недоступен",
      /Не получилось связаться с GitHub/,
    ],
  ])("%s shows its message and the button is active again", async (_code, reply, title, text) => {
    await renderScreen({ [importKey(101)]: [reply] });
    fireEvent.click(importButton("ann/one"));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(title)).toBeTruthy();
    expect(within(alert).getByText(text)).toBeTruthy();
    expect(alert.textContent).not.toMatch(/GITHUB_|NOT_FOUND|PROJECT_LIMIT/);
    expect(importButton("ann/one").textContent).toBe("Импортировать как проект");
    expect(importButton("ann/one").disabled).toBe(false);
    expect(push).not.toHaveBeenCalled();
  });

  test("the import 404 text does not ask to check the spelling", async () => {
    await renderScreen({ [importKey(101)]: [apiError(404, "NOT_FOUND")] });
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).not.toMatch(/написание/);
  });

  test("PROJECT_LIMIT_REACHED leads to «Мои проекты»", async () => {
    await renderScreen({ [importKey(101)]: [apiError(409, "PROJECT_LIMIT_REACHED", { limit: 50 })] });
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("link", { name: "К моим проектам" }).getAttribute("href")).toBe(
      "/me/projects",
    );
  });

  test("ALREADY_LINKED names the project, opens it and marks the card linked", async () => {
    await renderScreen({
      [importKey(101)]: [apiError(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "a" })],
    });
    fireEvent.click(importButton("ann/one"));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Репозиторий уже привязан")).toBeTruthy();
    expect(alert.textContent).toContain("уже привязан к вашему проекту «Alpha»");
    expect(within(alert).getByRole("link", { name: "Открыть проект" }).getAttribute("href")).toBe(
      "/me/projects/a",
    );
    const one = card("ann/one");
    expect(within(one).getByText("Привязан")).toBeTruthy();
    expect(within(one).getByRole("link", { name: "Alpha" })).toBeTruthy();
    expect(within(one).queryByRole("button")).toBeNull();
  });

  test("ALREADY_LINKED to a project not in the list says «к другому вашему проекту»", async () => {
    await renderScreen({
      [importKey(101)]: [apiError(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "zz" })],
    });
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("уже привязан к другому вашему проекту.");
    expect(within(alert).getByRole("link", { name: "Открыть проект" }).getAttribute("href")).toBe(
      "/me/projects/zz",
    );
  });

  test("GITHUB_UNAVAILABLE «Повторить» repeats the same import once per click", async () => {
    await renderScreen({
      [importKey(102)]: [
        apiError(502, "GITHUB_UNAVAILABLE"),
        Response.json(projectResponse(summary("p-fork", "fork"), FORK), { status: 201 }),
      ],
    });
    fireEvent.click(importButton("ann/fork"));
    await screen.findByText("GitHub сейчас недоступен");
    expect(calls(importKey(102))).toHaveLength(1);

    fireEvent.click(button("Повторить"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/me/projects/p-fork?imported=1"));
    expect(calls(importKey(102))).toHaveLength(2);
    expect(calls(importKey(101))).toHaveLength(0);
  });

  test("INTERNAL_ERROR shows the generic text with the request code", async () => {
    await renderScreen({ [importKey(101)]: [apiError(500, "INTERNAL_ERROR")] });
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Что-то пошло не так. Попробуйте ещё раз.")).toBeTruthy();
    expect(within(alert).getByText("Код запроса: r-9")).toBeTruthy();
    expect(within(alert).queryByRole("button")).toBeNull();
  });

  test("a network failure shows the cabinet text", async () => {
    await renderScreen({
      [importKey(101)]: [
        () => {
          throw new TypeError("Failed to fetch");
        },
      ],
    });
    fireEvent.click(importButton("ann/one"));
    expect(await screen.findByText("Не удалось связаться с сервером.")).toBeTruthy();
  });

  test("401 leaves for /login", async () => {
    await renderScreen({ [importKey(101)]: [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(importButton("ann/one"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("waiting for GitHub (fake timers)", () => {
  function fakeClock() {
    // setTimeout stays real, so findBy/waitFor keep polling.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
  }

  function tick(ms: number) {
    act(() => {
      vi.advanceTimersByTime(ms);
    });
  }

  test("429 counts down in minutes and keeps import and link disabled until the end", async () => {
    await renderScreen({
      [importKey(101)]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 125 })],
    });
    fakeClock();
    fireEvent.click(importButton("ann/one"));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Слишком много обращений к GitHub")).toBeTruthy();
    expect(alert.textContent).toContain(
      "Вы много раз обращались к GitHub за последний час. Повторите через 3 мин.",
    );
    expect(button("Повторить через 3 мин", alert).disabled).toBe(true);
    expect(importButton("ann/one").disabled).toBe(true);
    expect(importButton("ann/fork").disabled).toBe(true);
    expect(linkButton("ann/fork").disabled).toBe(true);

    tick(65_000);
    expect(button("Повторить через 1 мин", alert).disabled).toBe(true);
    tick(59_000);
    expect(button("Повторить через 1 мин", alert).disabled).toBe(true);
    expect(importButton("ann/one").disabled).toBe(true);

    tick(1_000);
    expect(button("Повторить", alert).disabled).toBe(false);
    expect(importButton("ann/one").disabled).toBe(false);
    expect(linkButton("ann/fork").disabled).toBe(false);

    // For an action «Повторить» closes the message; the user repeats the action.
    fireEvent.click(button("Повторить", alert));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(calls(importKey(101))).toHaveLength(1);
  });

  test("503 GITHUB_RATE_LIMITED: 30 seconds is «1 мин»", async () => {
    await renderScreen({
      [importKey(101)]: [apiError(503, "GITHUB_RATE_LIMITED", { retry_after_seconds: 30 })],
    });
    fakeClock();
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("GitHub ограничил запросы платформы")).toBeTruthy();
    expect(alert.textContent).toContain("Это не ваша вина: лимит общий на всех. Попробуйте через 1 мин.");
    expect(button("Повторить через 1 мин", alert).disabled).toBe(true);
    tick(30_000);
    expect(button("Повторить", alert).disabled).toBe(false);
  });

  test.each([
    ["missing", {}],
    ["negative", { retry_after_seconds: -5 }],
    ["a string", { retry_after_seconds: "60" }],
  ])("a %s retry_after_seconds gives «Попробуйте позже.» and no countdown", async (_name, details) => {
    await renderScreen({ [importKey(101)]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", details)] });
    fireEvent.click(importButton("ann/one"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(
      "Вы много раз обращались к GitHub за последний час. Попробуйте позже.",
    );
    expect(alert.textContent).not.toMatch(/через/);
    expect(button("Повторить", alert).disabled).toBe(false);
    expect(importButton("ann/one").disabled).toBe(false);
  });

  test("a list 429 counts down, then «Повторить» reloads the list", async () => {
    fakeClock();
    await renderScreen({
      [listKey(1)]: [
        apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 90 }),
        page([ONE]),
      ],
    });
    const alert = screen.getByRole("alert");
    expect(button("Повторить через 2 мин", alert).disabled).toBe(true);
    expect(screen.queryByRole("navigation", { name: "Страницы списка" })).toBeNull();

    tick(90_000);
    fireEvent.click(button("Повторить", alert));
    await waitFor(() => expect(card("ann/one")).toBeTruthy());
    expect(calls(listKey(1))).toHaveLength(2);
  });

  test("the countdown timer is cleared on unmount", async () => {
    const view = await renderScreen({
      [importKey(101)]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 600 })],
    });
    fakeClock();
    fireEvent.click(importButton("ann/one"));
    await screen.findByRole("alert");
    expect(vi.getTimerCount()).toBe(1);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("list errors", () => {
  test("GITHUB_LOGIN_OUTDATED offers «Войти через GitHub» with the login URL", async () => {
    await renderScreen({ [listKey(1)]: [apiError(409, "GITHUB_LOGIN_OUTDATED")] });
    const alert = screen.getByRole("alert");
    expect(within(alert).getByText("Логин на GitHub изменился")).toBeTruthy();
    expect(
      within(alert).getByText(
        "Мы запомнили ваш прежний логин и не видим ваши репозитории. Войдите заново, и мы обновим его.",
      ),
    ).toBeTruthy();
    expect(
      within(alert).getByRole("link", { name: "Войти через GitHub" }).getAttribute("href"),
    ).toBe(`${API}/auth/github/login`);
    expect(within(alert).queryByRole("button")).toBeNull();
    expect(alert.textContent).not.toContain("GITHUB_LOGIN_OUTDATED");
  });

  test("GITHUB_UNAVAILABLE: «Повторить» reloads; nothing is repeated without a click", async () => {
    await renderScreen({
      [listKey(1)]: [apiError(502, "GITHUB_UNAVAILABLE"), page([ONE])],
    });
    expect(screen.getByText("GitHub сейчас недоступен")).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(listKey(1))).toHaveLength(1);

    fireEvent.click(button("Повторить"));
    await waitFor(() => expect(card("ann/one")).toBeTruthy());
    expect(calls(listKey(1))).toHaveLength(2);
  });

  test("INTERNAL_ERROR shows the request code and «Повторить»", async () => {
    await renderScreen({ [listKey(1)]: [apiError(500, "INTERNAL_ERROR"), page([ONE])] });
    expect(screen.getByText("Код запроса: r-9")).toBeTruthy();
    fireEvent.click(button("Повторить"));
    await waitFor(() => expect(card("ann/one")).toBeTruthy());
  });

  test("401 on the list leaves for /login", async () => {
    await renderScreen({ [listKey(1)]: [apiError(401, "UNAUTHORIZED")] }, { wait: false });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("401 on the projects leaves for /login", async () => {
    await renderScreen({ "GET /projects": [apiError(401, "UNAUTHORIZED")] }, { wait: false });
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("a failed GET /projects shows the load error with «Повторить»", async () => {
    await renderScreen({
      "GET /projects": [apiError(500, "INTERNAL_ERROR"), projectList(PROJECTS)],
    });
    expect(screen.getByText("Код запроса: r-9")).toBeTruthy();
    fireEvent.click(button("Повторить"));
    await waitFor(() => expect(card("ann/one")).toBeTruthy());
    expect(calls("GET /projects")).toHaveLength(2);
  });
});

describe("the link dialog", () => {
  async function openDialog(fullName = "ann/one", table: Record<string, Reply[]> = {}) {
    await renderScreen(table);
    fireEvent.click(linkButton(fullName));
    return screen.findByRole("dialog", { name: "Привязать к проекту" });
  }

  test("lists the projects with their state; focus starts on the first project", async () => {
    const dialog = await openDialog();
    const radios = within(dialog).getAllByRole<HTMLInputElement>("radio");
    expect(radios).toHaveLength(2);
    expect(within(dialog).getByRole("radio", { name: /Alpha/ })).toBe(radios[0]);
    await waitFor(() => expect(document.activeElement).toBe(radios[0]));
    expect(within(dialog).getByText("Черновик")).toBeTruthy();
    expect(within(dialog).getByText("Опубликован")).toBeTruthy();
    expect(within(dialog).getByText("Репозиторий: ann/one")).toBeTruthy();
    expect(
      within(dialog).getByText("Привязка не меняет статус, видимость и тексты проекта."),
    ).toBeTruthy();
  });

  test("«Уже привязан к …» only under a project that has a repository", async () => {
    const dialog = await openDialog();
    const hint = "Уже привязан к ann/old. Новая привязка заменит старую.";
    expect(within(dialog).getAllByText(hint)).toHaveLength(1);
    const beta = within(dialog).getByRole("radio", { name: /Beta/ });
    expect(document.getElementById(beta.getAttribute("aria-describedby")!)!.textContent).toBe(hint);
    expect(within(dialog).getByRole("radio", { name: /Alpha/ }).getAttribute("aria-describedby")).toBeNull();
  });

  test("«Привязать» is disabled until a project is chosen", async () => {
    const dialog = await openDialog();
    expect(button("Привязать", dialog).disabled).toBe(true);
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    expect(button("Привязать", dialog).disabled).toBe(false);
  });

  test.each([
    ["Escape", (dialog: HTMLElement) => fireEvent.keyDown(dialog, { key: "Escape" })],
    ["«Отмена»", (dialog: HTMLElement) => fireEvent.click(button("Отмена", dialog))],
  ])("%s closes it and sends nothing", async (_name, close) => {
    const dialog = await openDialog();
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    close(dialog);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
  });

  test("a link sends full_name, moves the badge, confirms and re-reads only GET /projects", async () => {
    const linked = projectResponse(BETA, ONE);
    const dialog = await openDialog("ann/one", {
      [linkKey("b")]: [Response.json(linked)],
      "GET /projects": [
        projectList(PROJECTS),
        projectList([ALPHA, { ...BETA, github: { full_name: "ann/one", html_url: ONE.html_url } }]),
      ],
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Beta/ }));
    fireEvent.click(button("Привязать", dialog));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [, init] = calls(linkKey("b"))[0];
    expect(JSON.parse(init!.body as string)).toEqual({ full_name: "ann/one" });

    const one = card("ann/one");
    expect(within(one).getByText("Привязан")).toBeTruthy();
    expect(within(one).getByRole("link", { name: "Beta" })).toBeTruthy();
    // ann/old was linked to Beta; the link replaced it.
    const old = card("ann/old");
    expect(within(old).queryByText("Привязан")).toBeNull();
    expect(linkButton("ann/old")).toBeTruthy();

    const notice = screen.getByRole("status");
    expect(within(notice).getByText("Репозиторий привязан")).toBeTruthy();
    expect(notice.textContent).toContain(
      "Проект «Beta» привязан к ann/one. Статус, видимость и тексты проекта не менялись.",
    );
    await waitFor(() => expect(calls("GET /projects")).toHaveLength(2));
    expect(calls(listKey(1))).toHaveLength(1);
    await waitFor(() => expect(document.activeElement).toBe(notice));

    fireEvent.click(linkButton("ann/fork"));
    const next = await screen.findByRole("dialog");
    expect(within(next).getByText("Уже привязан к ann/one. Новая привязка заменит старую.")).toBeTruthy();
  });

  test("a double click on «Привязать» sends one request", async () => {
    const reply = deferred();
    const dialog = await openDialog("ann/one", { [linkKey("a")]: [reply.promise] });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    const target = button("Привязать", dialog);

    act(() => {
      target.click();
      target.click();
    });

    expect(calls(linkKey("a"))).toHaveLength(1);
    expect(button("Проверяем на GitHub…", dialog).disabled).toBe(true);
    expect(button("Отмена", dialog).disabled).toBe(true);
    await act(async () => reply.resolve(apiError(422, "GITHUB_RELATION_NOT_FOUND")));
  });

  test("Escape during the request does not close the dialog", async () => {
    const reply = deferred();
    const dialog = await openDialog("ann/one", { [linkKey("a")]: [reply.promise] });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBe(dialog);
    await act(async () => reply.resolve(apiError(422, "GITHUB_RELATION_NOT_FOUND")));
  });

  test("errors stay inside the open dialog and the buttons work again", async () => {
    const dialog = await openDialog("ann/one", {
      [linkKey("a")]: [apiError(422, "GITHUB_RELATION_NOT_FOUND")],
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));

    const alert = await within(dialog).findByRole("alert");
    expect(within(alert).getByText("Связь с репозиторием не найдена")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(button("Привязать", dialog).disabled).toBe(false);
    expect(button("Отмена", dialog).disabled).toBe(false);
    expect(within(card("ann/one")).queryByText("Привязан")).toBeNull();
  });

  test("ALREADY_LINKED in the dialog names the project and marks the card behind", async () => {
    const dialog = await openDialog("ann/one", {
      [linkKey("a")]: [apiError(409, "GITHUB_REPOSITORY_ALREADY_LINKED", { project_id: "b" })],
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));

    const alert = await within(dialog).findByRole("alert");
    expect(alert.textContent).toContain("уже привязан к вашему проекту «Beta»");
    expect(within(alert).getByRole("link", { name: "Открыть проект" }).getAttribute("href")).toBe(
      "/me/projects/b",
    );
    fireEvent.click(button("Отмена", dialog));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(within(card("ann/one")).getByText("Привязан")).toBeTruthy();
    // The project moved its link to ann/one, so ann/old is unlinked locally.
    expect(within(card("ann/old")).queryByText("Привязан")).toBeNull();
  });

  test("GITHUB_UNAVAILABLE in the dialog: «Повторить» sends the link again", async () => {
    const dialog = await openDialog("ann/one", {
      [linkKey("a")]: [apiError(502, "GITHUB_UNAVAILABLE"), Response.json(projectResponse(ALPHA, ONE))],
    });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));
    await within(dialog).findByText("GitHub сейчас недоступен");
    fireEvent.click(button("Повторить", dialog));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls(linkKey("a"))).toHaveLength(2);
    expect(within(card("ann/one")).getByRole("link", { name: "Alpha" })).toBeTruthy();
  });

  test("a 429 in the dialog keeps «Привязать» disabled until the countdown ends", async () => {
    const dialog = await openDialog("ann/one", {
      [linkKey("a")]: [apiError(429, "GITHUB_USER_LIMIT_REACHED", { retry_after_seconds: 60 })],
    });
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));

    const alert = await within(dialog).findByRole("alert");
    expect(button("Повторить через 1 мин", alert).disabled).toBe(true);
    expect(button("Привязать", dialog).disabled).toBe(true);
    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    expect(button("Привязать", dialog).disabled).toBe(false);
    fireEvent.click(button("Повторить", alert));
    expect(within(dialog).queryByRole("alert")).toBeNull();
  });

  test("401 on a link leaves for /login", async () => {
    const dialog = await openDialog("ann/one", { [linkKey("a")]: [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(within(dialog).getByRole("radio", { name: /Alpha/ }));
    fireEvent.click(button("Привязать", dialog));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("without projects it shows [Пока нет проектов] and only «Отмена»", async () => {
    const dialog = await openDialog("ann/one", { "GET /projects": [projectList([])] });
    expect(within(dialog).getByText("[Пока нет проектов]")).toBeTruthy();
    expect(within(dialog).queryByRole("radio")).toBeNull();
    expect(within(dialog).getAllByRole("button").map((b) => b.textContent)).toEqual(["Отмена"]);
    await waitFor(() => expect(document.activeElement).toBe(button("Отмена", dialog)));
  });
});
