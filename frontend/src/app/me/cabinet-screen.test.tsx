import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CabinetScreen } from "./cabinet-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  // Stable like the real router: a new object per render would re-run effects.
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();

type Profile = {
  slug: string;
  status: "PRIVATE" | "PUBLISHED";
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
};

const PROFILE: Profile = {
  slug: "ann",
  status: "PRIVATE",
  display_name: "Ann",
  headline: null,
  bio: null,
  location: "Berlin",
  avatar_url: null,
  github_login: "ann-gh",
};

function apiError(status: number, code: string, requestId: string, details = {}) {
  return Response.json({ error: { code, message: code, details, request_id: requestId } }, { status });
}

/** A fetch result the test resolves later. */
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

async function renderCabinet(profile: Partial<Profile> = {}) {
  fetchMock.mockResolvedValueOnce(Response.json({ ...PROFILE, ...profile }));
  render(<CabinetScreen />);
  await screen.findByRole("form", { name: "Профиль" });
}

const field = (name: string) => screen.getByRole("textbox", { name }) as HTMLInputElement;
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;
const type = (name: string, value: string) => fireEvent.change(field(name), { target: { value } });
const lastRequest = () => fetchMock.mock.calls.at(-1)!;

describe("loading", () => {
  test("shows loading while GET /profile is in flight", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<CabinetScreen />);

    expect(screen.getByRole("status").textContent).toBe("Загрузка…");
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/profile");
  });

  test("200 shows the header, the status and the stored values", async () => {
    await renderCabinet();

    expect(screen.getByText("@ann-gh")).toBeTruthy();
    expect(screen.getByText("Источник: GitHub")).toBeTruthy();
    expect(screen.getByText("Черновик · PRIVATE")).toBeTruthy();
    expect(field("Имя").value).toBe("Ann");
    expect(field("Заголовок").value).toBe("");
    expect(field("Локация").value).toBe("Berlin");
    expect(field("О себе").value).toBe("");
  });

  test("401 redirects to /login", async () => {
    fetchMock.mockResolvedValue(apiError(401, "UNAUTHORIZED", "r-1"));
    render(<CabinetScreen />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a network error offers a retry that loads again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<CabinetScreen />);

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );

    fetchMock.mockResolvedValueOnce(Response.json(PROFILE));
    fireEvent.click(button("Повторить"));

    await screen.findByRole("form", { name: "Профиль" });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("another API error shows the generic text with the request id", async () => {
    fetchMock.mockResolvedValue(apiError(500, "INTERNAL_ERROR", "r-500"));
    render(<CabinetScreen />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-500");
    expect(button("Повторить")).toBeTruthy();
  });
});

