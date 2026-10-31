import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { ProjectResponse } from "@/lib/api";

import { ProjectEditScreen } from "./project-edit-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";
const ID = "p1";

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
  technologies: ["Python", "Go"],
  featured_position: null,
  github: null,
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
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  replace.mockReset();
});

async function renderNew(extra: Record<string, Reply[]> = {}) {
  routes({ "GET /profile": [Response.json(PROFILE)], ...extra });
  render(<ProjectEditScreen />);
  await screen.findByRole("form", { name: "Проект" });
}

async function renderEdit(project: Partial<ProjectResponse> = {}, extra: Record<string, Reply[]> = {}) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    [`GET /projects/${ID}`]: [Response.json({ ...PROJECT, ...project })],
    ...extra,
  });
  render(<ProjectEditScreen projectId={ID} />);
  await screen.findByRole("form", { name: "Проект" });
}

const field = (name: string) => screen.getByRole("textbox", { name }) as HTMLInputElement;
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const type = (name: string, value: string) => fireEvent.change(field(name), { target: { value } });
const chips = () =>
  screen.queryByRole("list", { name: "Добавленные технологии" })
    ? within(screen.getByRole("list", { name: "Добавленные технологии" }))
        .getAllByRole("listitem")
        .map((li) => li.querySelector("span")!.textContent)
    : [];

function addTechnology(name: string, via: "enter" | "button" = "enter") {
  type("Технологии", name);
  if (via === "enter") {
    fireEvent.keyDown(field("Технологии"), { key: "Enter" });
  } else {
    fireEvent.click(button("Добавить"));
  }
}

describe("loading", () => {
  test("an existing project is loaded with GET /projects/{id}", async () => {
    await renderEdit();
    expect(calls(`GET /projects/${ID}`)).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Проект" })).toBeTruthy();
    expect(screen.getByText("Черновик")).toBeTruthy();
    expect(field("Название").value).toBe("Payments");
    expect(field("Роль").value).toBe("");
    expect(chips()).toEqual(["Python", "Go"]);
    expect(screen.getByRole("link", { name: /Назад к проектам/ }).getAttribute("href")).toBe(
      "/me/projects",
    );
    expect(screen.queryByRole("navigation", { name: "Кабинет" })).toBeNull();
  });

  test("404 shows «Проект не найден» with a link to the list", async () => {
    routes({ "GET /profile": [Response.json(PROFILE)], [`GET /projects/${ID}`]: [apiError(404, "NOT_FOUND")] });
    render(<ProjectEditScreen projectId={ID} />);
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Мои проекты" }).getAttribute("href")).toBe(
      "/me/projects",
    );
    expect(screen.queryByRole("form")).toBeNull();
  });

  test("401 redirects to /login", async () => {
    routes({ "GET /profile": [Response.json(PROFILE)], [`GET /projects/${ID}`]: [apiError(401, "UNAUTHORIZED")] });
    render(<ProjectEditScreen projectId={ID} />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("a network error offers a retry", async () => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [
        () => Promise.reject(new TypeError("Failed to fetch")),
        Response.json(PROJECT),
      ],
    });
    render(<ProjectEditScreen projectId={ID} />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    fireEvent.click(button("Повторить"));
    await screen.findByRole("form", { name: "Проект" });
  });

  test("a new project starts empty without a request", async () => {
    await renderNew();
    expect(calls(`GET /projects/${ID}`)).toHaveLength(0);
    expect(screen.getByRole("heading", { name: "Новый проект" })).toBeTruthy();
    expect(button("Сохранить").disabled).toBe(true);
    expect(button("Опубликовать").disabled).toBe(true);
    expect(button("В архив").disabled).toBe(true);
    expect(screen.getByText("«В архив» доступно у опубликованного проекта")).toBeTruthy();
  });
});

describe("fields", () => {
  test("labels, limits and counters follow the API", async () => {
    await renderEdit();
    const limits: [string, number, string][] = [
      ["Название", 100, "INPUT"],
      ["Коротко о проекте", 300, "INPUT"],
      ["Роль", 100, "INPUT"],
      ["Ваш вклад", 2000, "TEXTAREA"],
      ["Подробное описание", 5000, "TEXTAREA"],
      ["Какую задачу решали", 2000, "TEXTAREA"],
      ["Результат", 2000, "TEXTAREA"],
    ];
    for (const [name, max, tag] of limits) {
      expect(field(name).maxLength).toBe(max);
      expect(field(name).tagName).toBe(tag);
    }
    expect(field("Технологии").maxLength).toBe(50);
    expect(document.getElementById("project-title-count")!.textContent).toBe("8 / 100");
    expect(document.getElementById("project-technologies-count")!.textContent).toBe("2 / 20");
    type("Коротко о проекте", "abc");
    expect(document.getElementById("project-summary-count")!.textContent).toBe("3 / 300");
  });
});

