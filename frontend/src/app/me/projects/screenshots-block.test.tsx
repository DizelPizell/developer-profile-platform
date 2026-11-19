import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { ProjectResponse, Screenshot } from "@/lib/api";

import { ProjectEditScreen } from "./project-edit-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";
const ID = "p1";

const shot = (n: number, caption: string | null = `Shot ${n}`): Screenshot => ({
  id: `s${n}`,
  url: `/media/projects/${ID}/s${n}.webp`,
  caption,
  width: 1280,
  height: 800,
});

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
  demo_url: null,
  screenshots: [],
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
  contacts: [],
};

const list = (...items: Screenshot[]) => Response.json({ items });

function apiError(status: number, code: string, details = {}) {
  return Response.json({ error: { code, message: code, details, request_id: "r-9" } }, { status });
}

const fileError = (type: string, field = "file") =>
  apiError(422, "VALIDATION_ERROR", { fields: [{ loc: ["body", field], type }] });

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
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  replace.mockReset();
});

async function renderEdit(project: Partial<ProjectResponse> = {}, extra: Record<string, Reply[]> = {}) {
  routes({
    "GET /profile": [Response.json(PROFILE)],
    [`GET /projects/${ID}`]: [Response.json({ ...PROJECT, ...project })],
    ...extra,
  });
  render(<ProjectEditScreen projectId={ID} />);
  await screen.findByRole("form", { name: "Проект" });
}

const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const caption = (n: number) =>
  screen.getByRole("textbox", { name: `Подпись к скриншоту ${n}` }) as HTMLInputElement;
const fileInput = () => screen.getByLabelText("Файл скриншота") as HTMLInputElement;
const status = () => within(screen.getByRole("region", { name: "Демо и скриншоты" })).getAllByRole("status").at(-1)!;
const rows = () => within(screen.getByRole("list", { name: "Скриншоты проекта" })).getAllByRole("listitem");

function pick(file: File) {
  fireEvent.change(fileInput(), { target: { files: [file] } });
}

const png = (bytes = 10, name = "shot.png", type = "image/png") =>
  new File([new Uint8Array(bytes)], name, { type });

describe("states", () => {
  test("a new project shows only the note", async () => {
    routes({ "GET /profile": [Response.json(PROFILE)] });
    render(<ProjectEditScreen />);
    await screen.findByRole("form", { name: "Проект" });
    expect(screen.getByText("Скриншоты можно добавить после первого сохранения.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Добавить скриншот" })).toBeNull();
  });

  test("an empty list shows the placeholder, the counter and the note about direct links", async () => {
    await renderEdit();
    expect(screen.getByText("[Пока нет скриншотов]")).toBeTruthy();
    expect(screen.getByText("Скриншотов: 0 из 6")).toBeTruthy();
    expect(screen.getByText(/даже пока проект — черновик/)).toBeTruthy();
    expect(button("Добавить скриншот").disabled).toBe(false);
    expect(fileInput().accept).toBe("image/jpeg,image/png,image/webp");
  });

  test("rows show the thumbnail from the API origin, the caption and the preview label", async () => {
    await renderEdit({ demo_url: "https://demo.test", screenshots: [shot(1), shot(2, null)] });
    const [first, second] = rows();
    const img = within(first).getByRole("img") as HTMLImageElement;
    expect(img.src).toBe(`http://api.test/media/projects/${ID}/s1.webp`);
    expect(img.alt).toBe("Shot 1");
    expect(within(second).getByRole("img").getAttribute("alt")).toBe("Скриншот 2");
    expect(within(first).getByText("Превью демо")).toBeTruthy();
    expect(within(second).queryByText("Превью демо")).toBeNull();
    expect(button("Выше: скриншот 1").disabled).toBe(true);
    expect(button("Ниже: скриншот 2").disabled).toBe(true);
    expect(caption(1).value).toBe("Shot 1");
  });

  test("without a demo link there is no preview label", async () => {
    await renderEdit({ screenshots: [shot(1)] });
    expect(screen.queryByText("Превью демо")).toBeNull();
  });

  test("a foreign url never reaches an img", async () => {
    await renderEdit({ screenshots: [{ ...shot(1), url: "https://evil.test/x.webp" }] });
    expect(within(rows()[0]).queryByRole("img")).toBeNull();
  });

  test("at 6 the upload button is disabled with the limit text", async () => {
    await renderEdit({ screenshots: [1, 2, 3, 4, 5, 6].map((n) => shot(n)) });
    expect(button("Добавить скриншот").disabled).toBe(true);
    expect(screen.getByText("Можно добавить не больше 6 скриншотов.")).toBeTruthy();
  });
});

