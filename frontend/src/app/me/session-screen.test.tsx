import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { SessionScreen } from "./session-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  // Stable like the real router: a new object per render would re-run effects.
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const ME = { id: "1", github_login: "ann", email: null, profile_slug: "ann" };

function apiError(status: number, code: string, requestId: string) {
  return Response.json(
    { error: { code, message: code, details: {}, request_id: requestId } },
    { status },
  );
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

async function renderSignedIn() {
  fetchMock.mockResolvedValueOnce(Response.json(ME));
  render(<SessionScreen />);
  return screen.findByRole("button", { name: "Выйти" });
}

describe("loading the session", () => {
  test("shows loading while GET /auth/me is in flight", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<SessionScreen />);

    expect(screen.getByRole("status").textContent).toBe("Загрузка…");
  });

  test("200 shows the GitHub login with its source and the logout button", async () => {
    await renderSignedIn();

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("@ann");
    expect(screen.getByText("Источник: GitHub")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/auth/me");
  });

  test("401 redirects to /login", async () => {
    fetchMock.mockResolvedValue(apiError(401, "UNAUTHORIZED", "r-1"));
    render(<SessionScreen />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("a network error offers a retry that loads again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<SessionScreen />);

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );

    fetchMock.mockResolvedValueOnce(Response.json(ME));
    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));

    expect((await screen.findByRole("heading", { level: 1 })).textContent).toBe("@ann");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("another API error shows the generic text with the request id", async () => {
    fetchMock.mockResolvedValue(apiError(500, "INTERNAL_ERROR", "r-500"));
    render(<SessionScreen />);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-500");
    expect(screen.getByRole("button", { name: "Повторить" })).toBeTruthy();
  });
});

describe("logout", () => {
  test("204 redirects to /login", async () => {
    const button = await renderSignedIn();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    fireEvent.click(button);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("http://api.test/api/v1/auth/logout");
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
  });

  test("a network error is shown and the user stays", async () => {
    const button = await renderSignedIn();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    fireEvent.click(button);

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Не удалось связаться с сервером.",
    );
    expect(replace).not.toHaveBeenCalled();
    expect((screen.getByRole("button", { name: "Выйти" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  test("an API error is shown with the request id", async () => {
    const button = await renderSignedIn();
    fetchMock.mockResolvedValueOnce(apiError(500, "INTERNAL_ERROR", "r-logout"));

    fireEvent.click(button);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Что-то пошло не так. Попробуйте ещё раз.");
    expect(alert.textContent).toContain("Код запроса: r-logout");
    expect(replace).not.toHaveBeenCalled();
  });
});
