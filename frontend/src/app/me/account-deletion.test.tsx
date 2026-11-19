import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { AccountDeletion } from "./account-deletion";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();

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

function apiError(status: number, code: string, requestId: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: requestId } },
    { status },
  );
}

async function openDialog() {
  render(<AccountDeletion githubLogin="Ann-GH" />);
  fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт" }));
  return screen.findByRole("alertdialog", { name: "Удалить аккаунт?" });
}

const confirmButton = (dialog: HTMLElement) =>
  within(dialog).getByRole("button", { name: "Удалить навсегда" }) as HTMLButtonElement;

function typeLogin(dialog: HTMLElement, value: string) {
  fireEvent.change(within(dialog).getByRole("textbox"), { target: { value } });
}

describe("the section", () => {
  test("says what goes and links the data policy", () => {
    render(<AccountDeletion githubLogin="ann-gh" />);

    const section = screen.getByRole("region", { name: "Удаление аккаунта" });
    expect(section.textContent).toContain("Отменить нельзя.");
    expect(within(section).getByRole("link", { name: "политике данных" }).getAttribute("href")).toBe(
      "/privacy",
    );
  });
});

describe("the dialog", () => {
  test("asks for the login and links the GitHub settings", async () => {
    const dialog = await openDialog();

    expect(within(dialog).getByLabelText("Введите логин «Ann-GH», чтобы подтвердить")).toBeTruthy();
    const github = within(dialog).getByRole("link", { name: "настройках GitHub" });
    expect(github.getAttribute("href")).toBe("https://github.com/settings/applications");
    expect(github.getAttribute("rel")).toBe("noopener noreferrer");
    expect(confirmButton(dialog).disabled).toBe(true);
  });

  test("stays disabled for another login and sends nothing on Enter", async () => {
    const dialog = await openDialog();
    typeLogin(dialog, "ann");

    expect(confirmButton(dialog).disabled).toBe(true);
    fireEvent.submit(within(dialog).getByRole("textbox"));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("cancel sends nothing and clears the login", async () => {
    let dialog = await openDialog();
    typeLogin(dialog, "Ann-GH");
    fireEvent.click(within(dialog).getByRole("button", { name: "Отмена" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Удалить аккаунт" }));
    dialog = await screen.findByRole("alertdialog");
    expect((within(dialog).getByRole("textbox") as HTMLInputElement).value).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("the login in any case sends DELETE /auth/me once and leaves for /login", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const dialog = await openDialog();
    typeLogin(dialog, "  ann-gh ");

    fireEvent.click(confirmButton(dialog));
    const busy = within(dialog).getByRole("button", { name: "Удаляем…" }) as HTMLButtonElement;
    expect(busy.disabled).toBe(true);
    fireEvent.click(busy);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/auth/me");
    expect(init?.method).toBe("DELETE");
  });

  test("an error stays in the dialog with the request id", async () => {
    fetchMock.mockResolvedValue(apiError(500, "INTERNAL_ERROR", "r-9"));
    const dialog = await openDialog();
    typeLogin(dialog, "Ann-GH");

    fireEvent.click(confirmButton(dialog));

    const alert = await within(dialog).findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-9");
    expect(confirmButton(dialog).disabled).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });

  test("401 leaves for /login", async () => {
    fetchMock.mockResolvedValue(apiError(401, "UNAUTHORIZED", "r-1"));
    const dialog = await openDialog();
    typeLogin(dialog, "Ann-GH");

    fireEvent.click(confirmButton(dialog));

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});