describe("form", () => {
  test("fields carry the API limits and counters", async () => {
    await renderCabinet();

    expect(field("Имя").maxLength).toBe(100);
    expect(field("Заголовок").maxLength).toBe(160);
    expect(field("Локация").maxLength).toBe(100);
    expect(field("О себе").maxLength).toBe(2000);
    expect(field("О себе").tagName).toBe("TEXTAREA");
    expect(document.getElementById("profile-display_name-count")?.textContent).toBe("3 / 100");
    expect(document.getElementById("profile-headline-count")?.textContent).toBe("0 / 160");

    type("Заголовок", "Backend");

    expect(document.getElementById("profile-headline-count")?.textContent).toBe("7 / 160");
  });

  test("«Сохранить» is enabled only while something changed", async () => {
    await renderCabinet();
    expect(button("Сохранить").disabled).toBe(true);

    type("Имя", "Anna");
    expect(button("Сохранить").disabled).toBe(false);

    type("Имя", "Ann");
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("PATCH sends only the changed fields; the form then shows the response", async () => {
    await renderCabinet();
    type("Заголовок", "  Backend  ");
    type("Локация", "");
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...PROFILE, headline: "Backend", location: null }),
    );

    fireEvent.click(button("Сохранить"));

    expect(await screen.findByText("Сохранено")).toBeTruthy();
    const [url, init] = lastRequest();
    expect(url).toBe("http://api.test/api/v1/profile");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(init?.body as string)).toEqual({ headline: "  Backend  ", location: null });
    expect(field("Заголовок").value).toBe("Backend");
    expect(field("Локация").value).toBe("");
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("«Сохранить» is disabled during the request and a double click sends once", async () => {
    await renderCabinet();
    type("Имя", "Anna");
    const response = deferred();
    fetchMock.mockReturnValueOnce(response.promise);

    fireEvent.click(button("Сохранить"));
    fireEvent.click(button("Сохранить"));
    fireEvent.submit(screen.getByRole("form", { name: "Профиль" }));

    expect(button("Сохранить").disabled).toBe(true);
    expect(button("Опубликовать").disabled).toBe(true);
    expect(field("Имя").readOnly).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await act(async () => response.resolve(Response.json({ ...PROFILE, display_name: "Anna" })));
    expect(field("Имя").readOnly).toBe(false);
  });

  test("422 VALIDATION_ERROR is shown at the fields", async () => {
    await renderCabinet();
    type("Имя", "Anna");
    type("О себе", "text");
    fetchMock.mockResolvedValueOnce(
      apiError(422, "VALIDATION_ERROR", "r-422", {
        fields: [
          { loc: ["body", "display_name"], type: "string_too_long" },
          { loc: ["body", "bio"], type: "control_characters" },
        ],
      }),
    );

    fireEvent.click(button("Сохранить"));

    await waitFor(() => expect(field("Имя").getAttribute("aria-invalid")).toBe("true"));
    expect(document.getElementById("profile-display_name-error")?.textContent).toBe(
      "Не больше 100 символов.",
    );
    expect(document.getElementById("profile-bio-error")?.textContent).toBe(
      "Недопустимые символы.",
    );
    expect(field("Заголовок").getAttribute("aria-invalid")).toBeNull();
    expect(field("Имя").value).toBe("Anna");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("another API error shows the generic text with the request id", async () => {
    await renderCabinet();
    type("Имя", "Anna");
    fetchMock.mockResolvedValueOnce(apiError(500, "INTERNAL_ERROR", "r-save"));

    fireEvent.click(button("Сохранить"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-save");
  });

  test("a network error keeps the entered data", async () => {
    await renderCabinet();
    type("Имя", "Anna");
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    fireEvent.click(button("Сохранить"));

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    expect(field("Имя").value).toBe("Anna");
    expect(button("Сохранить").disabled).toBe(false);
  });

  test("PROFILE_INCOMPLETE on save of a published profile names the field", async () => {
    await renderCabinet({ status: "PUBLISHED", headline: "Backend" });
    type("Имя", "");
    fetchMock.mockResolvedValueOnce(
      apiError(422, "PROFILE_INCOMPLETE", "r-inc", { missing_fields: ["display_name"] }),
    );

    fireEvent.click(button("Сохранить"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Нельзя сохранить");
    expect(alert.textContent).toContain("Заполните обязательное поле: «Имя».");
    expect(field("Имя").getAttribute("aria-invalid")).toBe("true");
  });

  test("401 on save redirects to /login", async () => {
    await renderCabinet();
    type("Имя", "Anna");
    fetchMock.mockResolvedValueOnce(apiError(401, "UNAUTHORIZED", "r-401"));

    fireEvent.click(button("Сохранить"));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("publication", () => {
  test("the address is plain text while PRIVATE", async () => {
    await renderCabinet();

    expect(screen.getByText("/u/ann").tagName).toBe("SPAN");
    expect(screen.queryByRole("link", { name: "/u/ann" })).toBeNull();
  });

  test("«Опубликовать» is disabled while the form has unsaved changes", async () => {
    await renderCabinet({ headline: "Backend" });
    expect(button("Опубликовать").disabled).toBe(false);

    type("Имя", "Anna");

    expect(button("Опубликовать").disabled).toBe(true);
    expect(screen.getByText("Сохраните изменения, чтобы опубликовать профиль.")).toBeTruthy();
  });

  test("PROFILE_INCOMPLETE lists the missing fields and highlights them", async () => {
    await renderCabinet({ display_name: null });
    fetchMock.mockResolvedValueOnce(
      apiError(422, "PROFILE_INCOMPLETE", "r-inc", {
        missing_fields: ["display_name", "headline"],
      }),
    );

    fireEvent.click(button("Опубликовать"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Нельзя опубликовать");
    expect(alert.textContent).toContain("Заполните обязательные поля: «Имя» и «Заголовок».");
    expect(field("Имя").getAttribute("aria-invalid")).toBe("true");
    expect(field("Заголовок").getAttribute("aria-invalid")).toBe("true");
    expect(field("Локация").getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByText("Черновик · PRIVATE")).toBeTruthy();
  });

  test("success changes the status and turns the address into a link", async () => {
    await renderCabinet({ headline: "Backend" });
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...PROFILE, headline: "Backend", status: "PUBLISHED" }),
    );

    fireEvent.click(button("Опубликовать"));

    expect(await screen.findByText("В сети · PUBLISHED")).toBeTruthy();
    const [url, init] = lastRequest();
    expect(url).toBe("http://api.test/api/v1/profile/publish");
    expect(init?.method).toBe("POST");
    expect(screen.getByRole("link", { name: "/u/ann" }).getAttribute("href")).toBe("/u/ann");
    expect(button("Опубликовать").disabled).toBe(true);
    expect(button("Скрыть").disabled).toBe(false);
  });

  test("a double click on «Опубликовать» sends once", async () => {
    await renderCabinet({ headline: "Backend" });
    const response = deferred();
    fetchMock.mockReturnValueOnce(response.promise);

    fireEvent.click(button("Опубликовать"));
    fireEvent.click(button("Опубликовать"));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    await act(async () =>
      response.resolve(Response.json({ ...PROFILE, headline: "Backend", status: "PUBLISHED" })),
    );
  });

  test("«Скрыть» is available only in PUBLISHED", async () => {
    await renderCabinet();

    expect(button("Скрыть").disabled).toBe(true);
    expect(screen.getByText("«Скрыть» доступно, когда профиль опубликован.")).toBeTruthy();
  });

  test("«Скрыть» returns the profile to PRIVATE and keeps unsaved edits", async () => {
    await renderCabinet({ status: "PUBLISHED", headline: "Backend" });
    expect(screen.getByText("В сети · PUBLISHED")).toBeTruthy();
    type("О себе", "draft");
    expect(button("Скрыть").disabled).toBe(false);
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...PROFILE, headline: "Backend", status: "PRIVATE" }),
    );

    fireEvent.click(button("Скрыть"));

    expect(await screen.findByText("Черновик · PRIVATE")).toBeTruthy();
    const [url, init] = lastRequest();
    expect(url).toBe("http://api.test/api/v1/profile/unpublish");
    expect(init?.method).toBe("POST");
    expect(field("О себе").value).toBe("draft");
    expect(button("Сохранить").disabled).toBe(false);
    expect(button("Скрыть").disabled).toBe(true);
    expect(screen.queryByRole("link", { name: "/u/ann" })).toBeNull();
  });
});

describe("logout", () => {
  test("204 redirects to /login", async () => {
    await renderCabinet();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    fireEvent.click(button("Выйти"));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    const [url, init] = lastRequest();
    expect(url).toBe("http://api.test/api/v1/auth/logout");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
  });

  test("a failure is shown and the user stays", async () => {
    await renderCabinet();
    fetchMock.mockResolvedValueOnce(apiError(500, "INTERNAL_ERROR", "r-logout"));

    fireEvent.click(button("Выйти"));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Код запроса: r-logout");
    expect(replace).not.toHaveBeenCalled();
    expect(button("Выйти").disabled).toBe(false);
  });
});
