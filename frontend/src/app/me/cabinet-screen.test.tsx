import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CabinetScreen } from "./cabinet-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  // Stable like the real router: a new object per render would re-run effects.
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();

type Contact = { type: string; value: string; label: string | null; url: string };

type Profile = {
  slug: string;
  status: "PRIVATE" | "PUBLISHED";
  display_name: string | null;
  headline: string | null;
  bio: string | null;
  location: string | null;
  avatar_url: string | null;
  github_login: string;
  contacts: Contact[];
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
  contacts: [],
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

describe("contacts", () => {
  const EMAIL = { type: "EMAIL", value: "ann@example.com", label: null, url: "mailto:ann@example.com" };
  const TELEGRAM = { type: "TELEGRAM", value: "ann_dev", label: null, url: "https://t.me/ann_dev" };
  const LINKEDIN = {
    type: "LINKEDIN",
    value: "ann-dev",
    label: null,
    url: "https://www.linkedin.com/in/ann-dev",
  };
  const PHONE = { type: "PHONE", value: "+79123456789", label: null, url: "tel:+79123456789" };
  const OTHER = { type: "OTHER", value: "https://a.example/", label: "Blog", url: "https://a.example/" };

  const ADD = "+ Другие способы связи";
  const hint = (id: string) => document.getElementById(`contact-${id}-hint`)?.textContent;
  const error = (id: string) => document.getElementById(`contact-${id}-error`)?.textContent;
  const rowField = (n: number, name: string) =>
    within(screen.getByRole("group", { name: `Другой способ ${n}` })).getByRole("textbox", {
      name,
    }) as HTMLInputElement;
  const sentBody = () => JSON.parse(lastRequest()[1]?.body as string);

  test("a private profile is told that contacts appear after publication", async () => {
    await renderCabinet();

    expect(
      screen.getByText(/^Контакты станут видны на публичной странице после публикации профиля\./),
    ).toBeTruthy();
  });

  test("a published profile is warned that contacts are public at once", async () => {
    await renderCabinet({ status: "PUBLISHED" });

    expect(
      screen.getByText(/^Профиль опубликован: сохранённые контакты сразу видны/),
    ).toBeTruthy();
  });

  test("stored contacts fill the fields, with «Сохранено как» and no counters", async () => {
    await renderCabinet({ contacts: [OTHER, PHONE, LINKEDIN, TELEGRAM, EMAIL] });

    expect(field("Email").value).toBe("ann@example.com");
    expect(field("Telegram").value).toBe("@ann_dev");
    expect(field("LinkedIn").value).toBe("https://www.linkedin.com/in/ann-dev");
    expect(field("Телефон").value).toBe("+79123456789");
    expect(rowField(1, "Название").value).toBe("Blog");
    expect(hint("EMAIL")).toBe("Сохранено как: ann@example.com");
    expect(hint("TELEGRAM")).toBe("Сохранено как: @ann_dev");
    expect(hint("LINKEDIN")).toBe("Сохранено как: in/ann-dev");
    expect(hint("PHONE")).toBe("Сохранено как: +79123456789");
    expect(document.getElementById("contact-EMAIL-count")).toBeNull();
    // The stored order differs from the one the form sends; that alone is no change.
    expect(button("Сохранить").disabled).toBe(true);

    type("Telegram", "@other");

    expect(hint("TELEGRAM")).toBe("Имя пользователя или ссылка t.me/…");
  });

  test("contacts are not sent when only another field changed", async () => {
    await renderCabinet({ contacts: [EMAIL, OTHER] });
    type("Имя", "Anna");
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...PROFILE, display_name: "Anna", contacts: [EMAIL, OTHER] }),
    );

    fireEvent.click(button("Сохранить"));

    expect(await screen.findByText("Сохранено")).toBeTruthy();
    expect(sentBody()).toEqual({ display_name: "Anna" });
  });

  test("the whole list is sent in the page order; the form then shows the response", async () => {
    await renderCabinet();
    type("Email", " Ann@Example.com ");
    type("Телефон", "+7 (912) 345-67-89");
    type("Telegram", "t.me/ann_dev");
    fireEvent.click(button(ADD));
    fireEvent.change(rowField(1, "Название"), { target: { value: "Blog" } });
    fireEvent.change(rowField(1, "Ссылка"), { target: { value: "https://a.example/" } });
    fetchMock.mockResolvedValueOnce(
      Response.json({ ...PROFILE, contacts: [TELEGRAM, EMAIL, PHONE, OTHER] }),
    );

    fireEvent.click(button("Сохранить"));

    expect(await screen.findByText("Сохранено")).toBeTruthy();
    expect(sentBody()).toEqual({
      contacts: [
        { type: "TELEGRAM", value: "t.me/ann_dev" },
        { type: "EMAIL", value: " Ann@Example.com " },
        { type: "PHONE", value: "+7 (912) 345-67-89" },
        { type: "OTHER", value: "https://a.example/", label: "Blog" },
      ],
    });
    expect(field("Email").value).toBe("ann@example.com");
    expect(field("Telegram").value).toBe("@ann_dev");
    expect(field("Телефон").value).toBe("+79123456789");
    expect(button("Сохранить").disabled).toBe(true);
  });

  test("clearing every contact sends an empty list", async () => {
    await renderCabinet({ contacts: [EMAIL, OTHER] });
    type("Email", "  ");
    fireEvent.click(button("Удалить: другой способ 1"));
    fetchMock.mockResolvedValueOnce(Response.json(PROFILE));

    fireEvent.click(button("Сохранить"));

    expect(await screen.findByText("Сохранено")).toBeTruthy();
    expect(sentBody()).toEqual({ contacts: [] });
  });

  test("a stored LinkedIn is sent again as a link the server accepts", async () => {
    await renderCabinet();
    type("LinkedIn", "linkedin.com/in/ann-dev/");
    fetchMock.mockResolvedValueOnce(Response.json({ ...PROFILE, contacts: [LINKEDIN] }));
    fireEvent.click(button("Сохранить"));
    expect(await screen.findByText("Сохранено")).toBeTruthy();

    type("Телефон", "+79123456789");
    fetchMock.mockResolvedValueOnce(Response.json({ ...PROFILE, contacts: [LINKEDIN, PHONE] }));
    fireEvent.click(button("Сохранить"));

    expect(await screen.findByText("Сохранено")).toBeTruthy();
    expect(sentBody()).toEqual({
      contacts: [
        { type: "LINKEDIN", value: "https://www.linkedin.com/in/ann-dev" },
        { type: "PHONE", value: "+79123456789" },
      ],
    });
  });

  test("a server error lands on its field although empty fields were not sent", async () => {
    await renderCabinet();
    type("Email", "ann@example.com");
    type("Телефон", "89123456789");
    fireEvent.click(button(ADD));
    fireEvent.click(button(ADD));
    // Row 1 stays empty and is not sent; row 2 has a link without a name.
    fireEvent.change(rowField(2, "Ссылка"), { target: { value: "javascript:alert(1)" } });
    fetchMock.mockResolvedValueOnce(
      apiError(422, "VALIDATION_ERROR", "r-422", {
        fields: [
          { loc: ["body", "contacts", 1, "value"], type: "invalid_phone" },
          { loc: ["body", "contacts", 2, "value"], type: "invalid_url" },
          { loc: ["body", "contacts", 2, "label"], type: "missing" },
        ],
      }),
    );

    fireEvent.click(button("Сохранить"));

    await waitFor(() => expect(field("Телефон").getAttribute("aria-invalid")).toBe("true"));
    expect(sentBody().contacts.map((item: Contact) => item.type)).toEqual([
      "EMAIL",
      "PHONE",
      "OTHER",
    ]);
    expect(error("PHONE")).toBe("Укажите номер с плюсом, например +79991234567.");
    expect(field("Телефон").getAttribute("aria-describedby")).toContain("contact-PHONE-error");
    expect(error("other-1-url")).toBe("Допустимы только ссылки http и https.");
    expect(error("other-1-label")).toBe("Укажите название.");
    expect(error("other-0-url")).toBeUndefined();
    expect(field("Email").getAttribute("aria-invalid")).toBeNull();
    expect(field("Телефон").value).toBe("89123456789");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test.each([
    [
      "Email",
      "EMAIL",
      "invalid_email",
      "Укажите адрес латиницей: кириллические домены пока не поддерживаются.",
    ],
    [
      "Telegram",
      "TELEGRAM",
      "invalid_telegram",
      "Нужно имя пользователя или ссылка на профиль, а не приглашение.",
    ],
    [
      "LinkedIn",
      "LINKEDIN",
      "invalid_linkedin",
      "Нужна ссылка на профиль вида linkedin.com/in/имя.",
    ],
  ])("%s shows the text of its error type", async (name, id, errorType, text) => {
    await renderCabinet();
    type(name, "x");
    fetchMock.mockResolvedValueOnce(
      apiError(422, "VALIDATION_ERROR", "r-422", {
        fields: [{ loc: ["body", "contacts", 0, "value"], type: errorType }],
      }),
    );

    fireEvent.click(button("Сохранить"));

    await waitFor(() => expect(error(id)).toBe(text));
  });

  test("a list error is shown as the generic error", async () => {
    await renderCabinet();
    type("Email", "ann@example.com");
    fetchMock.mockResolvedValueOnce(
      apiError(422, "VALIDATION_ERROR", "r-list", {
        fields: [{ loc: ["body", "contacts"], type: "duplicate_contact_type" }],
      }),
    );

    fireEvent.click(button("Сохранить"));

    expect((await screen.findByRole("alert")).textContent).toContain("Код запроса: r-list");
  });

  test("at most 3 other contacts; empty rows are not a change", async () => {
    await renderCabinet();
    expect(screen.getByText("Добавлено 0 из 3")).toBeTruthy();

    fireEvent.click(button(ADD));
    expect(screen.getByText("Добавлено 1 из 3")).toBeTruthy();
    fireEvent.click(button(ADD));
    fireEvent.click(button(ADD));

    expect(button(ADD).disabled).toBe(true);
    expect(screen.getByText("Максимум 3 других способа связи")).toBeTruthy();
    expect(screen.getAllByRole("group")).toHaveLength(3);
    expect(rowField(1, "Название").maxLength).toBe(40);
    expect(button("Сохранить").disabled).toBe(true);

    fireEvent.click(button("Удалить: другой способ 2"));

    expect(button(ADD).disabled).toBe(false);
    expect(screen.getByText("Добавлено 2 из 3")).toBeTruthy();
  });
});
