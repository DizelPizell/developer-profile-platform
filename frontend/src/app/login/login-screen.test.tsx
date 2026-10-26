import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { LoginScreen } from "./login-screen";

const navigation = vi.hoisted(() => {
  const replace = vi.fn();
  // Stable like the real router: a new object per render would re-run effects.
  return { replace, router: { replace }, query: "" };
});

vi.mock("next/navigation", () => ({
  useRouter: () => navigation.router,
  useSearchParams: () => new URLSearchParams(navigation.query),
}));

const fetchMock = vi.fn<typeof fetch>();
const LOGIN_URL = "http://api.test/api/v1/auth/github/login";

function unauthorized() {
  return Response.json(
    { error: { code: "UNAUTHORIZED", message: "Authentication required", details: {}, request_id: "r" } },
    { status: 401 },
  );
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(unauthorized());
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  navigation.replace.mockReset();
  navigation.query = "";
});

async function renderSignedOut(query = "") {
  navigation.query = query;
  render(<LoginScreen />);
  return screen.findByRole("link", { name: "Войти через GitHub" });
}

describe("sign-in button", () => {
  test("is disabled while the session is being checked", () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(<LoginScreen />);

    const button = screen.getByRole("button", { name: "Войти через GitHub" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("link")).toBeNull();
  });

  test("without a session links to the API sign-in endpoint", async () => {
    const link = await renderSignedOut();

    expect(link.getAttribute("href")).toBe(LOGIN_URL);
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/auth/me");
    expect(navigation.replace).not.toHaveBeenCalled();
  });

  test("with a session redirects to /me", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ id: "1", github_login: "ann", email: null, profile_slug: "ann" }),
    );
    render(<LoginScreen />);

    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/me"));
  });

  test("an unreachable API keeps the button active and says so", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const link = await renderSignedOut();

    expect(link.getAttribute("href")).toBe(LOGIN_URL);
    expect(screen.getByRole("alert").textContent).toBe("Не удалось связаться с сервером.");
  });
});

describe("?error=", () => {
  test("no parameter, no error block", async () => {
    await renderSignedOut();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test.each([
    ["ACCESS_DENIED", "Вход отменён на стороне GitHub. Попробуйте ещё раз."],
    ["INVALID_STATE", "Сеанс входа устарел или был прерван. Начните вход заново."],
    ["MISSING_CODE", "GitHub не вернул код входа. Начните вход заново."],
    ["OAUTH_CODE_INVALID", "Код входа истёк или уже использован. Начните вход заново."],
    ["GITHUB_UNAVAILABLE", "GitHub сейчас недоступен. Попробуйте позже."],
    ["INTERNAL_ERROR", "Что-то пошло не так на нашей стороне. Попробуйте позже."],
  ])("%s shows its text and keeps the button active", async (code, text) => {
    const link = await renderSignedOut(`error=${code}`);

    expect(screen.getByRole("alert").textContent).toBe(text);
    expect(link.getAttribute("href")).toBe(LOGIN_URL);
  });

  test.each(["SOMETHING_ELSE", "<b>injected</b>", "toString", ""])(
    "unknown value %j shows the neutral text and never the value",
    async (value) => {
      await renderSignedOut(`error=${encodeURIComponent(value)}`);

      expect(screen.getByRole("alert").textContent).toBe("Не удалось войти. Попробуйте ещё раз.");
      if (value) {
        expect(document.body.textContent).not.toContain(value);
        expect(document.body.innerHTML).not.toContain(value);
      }
    },
  );
});
