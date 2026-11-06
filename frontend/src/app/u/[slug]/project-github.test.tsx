import { cleanup, render, screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import type { PublicGitHub } from "@/lib/api";

import { CardGitHub, RowGitHub } from "./project-github";

// A zone far from UTC, set before the module under test builds its formatter: CI runs
// in UTC, where a formatter without timeZone would give the same dates.
vi.hoisted(() => {
  process.env.TZ = "Asia/Tokyo";
});

const GITHUB: PublicGitHub = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: "A small shop",
  languages: [
    { name: "Python", bytes: 750 },
    { name: "Shell", bytes: 250 },
  ],
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  synced_at: "2026-11-01T12:00:00Z",
};

const language = (name: string, bytes: number) => ({ name, bytes });

function card(overrides: Partial<PublicGitHub> = {}) {
  return render(<CardGitHub github={{ ...GITHUB, ...overrides }} />).container;
}

function row(overrides: Partial<PublicGitHub> = {}) {
  return render(<RowGitHub github={{ ...GITHUB, ...overrides }} />).container;
}

function languageItems() {
  return within(screen.getByRole("list", { name: "Языки" }))
    .getAllByRole("listitem")
    .map((item) => item.textContent);
}

/** The texts must appear in `container` in this order. */
function expectOrder(container: HTMLElement, texts: string[]) {
  const content = container.textContent ?? "";
  const places = texts.map((text) => content.indexOf(text));
  expect(places).not.toContain(-1);
  expect(places).toEqual([...places].sort((a, b) => a - b));
}

describe("the time zone of this file", () => {
  test("is not UTC, so that the date tests can fail", () => {
    expect(new Intl.DateTimeFormat().resolvedOptions().timeZone).toBe("Asia/Tokyo");
    expect(new Date("2026-10-31T23:59:59Z").getDate()).toBe(1);
  });
});

describe("CardGitHub", () => {
  test("the owner's block in the order of the mockup", () => {
    const container = card({
      is_fork: true,
      parent_full_name: "org/shop",
      languages: ["A", "B", "C", "D"].map((name) => language(name, 10)),
    });

    expectOrder(container, [
      "Источник: GitHub",
      "ann/shop",
      "Владелец репозитория",
      "Форк org/shop",
      "A small shop",
      "Доля кода в байтах, по данным GitHub",
      "A 25 %",
      "Другие — 25 %",
      "Данные GitHub от 01.11.2026",
    ]);
  });

  test("a contributor is named with the source of the fact", () => {
    card({ relation: "CONTRIBUTOR" });

    expect(screen.getByText("В списке контрибьюторов (по данным GitHub)")).toBeTruthy();
    expect(screen.queryByText("Владелец репозитория")).toBeNull();
  });

  test("the root is a div with the line above it, not a section", () => {
    const container = card();
    const root = container.firstElementChild as HTMLElement;

    expect(root.tagName).toBe("DIV");
    expect(root.className).toContain("border-t-4");
    expect(root.className).toContain("border-outline");
    expect(container.querySelector("section")).toBeNull();
  });

  test("the name links to the repository in a new tab, without opener or referrer", () => {
    card();

    const link = screen.getByRole("link", { name: "ann/shop" });
    expect(link.getAttribute("href")).toBe("https://github.com/ann/shop");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  test.each([
    ["javascript:", "javascript:alert(1)"],
    ["a look-alike host", "https://github.com.evil.example/ann/shop"],
    ["http", "http://github.com/ann/shop"],
  ])("an unsafe html_url (%s) stays plain text", (_, url) => {
    const container = card({ html_url: url });

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("ann/shop")).toBeTruthy();
    expect(container.innerHTML).not.toContain(url);
  });

  test("a fork shows its parent", () => {
    card({ is_fork: true, parent_full_name: "org/shop" });

    expect(screen.getByText("Форк org/shop").className).toContain("border-2");
  });

  test("a fork without a parent says only «Форк»", () => {
    const container = card({ is_fork: true, parent_full_name: null });

    expect(screen.getByText("Форк")).toBeTruthy();
    expect(container.textContent).not.toContain("null");
  });

  test("a repository that is not a fork or archived has no chips", () => {
    const container = card({ parent_full_name: "org/shop" });

    expect(container.textContent).not.toContain("Форк");
    expect(container.textContent).not.toContain("В архиве");
  });

  test("an archived repository is marked", () => {
    card({ is_archived: true });

    expect(screen.getByText("В архиве на GitHub").className).toContain("border-2");
  });

  test("the description is cut at two lines and long words wrap", () => {
    card();

    const description = screen.getByText("A small shop");
    expect(description.className).toContain("line-clamp-2");
    expect(description.className).toContain("break-words");
  });

  test.each([
    ["null", null],
    ["empty", ""],
  ])("a %s description hides the line without a stub", (_, description) => {
    const container = card({ description });

    expect(container.querySelector(".line-clamp-2")).toBeNull();
    expect(container.textContent).not.toContain("описани");
  });

  test("the languages have their caption", () => {
    card();

    expect(screen.getByText("Доля кода в байтах, по данным GitHub")).toBeTruthy();
    expect(languageItems()).toEqual(["Python 75 %", "Shell 25 %"]);
  });

  test("no languages hide the list and the caption without a stub", () => {
    const container = card({ languages: [] });

    expect(screen.queryByRole("list")).toBeNull();
    expect(container.textContent).not.toContain("Доля кода");
    expect(container.textContent).not.toContain("не нашёл");
    expect(container.textContent).not.toContain("Другие");
  });

  test("exactly three languages make no «Другие»", () => {
    card({ languages: ["A", "B", "C"].map((name) => language(name, 10)) });

    expect(languageItems()).toEqual(["A 33 %", "B 33 %", "C 33 %"]);
  });

  test("seven languages show three and one «Другие» with the share of the rest", () => {
    card({
      languages: [
        language("A", 400),
        language("B", 300),
        language("C", 200),
        language("D", 40),
        language("E", 30),
        language("F", 20),
        language("G", 10),
      ],
    });

    expect(languageItems()).toEqual(["A 40 %", "B 30 %", "C 20 %", "Другие — 10 %"]);
    expect(screen.getByText("Другие — 10 %").className).toContain("text-text-muted");
  });

  test("a share under half a percent is «<1 %»", () => {
    card({ languages: [language("Python", 9990), language("Shell", 10)] });

    expect(languageItems()).toEqual(["Python 100 %", "Shell <1 %"]);
  });

  test("0 bytes in all show names without shares", () => {
    card({ languages: ["A", "B", "C", "D"].map((name) => language(name, 0)) });

    expect(languageItems()).toEqual(["A", "B", "C", "Другие"]);
  });

  test("a long repository name and a long language wrap", () => {
    const name = `ann/${"w".repeat(120)}`;
    const long = "L".repeat(80);
    card({ full_name: name, languages: [language(long, 10)] });

    expect(screen.getByRole("link", { name }).className).toContain("break-all");
    expect(screen.getByText(`${long} 100 %`).className).toContain("break-all");
  });

  test.each([
    ["the last second of a day", "2026-10-31T23:59:59Z", "31.10.2026"],
    ["the first second of a day", "2026-11-01T00:00:00Z", "01.11.2026"],
  ])("the date is the day in UTC: %s", (_, syncedAt, day) => {
    const container = card({ synced_at: syncedAt });

    expect(container.textContent).toContain(`Данные GitHub от ${day}`);
    const time = container.querySelector("time");
    expect(time?.textContent).toBe(day);
    expect(time?.getAttribute("datetime")).toBe(syncedAt);
  });

  test("text from GitHub stays text", () => {
    const markup = '<img src=x onerror="alert(1)">';
    const container = card({
      full_name: markup,
      description: markup,
      parent_full_name: markup,
      is_fork: true,
      languages: [language(markup, 10)],
    });

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("link", { name: markup })).toBeTruthy();
    expect(screen.getByText(`${markup} 100 %`)).toBeTruthy();
  });

  test("nothing claims a confirmation, and pushed_at is not shown", () => {
    const extra = { pushed_at: "2020-02-03T04:05:06Z" } as Partial<PublicGitHub>;
    for (const relation of ["OWNER", "CONTRIBUTOR"] as const) {
      const text = card({ ...extra, relation, is_fork: true, is_archived: true }).textContent;

      expect(text).not.toMatch(/подтвержд|проверен|верифиц/i);
      expect(text).not.toMatch(/Обновл/i);
      expect(text).not.toContain("2020");
      expect(text).not.toContain("03.02");
      cleanup();
    }
  });

  test("languages are shares, not levels or bars", () => {
    const container = card();

    expect(container.querySelector('[role="progressbar"], [role="meter"], progress')).toBeNull();
    expect(container.textContent).not.toMatch(/уровень|звёзд|stars/i);
  });
});