describe("technologies", () => {
  test("Enter and «Добавить» add trimmed names in order; Enter does not submit", async () => {
    await renderNew();
    addTechnology("  Node   js ");
    addTechnology("FastAPI", "button");
    expect(chips()).toEqual(["Node js", "FastAPI"]);
    expect(field("Технологии").value).toBe("");
    expect(calls("POST /projects")).toHaveLength(0);
    expect(document.getElementById("project-technologies-count")!.textContent).toBe("2 / 20");
  });

  test("blank names are ignored and duplicates ignoring case are rejected", async () => {
    await renderNew();
    addTechnology("Python");
    addTechnology("   ");
    addTechnology("PYTHON");
    expect(chips()).toEqual(["Python"]);
    expect(screen.getByText("«PYTHON» уже есть в списке.")).toBeTruthy();
    expect(field("Технологии").value).toBe("PYTHON");
  });

  test("× removes a chip", async () => {
    await renderEdit();
    fireEvent.click(button("Удалить «Python»"));
    expect(chips()).toEqual(["Go"]);
  });

  test("at 20 the input and «Добавить» stop", async () => {
    await renderNew();
    for (let i = 0; i < 20; i++) {
      addTechnology(`T${i}`);
    }
    expect(chips()).toHaveLength(20);
    expect(field("Технологии").readOnly).toBe(true);
    expect(button("Добавить").disabled).toBe(true);
    expect(screen.getByText("Не больше 20 технологий.")).toBeTruthy();
    fireEvent.keyDown(field("Технологии"), { key: "Enter" });
    expect(chips()).toHaveLength(20);
  });
});

