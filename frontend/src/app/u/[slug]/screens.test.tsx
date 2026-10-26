import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import RootNotFound from "../../not-found";
import ProfileError from "./error";
import ProfileNotFound from "./not-found";

describe("profile 404", () => {
  test("says the profile was not found without telling why", () => {
    render(<ProfileNotFound />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Профиль не найден");
    expect(screen.getByText("Такого профиля нет или он не опубликован. Проверьте ссылку.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "На главную" }).getAttribute("href")).toBe("/");
    expect(screen.getByRole("link", { name: "Создать свой" }).getAttribute("href")).toBe("/login");
  });
});

describe("unknown route 404", () => {
  test("says the page was not found and links to the start page", () => {
    render(<RootNotFound />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Страница не найдена");
    expect(screen.getByRole("link", { name: "На главную" }).getAttribute("href")).toBe("/");
    expect(screen.queryByText(/Профиль/)).toBeNull();
  });
});

describe("profile error", () => {
  test("shows no technical details and retries", () => {
    const retry = vi.fn();
    const error = Object.assign(new Error("connect ECONNREFUSED 10.0.0.5:8000"), {
      digest: "123456",
    });
    render(<ProfileError error={error} retry={retry} />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "Не удалось загрузить профиль",
    );
    expect(document.body.textContent).not.toContain("ECONNREFUSED");
    expect(document.body.textContent).not.toContain("123456");

    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