describe("RowGitHub", () => {
  test("the former row's block in the order of the mockup", () => {
    const container = row({ is_fork: true, parent_full_name: "org/shop", is_archived: true });

    expectOrder(container, [
      "Источник: GitHub",
      "ann/shop",
      "Владелец репозитория",
      "Форк org/shop",
      "В архиве на GitHub",
      "Данные GitHub от 01.11.2026",
    ]);
  });

  test("one wrapping line under a divider, in a div", () => {
    const root = row().firstElementChild as HTMLElement;

    expect(root.tagName).toBe("DIV");
    expect(root.className).toContain("flex-wrap");
    expect(root.className).toContain("border-t-4");
  });

  test("the name is a link", () => {
    row();

    expect(screen.getByRole("link", { name: "ann/shop" }).getAttribute("href")).toBe(
      "https://github.com/ann/shop",
    );
  });

  test("an unsafe html_url stays plain text", () => {
    row({ html_url: "https://github.com.evil.example/ann/shop" });

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("ann/shop")).toBeTruthy();
  });

  test("a contributor, and a fork without a parent", () => {
    const container = row({ relation: "CONTRIBUTOR", is_fork: true });

    expect(screen.getByText("В списке контрибьюторов (по данным GitHub)")).toBeTruthy();
    expect(screen.getByText("Форк")).toBeTruthy();
    expect(container.textContent).not.toContain("null");
  });

  test("the description and the languages are not in a row", () => {
    const container = row();

    expect(container.textContent).not.toContain("A small shop");
    expect(container.textContent).not.toContain("Python");
    expect(container.textContent).not.toContain("Доля кода");
    expect(screen.queryByRole("list")).toBeNull();
  });

  test("the date is the day in UTC in a <time>", () => {
    const container = row({ synced_at: "2026-10-31T23:59:59Z" });

    const time = container.querySelector("time");
    expect(time?.textContent).toBe("31.10.2026");
    expect(time?.getAttribute("datetime")).toBe("2026-10-31T23:59:59Z");
  });

  test("a long repository name wraps", () => {
    const name = `ann/${"w".repeat(120)}`;
    row({ full_name: name });

    expect(screen.getByRole("link", { name }).className).toContain("break-all");
  });
});