describe("upload", () => {
  test("posts the file, shows the list, keeps unsaved edits and focuses the new caption", async () => {
    const reply = deferred();
    await renderEdit({ screenshots: [shot(1)] }, { [`POST /projects/${ID}/screenshots`]: [reply.promise] });
    fireEvent.change(screen.getByRole("textbox", { name: "Название" }), { target: { value: "Edited" } });

    pick(png());
    expect(button("Загружаем…").disabled).toBe(true);
    expect(status().textContent).toBe("Загружаем скриншот…");
    expect(button("Сохранить").disabled).toBe(true);
    pick(png());

    await act(async () => reply.resolve(list(shot(1), shot(2, null))));
    expect(calls(`POST /projects/${ID}/screenshots`)).toHaveLength(1);
    const form = calls(`POST /projects/${ID}/screenshots`)[0][1]!.body as FormData;
    expect(form.get("file")).toBeInstanceOf(File);
    expect(rows()).toHaveLength(2);
    expect(screen.getByText("Скриншотов: 2 из 6")).toBeTruthy();
    expect(status().textContent).toBe("Скриншот добавлен.");
    await waitFor(() => expect(document.activeElement).toBe(caption(2)));
    expect((screen.getByRole("textbox", { name: "Название" }) as HTMLInputElement).value).toBe("Edited");
    expect(button("Сохранить").disabled).toBe(false);
  });

  test.each([
    ["over 5 MB", png(5 * 1024 * 1024 + 1, "big.png"), "Файл больше 5 МБ."],
    ["another type", png(10, "doc.gif", "image/gif"), "Подходят JPEG, PNG и WebP."],
  ])("a file %s is rejected without a request", async (_case, file, text) => {
    await renderEdit();
    pick(file);
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText(file.name)).toBeTruthy();
    expect(calls(`POST /projects/${ID}/screenshots`)).toHaveLength(0);
  });

  test("a file the browser cannot type goes to the server", async () => {
    await renderEdit({}, { [`POST /projects/${ID}/screenshots`]: [list(shot(1))] });
    pick(png(10, "shot", ""));
    await screen.findByText("Скриншот добавлен.");
  });

  test.each([
    ["invalid_image", fileError("invalid_image"), "Не получилось прочитать картинку. Подходят JPEG, PNG и WebP."],
    ["image_too_large", fileError("image_too_large"), "Файл больше 5 МБ."],
    ["too_many_pixels", fileError("too_many_pixels"), "Слишком большое изображение: не больше 40 мегапикселей."],
    ["413 from Nginx", new Response("<html>413</html>", { status: 413 }), "Файл больше 5 МБ."],
  ])("%s is shown under the button with the file name", async (_case, response, text) => {
    await renderEdit({}, { [`POST /projects/${ID}/screenshots`]: [response] });
    pick(png(10, "panorama.png"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(text);
    expect(alert.textContent).toContain("panorama.png");
  });

  test("SCREENSHOT_LIMIT_REACHED reloads the list", async () => {
    const six = [1, 2, 3, 4, 5, 6].map((n) => shot(n));
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [Response.json(PROJECT), Response.json({ ...PROJECT, screenshots: six })],
      [`POST /projects/${ID}/screenshots`]: [apiError(409, "SCREENSHOT_LIMIT_REACHED", { limit: 6 })],
    });
    render(<ProjectEditScreen projectId={ID} />);
    await screen.findByRole("form", { name: "Проект" });
    pick(png());
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Можно добавить не больше 6 скриншотов. Список загружен заново.",
    );
    expect(rows()).toHaveLength(6);
  });

  test("another error shows the request id", async () => {
    await renderEdit({}, { [`POST /projects/${ID}/screenshots`]: [apiError(500, "INTERNAL_ERROR")] });
    pick(png());
    expect((await screen.findByRole("alert")).textContent).toContain("Код запроса: r-9");
  });

  test("401 redirects to /login", async () => {
    await renderEdit({}, { [`POST /projects/${ID}/screenshots`]: [apiError(401, "UNAUTHORIZED")] });
    pick(png());
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("caption", () => {
  test("«Сохранить подпись» is active only for a change and sends null for an empty caption", async () => {
    await renderEdit(
      { screenshots: [shot(1)] },
      { [`PATCH /projects/${ID}/screenshots/s1`]: [list(shot(1, null))] },
    );
    expect(button("Сохранить подпись").disabled).toBe(true);
    fireEvent.change(caption(1), { target: { value: "" } });
    expect(screen.getByText("0 / 200")).toBeTruthy();
    fireEvent.click(button("Сохранить подпись"));
    await screen.findByText("Подпись сохранена.");
    expect(JSON.parse(calls(`PATCH /projects/${ID}/screenshots/s1`)[0][1]!.body as string)).toEqual({
      caption: null,
    });
    expect(button("Сохранить подпись").disabled).toBe(true);
  });

  test("Enter saves the caption, not the project form", async () => {
    await renderEdit(
      { screenshots: [shot(1)] },
      { [`PATCH /projects/${ID}/screenshots/s1`]: [list(shot(1, "New"))] },
    );
    fireEvent.change(caption(1), { target: { value: "New" } });
    fireEvent.keyDown(caption(1), { key: "Enter" });
    await screen.findByText("Подпись сохранена.");
    expect(calls(`PATCH /projects/${ID}`)).toHaveLength(0);
  });

  test("a caption error is shown under its row", async () => {
    await renderEdit(
      { screenshots: [shot(1), shot(2)] },
      { [`PATCH /projects/${ID}/screenshots/s2`]: [fileError("control_characters", "caption")] },
    );
    fireEvent.change(caption(2), { target: { value: "bad" } });
    fireEvent.click(within(rows()[1]).getByRole("button", { name: "Сохранить подпись" }));
    const alert = await within(rows()[1]).findByRole("alert");
    expect(alert.textContent).toBe("Недопустимые символы.");
    expect(caption(2).value).toBe("bad");
  });
});

describe("order", () => {
  test("a move sends the whole set and keeps the focus on the arrow in its new place", async () => {
    await renderEdit(
      { screenshots: [shot(1), shot(2), shot(3)] },
      { [`POST /projects/${ID}/screenshots/reorder`]: [list(shot(2), shot(1), shot(3))] },
    );
    fireEvent.change(caption(1), { target: { value: "Draft" } });
    fireEvent.click(button("Ниже: скриншот 1"));
    await screen.findByText("Порядок изменён.");
    expect(
      JSON.parse(calls(`POST /projects/${ID}/screenshots/reorder`)[0][1]!.body as string),
    ).toEqual({ screenshot_ids: ["s2", "s1", "s3"] });
    await waitFor(() => expect(document.activeElement).toBe(button("Ниже: скриншот 2")));
    // The unsaved caption moved with its screenshot.
    expect(caption(2).value).toBe("Draft");
  });

  test("at an edge the focus goes to the other arrow", async () => {
    await renderEdit(
      { screenshots: [shot(1), shot(2)] },
      { [`POST /projects/${ID}/screenshots/reorder`]: [list(shot(2), shot(1))] },
    );
    fireEvent.click(button("Выше: скриншот 2"));
    await screen.findByText("Порядок изменён.");
    await waitFor(() => expect(document.activeElement).toBe(button("Ниже: скриншот 1")));
  });

  test("SCREENSHOT_ORDER_MISMATCH reloads the list", async () => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [
        Response.json({ ...PROJECT, screenshots: [shot(1), shot(2)] }),
        Response.json({ ...PROJECT, screenshots: [shot(1), shot(2), shot(3)] }),
      ],
      [`POST /projects/${ID}/screenshots/reorder`]: [apiError(409, "SCREENSHOT_ORDER_MISMATCH")],
    });
    render(<ProjectEditScreen projectId={ID} />);
    await screen.findByRole("form", { name: "Проект" });
    fireEvent.click(button("Ниже: скриншот 1"));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Список скриншотов изменился, порядок загружен заново.",
    );
    expect(rows()).toHaveLength(3);
  });
});

