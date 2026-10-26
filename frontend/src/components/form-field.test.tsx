import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { FormField } from "./form-field";

function renderField(props: Partial<Parameters<typeof FormField>[0]> = {}) {
  const onChange = vi.fn();
  render(
    <FormField
      id="name"
      label="Имя"
      hint="Обязательно для публикации"
      value="Ann"
      maxLength={100}
      onChange={onChange}
      {...props}
    />,
  );
  return { onChange };
}

describe("FormField", () => {
  test("labels the input and links the hint and counter", () => {
    renderField({ required: true });

    const input = screen.getByRole("textbox", { name: "Имя" }) as HTMLInputElement;
    expect(input.tagName).toBe("INPUT");
    expect(input.value).toBe("Ann");
    expect(input.maxLength).toBe(100);
    expect(input.getAttribute("aria-invalid")).toBeNull();
    expect(input.getAttribute("aria-describedby")).toBe("name-hint name-count");
    expect(document.getElementById("name-count")?.textContent).toBe("3 / 100");
    expect(document.getElementById("name-hint")?.textContent).toBe("Обязательно для публикации");
  });

  test("reports the new value", () => {
    const { onChange } = renderField();

    fireEvent.change(screen.getByRole("textbox", { name: "Имя" }), { target: { value: "Anna" } });

    expect(onChange).toHaveBeenCalledWith("Anna");
  });

  test("an error is shown under the field and marks it invalid", () => {
    renderField({ error: "Не больше 100 символов." });

    const input = screen.getByRole("textbox", { name: "Имя" });
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("name-hint name-count name-error");
    expect(document.getElementById("name-error")?.textContent).toBe("Не больше 100 символов.");
  });

  test("invalid highlights the field without a message", () => {
    renderField({ invalid: true });

    expect(screen.getByRole("textbox", { name: "Имя" }).getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById("name-error")).toBeNull();
  });

  test("multiline renders a textarea with the limit", () => {
    renderField({ multiline: true, maxLength: 2000, value: "" });

    const textarea = screen.getByRole("textbox", { name: "Имя" }) as HTMLTextAreaElement;
    expect(textarea.tagName).toBe("TEXTAREA");
    expect(textarea.maxLength).toBe(2000);
    expect(document.getElementById("name-count")?.textContent).toBe("0 / 2000");
  });
});
