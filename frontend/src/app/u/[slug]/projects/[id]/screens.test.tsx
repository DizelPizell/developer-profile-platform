import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import ProjectError from "./error";
import ProjectNotFound from "./not-found";

describe("project 404", () => {
  test("says the project was not found, without a link that would tell why", () => {
    render(<ProjectNotFound />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Проект не найден");
    expect(screen.getByText("Возможно, он скрыт, ещё не опубликован или ссылка неверна.")).toBeTruthy();
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });
});

describe("project error", () => {
  test("shows no technical details and retries", () => {
    const retry = vi.fn();
    const error = Object.assign(new Error("connect ECONNREFUSED 10.0.0.5:8000"), { digest: "123456" });
    render(<ProjectError error={error} retry={retry} />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Не удалось загрузить проект");
    expect(document.body.textContent).not.toContain("ECONNREFUSED");
    expect(document.body.textContent).not.toContain("123456");

    fireEvent.click(screen.getByRole("button", { name: "Повторить" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });
});