describe("save", () => {
  test("a new project is created with POST and opens its edit screen", async () => {
    const reply = deferred();
    await renderNew({ "POST /projects": [reply.promise] });
    type("Название", "Payments");
    addTechnology("Python");
    fireEvent.click(button("Сохранить"));
    fireEvent.click(button("Сохранить"));

    expect(calls("POST /projects")).toHaveLength(1);
    expect(body("POST /projects")).toEqual({ title: "Payments", technologies: ["Python"] });
    expect(field("Название").readOnly).toBe(true);

    await act(async () => reply.resolve(Response.json({ ...PROJECT, id: "new-id" })));
    expect(replace).toHaveBeenCalledWith("/me/projects/new-id");
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("PROJECT_LIMIT_REACHED on create", async () => {
    await renderNew({ "POST /projects": [apiError(409, "PROJECT_LIMIT_REACHED", { limit: 50 })] });
    type("Название", "One more");
    fireEvent.click(button("Сохранить"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Можно создать не больше 50 проектов.",
    );
    expect(replace).not.toHaveBeenCalled();
  });

  test("PATCH sends only the changed fields and shows the stored values", async () => {
    const stored = { ...PROJECT, summary: null, role: "Lead", technologies: ["Go", "python"] };
    await renderEdit({}, { [`PATCH /projects/${ID}`]: [Response.json(stored)] });
    expect(button("Сохранить").disabled).toBe(true);

    type("Коротко о проекте", "");
    type("Роль", "  Lead ");
    fireEvent.click(button("Удалить «Python»"));
    addTechnology("python");
    fireEvent.click(button("Сохранить"));

    await screen.findByText("Сохранено");
    expect(body(`PATCH /projects/${ID}`)).toEqual({
      summary: null,
      role: "  Lead ",
      technologies: ["Go", "python"],
    });
    expect(field("Роль").value).toBe("Lead");
    expect(chips()).toEqual(["Go", "python"]);
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("restoring the stored value makes the form clean again", async () => {
    await renderEdit();
    type("Название", "Other");
    expect(button("Сохранить").disabled).toBe(false);
    type("Название", "Payments");
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("422 VALIDATION_ERROR is shown under its fields", async () => {
    await renderEdit({}, {
      [`PATCH /projects/${ID}`]: [
        apiError(422, "VALIDATION_ERROR", {
          fields: [
            { loc: ["body", "title"], type: "string_too_long" },
            { loc: ["body", "technologies"], type: "duplicate_technology" },
          ],
        }),
      ],
    });
    type("Название", "x");
    fireEvent.click(button("Сохранить"));
    expect(await screen.findByText("Не больше 100 символов.")).toBeTruthy();
    expect(
      screen.getByText("Технологии не должны повторяться, даже с другим регистром букв."),
    ).toBeTruthy();
    expect(field("Название").getAttribute("aria-invalid")).toBe("true");
    expect(field("Технологии").getAttribute("aria-invalid")).toBe("true");
    expect(field("Название").value).toBe("x");
  });

  test("a network error keeps the edits", async () => {
    await renderEdit({}, {
      [`PATCH /projects/${ID}`]: [() => Promise.reject(new TypeError("Failed to fetch"))],
    });
    type("Название", "Kept");
    fireEvent.click(button("Сохранить"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    expect(field("Название").value).toBe("Kept");
  });

  test("another error shows the request id", async () => {
    await renderEdit({}, { [`PATCH /projects/${ID}`]: [apiError(500, "INTERNAL_ERROR")] });
    type("Название", "x");
    fireEvent.click(button("Сохранить"));
    expect((await screen.findByRole("alert")).textContent).toContain("Код запроса: r-7");
  });

  test("PROJECT_INCOMPLETE from save", async () => {
    await renderEdit({ status: "PUBLISHED", visibility: "PUBLIC", role: "Dev", contribution: "x" }, {
      [`PATCH /projects/${ID}`]: [apiError(422, "PROJECT_INCOMPLETE", { missing_fields: ["role"] })],
    });
    type("Роль", "");
    fireEvent.click(button("Сохранить"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Нельзя сохранить");
    expect(alert.textContent).toContain(
      "Заполните обязательное поле: «Роль». Опубликованный проект должен оставаться заполненным.",
    );
  });
});

describe("publish and archive", () => {
  test("«Опубликовать» is disabled while there are unsaved changes", async () => {
    await renderEdit();
    expect(button("Опубликовать").disabled).toBe(false);
    type("Название", "Changed");
    expect(button("Опубликовать").disabled).toBe(true);
    expect(screen.getByText("Сохраните изменения, чтобы опубликовать проект.")).toBeTruthy();
  });

  test("PROJECT_INCOMPLETE highlights the missing fields", async () => {
    await renderEdit({ technologies: [] }, {
      [`POST /projects/${ID}/publish`]: [
        apiError(422, "PROJECT_INCOMPLETE", {
          missing_fields: ["role", "contribution", "technologies"],
        }),
      ],
    });
    fireEvent.click(button("Опубликовать"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Нельзя опубликовать");
    expect(alert.textContent).toContain(
      "Заполните обязательные поля: «Роль», «Технологии», «Ваш вклад».",
    );
    expect(field("Роль").getAttribute("aria-invalid")).toBe("true");
    expect(field("Ваш вклад").getAttribute("aria-invalid")).toBe("true");
    expect(field("Название").getAttribute("aria-invalid")).toBeNull();
    expect(screen.getAllByText("Заполните это поле")).toHaveLength(2);
    expect(screen.getByText("Нужна хотя бы одна")).toBeTruthy();
    expect(screen.getByText("Черновик")).toBeTruthy();
  });

  test("the error block is scrolled into view", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      await renderEdit({ technologies: [] }, {
        [`POST /projects/${ID}/publish`]: [
          apiError(422, "PROJECT_INCOMPLETE", { missing_fields: ["technologies"] }),
        ],
      });
      fireEvent.click(button("Опубликовать"));
      const alert = await screen.findByRole("alert");
      await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
      expect(scrollIntoView.mock.contexts[0]).toBe(alert.parentElement);
    } finally {
      delete (Element.prototype as Partial<Element>).scrollIntoView;
    }
  });

  test("publish updates the badge and enables «В архив»", async () => {
    await renderEdit({}, {
      [`POST /projects/${ID}/publish`]: [
        Response.json({ ...PROJECT, status: "PUBLISHED", visibility: "PUBLIC" }),
      ],
    });
    fireEvent.click(button("Опубликовать"));
    expect(await screen.findByText("Опубликован")).toBeTruthy();
    expect(button("Опубликовать").disabled).toBe(true);
    expect(button("В архив").disabled).toBe(false);
  });

  test("archive keeps unsaved edits and warns about a featured project", async () => {
    await renderEdit({ status: "PUBLISHED", visibility: "PUBLIC", featured_position: 2 }, {
      [`POST /projects/${ID}/archive`]: [
        Response.json({ ...PROJECT, status: "ARCHIVED", visibility: "PRIVATE" }),
      ],
    });
    expect(screen.getByText("«В архив» уберёт проект из главных.")).toBeTruthy();
    type("Название", "Unsaved");
    fireEvent.click(button("В архив"));
    expect(await screen.findByText("В архиве")).toBeTruthy();
    expect(field("Название").value).toBe("Unsaved");
    expect(button("В архив").disabled).toBe(true);
  });

  test("PROJECT_TRANSITION_INVALID reloads the project", async () => {
    await renderEdit({}, {
      [`POST /projects/${ID}/publish`]: [apiError(409, "PROJECT_TRANSITION_INVALID")],
      [`GET /projects/${ID}`]: [
        Response.json(PROJECT),
        Response.json({ ...PROJECT, status: "PUBLISHED", visibility: "PUBLIC" }),
      ],
    });
    fireEvent.click(button("Опубликовать"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Это действие недоступно в текущем состоянии проекта. Данные загружены заново.",
    );
    expect(await screen.findByText("Опубликован")).toBeTruthy();
    expect(calls(`GET /projects/${ID}`)).toHaveLength(2);
  });

  test("404 on an action shows «Проект не найден»", async () => {
    await renderEdit({}, { [`POST /projects/${ID}/publish`]: [apiError(404, "NOT_FOUND")] });
    fireEvent.click(button("Опубликовать"));
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
  });

  test("401 on an action redirects to /login", async () => {
    await renderEdit({}, { [`POST /projects/${ID}/publish`]: [apiError(401, "UNAUTHORIZED")] });
    fireEvent.click(button("Опубликовать"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("a second click during publish sends nothing", async () => {
    const reply = deferred();
    await renderEdit({}, { [`POST /projects/${ID}/publish`]: [reply.promise] });
    fireEvent.click(button("Опубликовать"));
    fireEvent.click(button("Опубликовать"));
    expect(calls(`POST /projects/${ID}/publish`)).toHaveLength(1);
    expect(button("Сохранить").disabled).toBe(true);
    expect(field("Роль").readOnly).toBe(true);
    expect(button("Добавить").disabled).toBe(true);
    await act(async () =>
      reply.resolve(Response.json({ ...PROJECT, status: "PUBLISHED", visibility: "PUBLIC" })),
    );
    expect(field("Роль").readOnly).toBe(false);
  });
});

describe("after an import", () => {
  const GITHUB = {
    github_repo_id: 1296269,
    full_name: "ann/payments",
    html_url: "https://github.com/ann/payments",
    description: null,
    languages: [],
    pushed_at: null,
    is_fork: false,
    parent_full_name: null,
    is_archived: false,
    relation: "OWNER" as const,
    unavailable: false,
    synced_at: null,
    sync: { status: "NOT_SYNCED" as const, last_success_at: null, next_manual_sync_at: null },
  };
  const IMPORTED: ProjectResponse = {
    ...PROJECT,
    title: "payments",
    summary: null,
    technologies: [],
    github: GITHUB,
  };
  const NOTICE =
    "Из репозитория ann/payments создан черновик «payments». Заполните «Коротко о проекте», " +
    "«Роль», «Ваш вклад» и «Технологии», чтобы опубликовать его.";

  async function renderImported(imported: boolean, project = IMPORTED) {
    window.history.replaceState(null, "", `/me/projects/${ID}${imported ? "?imported=1" : ""}`);
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [Response.json(project)],
      [`PATCH /projects/${ID}`]: [Response.json({ ...project, role: "Dev" })],
    });
    const view = render(<ProjectEditScreen projectId={ID} imported={imported} />);
    await screen.findByRole("form", { name: "Проект" });
    return view;
  }

  afterEach(() => {
    window.history.replaceState(null, "", "/");
  });

  test("the form shows «Проект создан» and removes the marker from the address", async () => {
    await renderImported(true);
    const notice = screen.getByText("Проект создан").closest('[role="status"]')!;
    expect(within(notice as HTMLElement).getByText(NOTICE)).toBeTruthy();
    expect(window.location.pathname).toBe(`/me/projects/${ID}`);
    expect(window.location.search).toBe("");
  });

  test("the panel is shown once: opened again without the marker, there is none", async () => {
    const view = await renderImported(true);
    expect(screen.getByText("Проект создан")).toBeTruthy();
    view.unmount();
    // A reload reads the cleaned address.
    await renderImported(new URLSearchParams(window.location.search).get("imported") === "1");
    expect(screen.queryByText("Проект создан")).toBeNull();
  });

  test("the next save closes the panel", async () => {
    await renderImported(true);
    type("Роль", "Dev");
    fireEvent.click(button("Сохранить"));
    await screen.findByText("Сохранено");
    expect(screen.queryByText("Проект создан")).toBeNull();
  });

  test("without a linked repository the marker shows nothing", async () => {
    await renderImported(true, { ...IMPORTED, github: null });
    expect(screen.queryByText("Проект создан")).toBeNull();
  });
});
