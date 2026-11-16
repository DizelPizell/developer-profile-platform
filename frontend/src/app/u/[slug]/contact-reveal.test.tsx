import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ContactReveal } from "./contact-reveal";

const fetchMock = vi.fn<typeof fetch>();
let warn: ReturnType<typeof vi.spyOn>;

const EMAIL = { type: "EMAIL", value: "ann@example.com", url: "mailto:ann@example.com" };

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
  warn = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  warn.mockRestore();
});

const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

describe("ContactReveal", () => {
  test("at rest it is a button and nothing is requested", () => {
    render(<ContactReveal type="EMAIL" slug="ann" />);

    expect(button("Показать email").disabled).toBe(false);
    expect(screen.getByRole("status").textContent).toBe("");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("a click requests the type; the button waits, then the link takes the focus", async () => {
    let resolve!: (response: Response) => void;
    fetchMock.mockReturnValue(new Promise((r) => (resolve = r)));
    render(<ContactReveal type="EMAIL" slug="ann" />);

    fireEvent.click(button("Показать email"));

    expect(button("Загрузка…").disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toBe("Загрузка…");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/api/v1/public/profiles/ann/contacts?type=EMAIL");
    expect(init?.cache).toBe("no-store");

    await act(async () => resolve(Response.json(EMAIL)));

    const link = screen.getByRole("link", { name: "ann@example.com" });
    expect(link.getAttribute("href")).toBe("mailto:ann@example.com");
    expect(link.hasAttribute("target")).toBe(false);
    expect(document.activeElement).toBe(link);
    expect(screen.queryByRole("button")).toBeNull();
  });

  test("a phone is shown as a tel: link", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ type: "PHONE", value: "+79123456789", url: "tel:+79123456789" }),
    );
    render(<ContactReveal type="PHONE" slug="ann" />);

    fireEvent.click(button("Показать телефон"));

    const link = await screen.findByRole("link", { name: "+79123456789" });
    expect(link.getAttribute("href")).toBe("tel:+79123456789");
  });

  test("a failure is announced and «Повторить» asks again", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<ContactReveal type="EMAIL" slug="ann" />);

    fireEvent.click(button("Показать email"));

    expect((await screen.findByText("Не удалось получить email.")).getAttribute("role")).toBe(
      "status",
    );
    expect(screen.queryByRole("button", { name: "Показать email" })).toBeNull();
    expect(warn.mock.calls).toEqual([["Contact EMAIL: request failed"]]);

    fetchMock.mockResolvedValueOnce(Response.json(EMAIL));
    fireEvent.click(button("Повторить"));

    expect(await screen.findByRole("link", { name: "ann@example.com" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  test("the phone has its own failure text", async () => {
    fetchMock.mockResolvedValue(Response.json({}, { status: 404 }));
    render(<ContactReveal type="PHONE" slug="ann" />);

    fireEvent.click(button("Показать телефон"));

    expect(await screen.findByText("Не удалось получить телефон.")).toBeTruthy();
  });

  test("a wrong answer is a failure: nothing from it is shown, linked or logged", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ type: "EMAIL", value: "SECRET", url: "javascript:alert(1)" }),
    );
    render(<ContactReveal type="EMAIL" slug="ann" />);

    fireEvent.click(button("Показать email"));

    expect(await screen.findByText("Не удалось получить email.")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
    expect(document.body.textContent).not.toContain("SECRET");
    expect(JSON.stringify(warn.mock.calls)).not.toContain("SECRET");
  });
});
