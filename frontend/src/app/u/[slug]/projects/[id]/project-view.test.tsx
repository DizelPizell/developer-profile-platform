import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { PublicGitHub, PublicProjectPage } from "@/lib/api";

import { ProjectView } from "./project-view";

const MEDIA = "/media/projects/p1";

const SHOTS = [
  { url: `${MEDIA}/a.webp`, caption: "Главный экран", width: 1280, height: 800 },
  { url: `${MEDIA}/b.webp`, caption: null, width: 1024, height: 768 },
  { url: `${MEDIA}/c.webp`, caption: "Отчёт", width: 800, height: 600 },
];

const PROJECT: PublicProjectPage = {
  id: "p1",
  title: "Shop",
  summary: "Payments",
  description: "Подробности",
  problem: "Медленная оплата",
  results: "Быстрее",
  role: "Backend",
  contribution: "Первая строка\nВторая строка",
  technologies: ["Python", "FastAPI", "PostgreSQL", "Celery"],
  demo_url: "https://demo.example.com/shop",
  screenshots: SHOTS,
  github: null,
  owner: { slug: "ann", display_name: "Ann Lee" },
};

const GITHUB: PublicGitHub = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: "A small shop",
  languages: [{ name: "Python", bytes: 100 }],
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  synced_at: "2026-11-01T00:00:00Z",
};

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://browser.test");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

function view(changes: Partial<PublicProjectPage> = {}) {
  return render(<ProjectView project={{ ...PROJECT, ...changes }} />).container;
}

function headings(root: Element) {
  return [...root.querySelectorAll("h1, h2")].map((h) => h.textContent);
}

function section(root: Element, title: string) {
  const heading = [...root.querySelectorAll("h2")].find((h) => h.textContent === title);
  return heading?.closest("section") ?? null;
}

describe("the page", () => {
  test("puts the blocks in order: title, demo, screenshots, texts, GitHub", () => {
    expect(headings(view({ github: GITHUB }))).toEqual([
      "Shop",
      "Демо",
      "Скриншоты",
      "Задача",
      "Мой вклад",
      "Результат",
      "Подробнее",
      "Данные GitHub",
    ]);
  });

  test("shows the title block and every technology in order", () => {
    const root = view();
    const technologies = root.querySelector('ul[aria-label="Технологии"]')!;

    expect(root.querySelector("h1")?.textContent).toBe("Shop");
    expect([...technologies.querySelectorAll("li")].map((li) => li.textContent)).toEqual(
      PROJECT.technologies,
    );
    expect(root.textContent).toContain("Моя роль: Backend");
  });

  test("links back to the owner's profile by name", () => {
    expect(view().querySelector('a[href="/u/ann"]')?.textContent).toBe("‹ Ann Lee");
  });

  test("keeps line breaks of a text as text", () => {
    const text = section(view(), "Мой вклад")?.querySelector("p");

    expect(text?.textContent).toBe("Первая строка\nВторая строка");
    expect(text?.className).toContain("whitespace-pre-line");
  });

  test("escapes every value", () => {
    const root = view({ title: "<script>alert(1)</script>", problem: "<img src=x onerror=alert(1)>" });

    expect(root.querySelector("script")).toBeNull();
    expect(root.querySelector('img[src="x"]')).toBeNull();
    expect(root.querySelector("h1")?.textContent).toBe("<script>alert(1)</script>");
  });

  test("hides the empty texts and shows no stubs", () => {
    const shown = headings(view({ problem: null, results: null, description: null }));

    expect(shown).not.toContain("Задача");
    expect(shown).not.toContain("Результат");
    expect(shown).not.toContain("Подробнее");
    expect(shown).toContain("Мой вклад");
  });

  test("without a demo and screenshots has neither section and says nothing about them", () => {
    const root = view({ demo_url: null, screenshots: [] });

    expect(headings(root)).not.toContain("Демо");
    expect(headings(root)).not.toContain("Скриншоты");
    expect(root.textContent).not.toMatch(/нет демо|нет скриншотов/i);
  });
});