describe("delete", () => {
  test("asks first, deletes and moves the focus to the next row", async () => {
    await renderEdit(
      { screenshots: [shot(1), shot(2)] },
      { [`DELETE /projects/${ID}/screenshots/s1`]: [list(shot(2))] },
    );
    fireEvent.click(button("Удалить скриншот 1"));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Файл удалится навсегда. Отменить нельзя.")).toBeTruthy();
    expect(calls(`DELETE /projects/${ID}/screenshots/s1`)).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole("button", { name: "Удалить" }));
    await screen.findByText("Скриншот удалён.");
    expect(rows()).toHaveLength(1);
    await waitFor(() => expect(document.activeElement).toBe(button("Удалить скриншот 1")));
  });

  test("«Отмена» sends nothing", async () => {
    await renderEdit({ screenshots: [shot(1)] });
    fireEvent.click(button("Удалить скриншот 1"));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Отмена" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(calls(`DELETE /projects/${ID}/screenshots/s1`)).toHaveLength(0);
  });

  test("the last one gone, the focus goes to «Добавить скриншот»", async () => {
    await renderEdit({ screenshots: [shot(1)] }, { [`DELETE /projects/${ID}/screenshots/s1`]: [list()] });
    fireEvent.click(button("Удалить скриншот 1"));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Удалить" }));
    await screen.findByText("[Пока нет скриншотов]");
    await waitFor(() => expect(document.activeElement).toBe(button("Добавить скриншот")));
  });
});

describe("404", () => {
  test("a missing screenshot reloads the list", async () => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [
        Response.json({ ...PROJECT, screenshots: [shot(1)] }),
        Response.json(PROJECT),
      ],
      [`DELETE /projects/${ID}/screenshots/s1`]: [apiError(404, "NOT_FOUND")],
    });
    render(<ProjectEditScreen projectId={ID} />);
    await screen.findByRole("form", { name: "Проект" });
    fireEvent.click(button("Удалить скриншот 1"));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Удалить" }));
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Скриншот не найден. Список загружен заново.",
    );
    expect(screen.getByText("[Пока нет скриншотов]")).toBeTruthy();
  });

  test("a missing project shows «Проект не найден»", async () => {
    routes({
      "GET /profile": [Response.json(PROFILE)],
      [`GET /projects/${ID}`]: [Response.json(PROJECT), apiError(404, "NOT_FOUND")],
      [`POST /projects/${ID}/screenshots`]: [apiError(404, "NOT_FOUND")],
    });
    render(<ProjectEditScreen projectId={ID} />);
    await screen.findByRole("form", { name: "Проект" });
    pick(png());
    expect(await screen.findByRole("heading", { name: "Проект не найден" })).toBeTruthy();
  });
});
