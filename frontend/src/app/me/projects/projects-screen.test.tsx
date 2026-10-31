import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ProjectsScreen } from "./projects-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";

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

function project(id: string, title: string, fields: Partial<Summary> = {}): Summary {
  return {
    id,
    status: "PUBLISHED",
    visibility: "PUBLIC",
    title,
    summary: `${title} summary`,
    technologies: ["Python", "FastAPI"],
    featured_position: null,
    github: null,
    ...fields,
  };
}

// The list is newest first; positions do not follow list order.
const ALPHA = project("a", "Alpha", { featured_position: 2 });
const BETA = project("b", "Beta", { featured_position: 1 });
const GAMMA = project("g", "Gamma");
const DELTA = project("d", "Delta", { visibility: "PRIVATE" });
const EPSILON = project("e", "Epsilon", { status: "DRAFT", visibility: "PRIVATE", technologies: [] });
const ZETA = project("z", "Zeta", { status: "ARCHIVED", visibility: "PRIVATE" });
const ALL = [ALPHA, BETA, GAMMA, DELTA, EPSILON, ZETA];

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
  return Response.json({ error: { code, message: code, details, request_id: "r-9" } }, { status });
}

function full(summary: Summary, fields: Partial<Summary> = {}) {
  return {
    ...summary,
    description: null,
    problem: null,
    results: null,
    role: "Dev",
    contribution: "All",
    ...fields,
  };
}

function featured(...items: [string, number][]) {
  return Response.json({ items: items.map(([project_id, position]) => ({ project_id, position })) });
}

type Reply = Response | Promise<Response> | (() => Response | Promise<Response>);