describe("the demo block", () => {
  test("is the preview and a link that opens a new tab", () => {
    const demo = section(view(), "Демо")!;
    const link = [...demo.querySelectorAll("a")].find((a) => a.textContent === "Открыть демо ↗");
    const preview = demo.querySelector("img")!;

    expect(link?.getAttribute("href")).toBe("https://demo.example.com/shop");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noopener noreferrer nofollow ugc");
    expect(preview.getAttribute("src")).toBe(`http://browser.test${MEDIA}/a.webp`);
    expect(preview.getAttribute("width")).toBe("1280");
    expect(preview.getAttribute("height")).toBe("800");
    expect(preview.getAttribute("alt")).toBe("Главный экран");
    expect(preview.hasAttribute("loading")).toBe(false);
    expect(preview.closest("a")).toBeNull();
    expect(demo.textContent).toContain("demo.example.com · откроется в новой вкладке");
    expect(demo.textContent).toContain("Ссылку указал автор, платформа сайт демо не проверяет.");
  });

  test("a preview without a caption has the numbered alt", () => {
    const preview = section(view({ screenshots: [SHOTS[1]] }), "Демо")!.querySelector("img");
    expect(preview?.getAttribute("alt")).toBe("Скриншот 1 проекта «Shop»");
  });

  test("without screenshots shows the host instead of the preview", () => {
    const root = view({ screenshots: [] });
    const demo = section(root, "Демо")!;

    expect(demo.querySelector("img")).toBeNull();
    expect(demo.querySelector("p")?.textContent).toBe("demo.example.com");
    expect(headings(root)).not.toContain("Скриншоты");
  });

  test("shows an IDN host as punycode", () => {
    const demo = section(view({ demo_url: "https://пример.рф/demo", screenshots: [] }), "Демо");
    expect(demo?.textContent).toContain("xn--e1afmkfd.xn--p1ai · откроется");
  });
});

describe("screenshots", () => {
  test("with a demo start from the second one, without repeating the preview", () => {
    const images = [...section(view(), "Скриншоты")!.querySelectorAll("img")];

    expect(images.map((img) => img.getAttribute("src"))).toEqual([
      `http://browser.test${MEDIA}/b.webp`,
      `http://browser.test${MEDIA}/c.webp`,
    ]);
  });

  test("with a demo and one screenshot there is no gallery", () => {
    expect(headings(view({ screenshots: [SHOTS[0]] }))).not.toContain("Скриншоты");
  });

  test("without a demo show all, numbered from one", () => {
    const links = [...section(view({ demo_url: null }), "Скриншоты")!.querySelectorAll("a")];

    expect(links.map((a) => a.getAttribute("aria-label"))).toEqual([
      "Открыть скриншот 1 в полном размере",
      "Открыть скриншот 2 в полном размере",
      "Открыть скриншот 3 в полном размере",
    ]);
  });

  test("are lazy links to their file with their size, alt and caption", () => {
    const figures = [...section(view(), "Скриншоты")!.querySelectorAll("figure")];
    const [first, second] = figures.map((figure) => figure.querySelector("img")!);

    expect(first.closest("a")?.getAttribute("href")).toBe(`http://browser.test${MEDIA}/b.webp`);
    expect(first.closest("a")?.getAttribute("target")).toBe("_blank");
    expect(first.closest("a")?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(first.getAttribute("loading")).toBe("lazy");
    expect(first.getAttribute("width")).toBe("1024");
    expect(first.getAttribute("height")).toBe("768");
    expect(first.getAttribute("alt")).toBe("Скриншот 2 проекта «Shop»");
    expect(figures[0].querySelector("figcaption")).toBeNull();
    expect(second.getAttribute("alt")).toBe("Отчёт");
    expect(figures[1].querySelector("figcaption")?.textContent).toBe("Отчёт");
  });

  test("one screenshot is one column, two make two from sm", () => {
    const one = section(view({ demo_url: null, screenshots: [SHOTS[0]] }), "Скриншоты");
    const two = section(view({ demo_url: null, screenshots: SHOTS.slice(0, 2) }), "Скриншоты");

    expect(one?.querySelector("ul")?.className).not.toContain("sm:grid-cols-2");
    expect(two?.querySelector("ul")?.className).toContain("sm:grid-cols-2");
  });
});

describe("the GitHub section", () => {
  test("shows the card block without its divider", () => {
    const github = section(view({ github: GITHUB }), "Данные GitHub")!;

    expect(github.textContent).toContain("ann/shop");
    expect(github.textContent).toContain("Источник: GitHub");
    expect(github.innerHTML).not.toContain("border-t-4");
  });

  test("null shows no section", () => {
    expect(headings(view())).not.toContain("Данные GitHub");
  });
});