/**
 * Answers by "METHOD /path". Each route answers its replies in order and then
 * repeats the last one. Unknown routes fail the test.
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

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  replace.mockReset();
});

async function renderList(items: Summary[] = ALL, extra: Record<string, Reply[]> = {}) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    "GET /projects": [Response.json({ items })],
    ...extra,
  });
  render(<ProjectsScreen />);
  await screen.findByRole("heading", { name: "Мои проекты" });
}

const card = (title: string) =>
  screen.getByRole("heading", { name: title, level: 3 }).closest("li") as HTMLElement;
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const featuredTitles = () =>
  within(screen.getByRole("region", { name: "Главные проекты" }))
    .queryAllByRole("listitem")
    .map((item) => item.querySelector("p")!.textContent!.replace(/^Место \d+: /, ""));

describe("loading", () => {
  test("loads GET /projects with a loading state", () => {
    routes({ "GET /profile": [Response.json(PROFILE)], "GET /projects": [new Promise(() => {})] });
    render(<ProjectsScreen />);
    expect(screen.getByRole("status").textContent).toBe("Загрузка…");
    expect(calls("GET /projects")).toHaveLength(1);
  });

  test("shows the header and the tabs with Проекты active", async () => {
    await renderList();
    expect(await screen.findByText("@ann-gh")).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Кабинет" });
    expect(within(nav).getByRole("link", { name: "Профиль" }).getAttribute("href")).toBe("/me");
    const current = within(nav).getByRole("link", { name: "Проекты" });
    expect(current.getAttribute("href")).toBe("/me/projects");
    expect(current.getAttribute("aria-current")).toBe("page");
  });

  test.each(["GET /projects", "GET /profile"])("401 from %s redirects to /login", async (key) => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      "GET /projects": [Response.json({ items: [] })],
      [key]: [apiError(401, "UNAUTHORIZED")],
    });
    render(<ProjectsScreen />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("a network error offers a retry", async () => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      "GET /projects": [
        () => Promise.reject(new TypeError("Failed to fetch")),
        Response.json({ items: ALL }),
      ],
    });
    render(<ProjectsScreen />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    fireEvent.click(button("Повторить"));
    await screen.findByRole("heading", { name: "Мои проекты" });
    expect(calls("GET /projects")).toHaveLength(2);
  });

  test("another error shows the generic text with the request id", async () => {
    routes({ "GET /profile": [Response.json(PROFILE)], "GET /projects": [apiError(500, "INTERNAL_ERROR")] });
    render(<ProjectsScreen />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-9");
  });
});

describe("list", () => {
  test("counters and the new project link", async () => {
    await renderList();
    expect(screen.getByText("Проектов: 6 из 50 · Главных: 2 из 3")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Новый проект" }).getAttribute("href")).toBe(
      "/me/projects/new",
    );
  });

  test("at 50 projects «Новый проект» is disabled with the reason", async () => {
    const many = Array.from({ length: 50 }, (_, i) =>
      project(`p${i}`, `P${i}`, { status: "DRAFT", visibility: "PRIVATE" }),
    );
    await renderList(many);
    expect(screen.queryByRole("link", { name: "Новый проект" })).toBeNull();
    const create = button("Новый проект");
    expect(create.disabled).toBe(true);
    expect(document.getElementById(create.getAttribute("aria-describedby")!)!.textContent).toBe(
      "Можно создать не больше 50 проектов.",
    );
    // Linking still works at the limit, so the repository page stays reachable.
    expect(screen.getByRole("link", { name: "Импорт из GitHub" }).getAttribute("href")).toBe(
      "/me/repositories",
    );
  });

  test("«Импорт из GitHub» opens the repository page", async () => {
    await renderList();
    expect(screen.getByRole("link", { name: "Импорт из GitHub" }).getAttribute("href")).toBe(
      "/me/repositories",
    );
  });

  test("an empty list", async () => {
    await renderList([]);
    expect(screen.getByText("[Пока нет проектов]")).toBeTruthy();
    expect(screen.getByText("Свободное место для главного проекта: 3 из 3")).toBeTruthy();
    expect(featuredTitles()).toEqual([]);
  });

  test("a project without a title", async () => {
    await renderList([project("x", "", { title: null, status: "DRAFT", visibility: "PRIVATE" })]);
    expect(screen.getByRole("heading", { name: "[Без названия]", level: 3 })).toBeTruthy();
  });

  test.each([
    ["Alpha", ["Опубликован", "Главный: 2"], ["Редактировать: Alpha", "Скрыть", "В архив"]],
    ["Beta", ["Опубликован", "Главный: 1"], ["Редактировать: Beta", "Скрыть", "В архив"]],
    ["Gamma", ["Опубликован"], ["Редактировать: Gamma", "Сделать главным", "Скрыть", "В архив"]],
    ["Delta", ["Скрыт"], ["Редактировать: Delta", "Показать", "В архив"]],
    ["Epsilon", ["Черновик"], ["Редактировать: Epsilon", "Опубликовать", "Удалить"]],
    ["Zeta", ["В архиве"], ["Редактировать: Zeta", "Опубликовать снова", "Удалить"]],
  ])("%s: badges and actions", async (title, badges, actions) => {
    await renderList();
    const item = within(card(title));
    for (const badge of badges) {
      expect(item.getByText(badge)).toBeTruthy();
    }
    const controls = [...item.queryAllByRole("link"), ...item.queryAllByRole("button")].map(
      (el) => el.getAttribute("aria-label") ?? el.textContent,
    );
    expect(controls.sort()).toEqual([...actions].sort());
    expect(item.getByRole("link").getAttribute("href")).toBe(`/me/projects/${title[0].toLowerCase()}`);
  });

  test("card content and notes", async () => {
    await renderList();
    expect(within(card("Gamma")).getByText("Gamma summary")).toBeTruthy();
    expect(
      within(within(card("Gamma")).getByRole("list", { name: "Технологии" }))
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Python", "FastAPI"]);
    expect(within(card("Delta")).getByText("Опубликован, но не виден посетителям. Из главных убран.")).toBeTruthy();
    expect(
      within(card("Alpha")).getByText("«Скрыть» и «В архив» уберут проект из главных."),
    ).toBeTruthy();
    expect(within(card("Gamma")).queryByText(/уберут проект из главных/)).toBeNull();
  });

  test("«Сделать главным» is disabled with a hint at three featured", async () => {
    await renderList([...ALL, project("h", "Eta", { featured_position: 3 })]);
    const make = within(card("Gamma")).getByRole("button", { name: "Сделать главным" });
    expect((make as HTMLButtonElement).disabled).toBe(true);
    expect(document.getElementById(make.getAttribute("aria-describedby")!)!.textContent).toBe(
      "В главных уже 3 проекта. Уберите один, чтобы добавить другой.",
    );
    expect(screen.queryByText(/Свободное место/)).toBeNull();
  });
});

describe("featured order", () => {
  test("by position, with the outer arrows disabled", async () => {
    await renderList();
    expect(featuredTitles()).toEqual(["Beta", "Alpha"]);
    expect(button("Выше: Beta").disabled).toBe(true);
    expect(button("Ниже: Beta").disabled).toBe(false);
    expect(button("Выше: Alpha").disabled).toBe(false);
    expect(button("Ниже: Alpha").disabled).toBe(true);
    expect(screen.getByText("Свободное место для главного проекта: 1 из 3")).toBeTruthy();
  });

  test("a move sends the full list and applies the response; controls wait", async () => {
    const reply = deferred();
    await renderList(ALL, { "POST /profile/featured-projects/reorder": [reply.promise] });

    fireEvent.click(button("Ниже: Beta"));
    fireEvent.click(button("Ниже: Beta"));
    const sent = calls("POST /profile/featured-projects/reorder");
    expect(sent).toHaveLength(1);
    expect(JSON.parse(sent[0][1]!.body as string)).toEqual({ project_ids: ["a", "b"] });
    expect(button("Выше: Alpha").disabled).toBe(true);
    for (const el of screen.getAllByRole("button", { name: "Убрать из главных" })) {
      expect((el as HTMLButtonElement).disabled).toBe(true);
    }
    expect(within(card("Epsilon")).getByRole("button", { name: "Удалить" })).toHaveProperty(
      "disabled",
      true,
    );

    await act(async () => reply.resolve(featured(["a", 1], ["b", 2])));
    await waitFor(() => expect(featuredTitles()).toEqual(["Alpha", "Beta"]));
    expect(within(card("Alpha")).getByText("Главный: 1")).toBeTruthy();
    expect(button("Выше: Alpha").disabled).toBe(true);
  });

  test("FEATURED_ORDER_MISMATCH reloads the list with a message", async () => {
    await renderList(ALL, {
      "POST /profile/featured-projects/reorder": [apiError(409, "FEATURED_ORDER_MISMATCH")],
      "GET /projects": [
        Response.json({ items: ALL }),
        Response.json({ items: [ALPHA, { ...BETA, featured_position: null }, GAMMA] }),
      ],
    });
    fireEvent.click(button("Выше: Alpha"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Список главных изменился, порядок загружен заново.",
    );
    await waitFor(() => expect(featuredTitles()).toEqual(["Alpha"]));
    expect(calls("GET /projects")).toHaveLength(2);
    expect(screen.queryByRole("heading", { name: "Zeta" })).toBeNull();
  });

  test("«Сделать главным» takes positions from the response", async () => {
    await renderList(ALL, {
      "POST /projects/g/showcase": [featured(["b", 1], ["a", 2], ["g", 3])],
    });
    fireEvent.click(within(card("Gamma")).getByRole("button", { name: "Сделать главным" }));
    await waitFor(() => expect(featuredTitles()).toEqual(["Beta", "Alpha", "Gamma"]));
    expect(screen.getByText("Проектов: 6 из 50 · Главных: 3 из 3")).toBeTruthy();
  });

  test("FEATURED_LIMIT_REACHED shows its text and reloads", async () => {
    await renderList(ALL, {
      "POST /projects/g/showcase": [apiError(409, "FEATURED_LIMIT_REACHED", { limit: 3 })],
    });
    fireEvent.click(within(card("Gamma")).getByRole("button", { name: "Сделать главным" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "В главных уже 3 проекта. Уберите один, чтобы добавить другой.",
    );
    await waitFor(() => expect(calls("GET /projects")).toHaveLength(2));
  });

  test("«Убрать из главных» takes positions from the response", async () => {
    await renderList(ALL, { "DELETE /projects/b/showcase": [featured(["a", 1])] });
    const beta = screen
      .getAllByRole("button", { name: "Убрать из главных" })
      .find((el) => el.closest("li")!.textContent!.includes("Beta"))!;
    fireEvent.click(beta);
    await waitFor(() => expect(featuredTitles()).toEqual(["Alpha"]));
    expect(within(card("Alpha")).getByText("Главный: 1")).toBeTruthy();
  });
});

describe("lifecycle actions", () => {
  test("publishing a draft updates its card from the response", async () => {
    await renderList(ALL, {
      "POST /projects/e/publish": [Response.json(full(EPSILON, { status: "PUBLISHED", visibility: "PUBLIC" }))],
    });
    fireEvent.click(within(card("Epsilon")).getByRole("button", { name: "Опубликовать" }));
    await waitFor(() => expect(within(card("Epsilon")).getByText("Опубликован")).toBeTruthy());
    expect(calls("GET /projects")).toHaveLength(1);
  });

  test("PROJECT_INCOMPLETE names the missing fields on the card", async () => {
    await renderList(ALL, {
      "POST /projects/e/publish": [
        apiError(422, "PROJECT_INCOMPLETE", {
          missing_fields: ["role", "contribution", "technologies"],
        }),
      ],
    });
    fireEvent.click(within(card("Epsilon")).getByRole("button", { name: "Опубликовать" }));
    expect((await within(card("Epsilon")).findByRole("alert")).textContent).toBe(
      "Чтобы опубликовать, не хватает: роль, технологии, вклад.",
    );
    expect(within(card("Epsilon")).getByText("Черновик")).toBeTruthy();
  });

  test.each([
    ["Скрыть", "POST /projects/a/visibility", { visibility: "PRIVATE" }, { visibility: "PRIVATE" }],
    ["В архив", "POST /projects/a/archive", undefined, { status: "ARCHIVED", visibility: "PRIVATE" }],
  ] as const)(
    "«%s» on a featured project reloads the list for the new positions",
    async (action, key, body, change) => {
      await renderList(ALL, {
        [key]: [Response.json(full(ALPHA, { ...change, featured_position: null }))],
        "GET /projects": [
          Response.json({ items: ALL }),
          Response.json({
            items: [{ ...ALPHA, ...change, featured_position: null }, BETA, GAMMA],
          }),
        ],
      });
      fireEvent.click(within(card("Alpha")).getByRole("button", { name: action }));
      await waitFor(() => expect(calls("GET /projects")).toHaveLength(2));
      const sent = calls(key)[0][1]!;
      expect(sent.body === undefined ? undefined : JSON.parse(sent.body as string)).toEqual(body);
      await waitFor(() => expect(featuredTitles()).toEqual(["Beta"]));
    },
  );

  test("«Показать» on a hidden project", async () => {
    await renderList(ALL, {
      "POST /projects/d/visibility": [Response.json(full(DELTA, { visibility: "PUBLIC" }))],
    });
    fireEvent.click(within(card("Delta")).getByRole("button", { name: "Показать" }));
    await waitFor(() => expect(within(card("Delta")).getByText("Опубликован")).toBeTruthy());
    expect(JSON.parse(calls("POST /projects/d/visibility")[0][1]!.body as string)).toEqual({
      visibility: "PUBLIC",
    });
  });

  test("PROJECT_TRANSITION_INVALID shows its text and reloads", async () => {
    await renderList(ALL, {
      "POST /projects/z/publish": [apiError(409, "PROJECT_TRANSITION_INVALID", { status: "DRAFT" })],
    });
    fireEvent.click(within(card("Zeta")).getByRole("button", { name: "Опубликовать снова" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Это действие недоступно в текущем состоянии проекта. Данные загружены заново.",
    );
    await waitFor(() => expect(calls("GET /projects")).toHaveLength(2));
  });

  test("a network error on an action keeps the list", async () => {
    await renderList(ALL, {
      "POST /projects/g/archive": [() => Promise.reject(new TypeError("Failed to fetch"))],
    });
    fireEvent.click(within(card("Gamma")).getByRole("button", { name: "В архив" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    expect(within(card("Gamma")).getByText("Опубликован")).toBeTruthy();
  });

  test("401 on an action redirects to /login", async () => {
    await renderList(ALL, { "POST /projects/g/archive": [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(within(card("Gamma")).getByRole("button", { name: "В архив" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("delete", () => {
  test("cancel sends nothing", async () => {
    await renderList();
    fireEvent.click(within(card("Epsilon")).getByRole("button", { name: "Удалить" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Удалить проект?" });
    expect(dialog.textContent).toContain(
      "Проект «Epsilon» удалится навсегда вместе со своими данными. Отменить нельзя.",
    );
    expect(dialog.textContent).not.toMatch(/главн|архив/);
    fireEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(calls("DELETE /projects/e")).toHaveLength(0);
    expect(card("Epsilon")).toBeTruthy();
  });

  test("confirm sends DELETE once and removes the card on 204", async () => {
    await renderList(ALL, { "DELETE /projects/z": [new Response(null, { status: 204 })] });
    fireEvent.click(within(card("Zeta")).getByRole("button", { name: "Удалить" }));
    const dialog = await screen.findByRole("alertdialog");
    const confirm = within(dialog).getByRole("button", { name: "Удалить навсегда" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Zeta" })).toBeNull());
    expect(calls("DELETE /projects/z")).toHaveLength(1);
    expect(screen.getByText("Проектов: 5 из 50 · Главных: 2 из 3")).toBeTruthy();
  });
});

describe("the GitHub label", () => {
  const repo = (name: string) => ({ full_name: `ann/${name}`, html_url: `https://github.com/ann/${name}` });

  test("a linked project shows «GitHub» and full_name in every state; github null shows nothing", async () => {
    const linked = [
      project("l1", "Live", { featured_position: 1, github: repo("live") }),
      project("l2", "Hidden", { visibility: "PRIVATE", github: repo("hidden") }),
      project("l3", "Draft", { status: "DRAFT", visibility: "PRIVATE", github: repo("draft") }),
      project("l4", "Archived", { status: "ARCHIVED", visibility: "PRIVATE", github: repo("archived") }),
    ];
    await renderList([...linked, project("n1", "Plain")]);

    for (const [title, name] of [
      ["Live", "live"],
      ["Hidden", "hidden"],
      ["Draft", "draft"],
      ["Archived", "archived"],
    ]) {
      const item = card(title);
      expect(within(item).getByText("GitHub")).toBeTruthy();
      const link = within(item).getByRole("link", { name: `ann/${name}` });
      expect(link.getAttribute("href")).toBe(`https://github.com/ann/${name}`);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
    const plain = card("Plain");
    expect(within(plain).queryByText("GitHub")).toBeNull();
    expect(within(plain).queryByRole("link", { name: /ann\// })).toBeNull();
  });

  test("the label says only which repository: no relation, languages or sync", async () => {
    await renderList([project("l1", "Live", { technologies: ["Go"], github: repo("live") })]);
    const item = card("Live");
    const label = within(item).getByText("GitHub").parentElement!;
    expect(label.textContent).toBe("GitHubann/live");
  });

  test("full_name with a non-GitHub URL is plain text, and markup is text", async () => {
    await renderList([
      project("x", "Odd", {
        github: { full_name: "<b>ann</b>/x", html_url: "javascript:alert(1)" },
      }),
    ]);
    const item = card("Odd");
    expect(within(item).getByText("<b>ann</b>/x")).toBeTruthy();
    expect(within(item).queryByRole("link", { name: /ann/ })).toBeNull();
    expect(item.querySelector("b")).toBeNull();
  });
});
