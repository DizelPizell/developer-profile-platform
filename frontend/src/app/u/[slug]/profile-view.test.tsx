import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import type { PublicFeaturedProject, PublicProfile, PublicProject } from "@/lib/api";

import { ProfileView } from "./profile-view";

const PROFILE: PublicProfile = {
  slug: "ann",
  display_name: "Ann Lee",
  headline: "Backend",
  bio: null,
  location: null,
  avatar_url: null,
  github_login: "ann-gh",
  featured: [],
  other: [],
};

function project(id: string, title: string, overrides: Partial<PublicProject> = {}): PublicProject {
  return {
    id,
    title,
    summary: `${title} summary`,
    role: `${title} role`,
    technologies: ["Python"],
    ...overrides,
  };
}

function featured(position: number, title: string, overrides: Partial<PublicProject> = {}) {
  return { ...project(`f${position}`, title, overrides), position } satisfies PublicFeaturedProject;
}

function renderView(profile: Partial<PublicProfile>) {
  return render(<ProfileView profile={{ ...PROFILE, ...profile }} />);
}

function section(name: string) {
  return screen.getByRole("region", { name });
}

/** The cards or rows of a section, not the technology chips inside them. */
function cards(name: string) {
  return [...section(name).querySelectorAll<HTMLElement>(":scope > ol > li, :scope > ul > li")];
}

describe("featured projects", () => {
  test("cards in the given order with the label, title, summary, chips and role", () => {
    renderView({
      featured: [
        featured(1, "Shop", { technologies: ["Python", "FastAPI", "PostgreSQL", "Redis"] }),
        featured(2, "Tracker"),
      ],
    });

    const items = cards("Главные проекты");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByRole("heading", { level: 3 }).textContent).toBe("Shop");
    expect(within(items[1]).getByRole("heading", { level: 3 }).textContent).toBe("Tracker");

    const first = within(items[0]);
    expect(first.getByText("Главный 1")).toBeTruthy();
    expect(first.getByText("Shop summary")).toBeTruthy();
    expect(first.getByText("Моя роль: Shop role")).toBeTruthy();
    const chips = first.getByRole("list", { name: "Технологии" });
    expect(within(chips).getAllByRole("listitem").map((chip) => chip.textContent)).toEqual([
      "Python",
      "FastAPI",
      "PostgreSQL",
    ]);
    expect(within(items[1]).getByText("Главный 2")).toBeTruthy();
  });

  test("no link to a project page and no «Открыть проект»", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(screen.queryByText(/Открыть проект/)).toBeNull();
    const links = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(links).toEqual(["/login", "https://github.com/ann-gh", "#projects"]);
  });

  test("a long title wraps and the summary is limited to four lines", () => {
    const title = "Т".repeat(100);
    const summary = "S".repeat(300);
    renderView({ featured: [featured(1, title, { summary })] });

    const card = within(cards("Главные проекты")[0]);
    expect(card.getByRole("heading", { level: 3 }).className).toContain("break-words");
    const text = card.getByText(summary);
    expect(text.className).toContain("line-clamp-4");
    expect(text.className).toContain("break-words");
  });
});

describe("other projects", () => {
  test("rows in API order with title, one-line summary and only the first technology", () => {
    renderView({
      other: [
        project("o1", "Bot", { technologies: ["TypeScript", "React"] }),
        project("o2", "Site", { technologies: ["HTML"] }),
      ],
    });

    const rows = cards("Другие проекты");
    expect(rows.map((row) => within(row).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "Bot",
      "Site",
    ]);
    const first = within(rows[0]);
    expect(first.getByText("Bot summary").className).toContain("truncate");
    expect(first.getByText("TypeScript")).toBeTruthy();
    expect(first.queryByText("React")).toBeNull();
    expect(first.queryByText(/Моя роль/)).toBeNull();
    expect(within(rows[1]).getByText("HTML")).toBeTruthy();
  });

  test("a row without technologies has no badge", () => {
    renderView({ other: [project("o1", "Bot", { technologies: [] })] });

    const row = cards("Другие проекты")[0];
    expect(row.querySelectorAll("span")).toHaveLength(0);
  });

  test("a long title wraps in a row", () => {
    const title = "W".repeat(100);
    renderView({ other: [project("o1", title)] });

    expect(screen.getByRole("heading", { level: 3, name: title }).className).toContain(
      "break-words",
    );
  });
});

describe("sections", () => {
  test("each section heading carries «От автора»", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(within(section("Главные проекты")).getByText("От автора")).toBeTruthy();
    expect(within(section("Другие проекты")).getByText("От автора")).toBeTruthy();
  });

  test("empty featured hides its section, other stays", () => {
    renderView({ other: [project("o1", "Bot")] });

    expect(screen.queryByRole("region", { name: "Главные проекты" })).toBeNull();
    expect(section("Другие проекты")).toBeTruthy();
  });

  test("empty other hides its section, featured stays", () => {
    renderView({ featured: [featured(1, "Shop")] });

    expect(screen.queryByRole("region", { name: "Другие проекты" })).toBeNull();
    expect(section("Главные проекты")).toBeTruthy();
  });

  test("the hero «Проекты» links to the projects", () => {
    const { container } = renderView({ other: [project("o1", "Bot")] });

    expect(screen.getByRole("link", { name: "Проекты" }).getAttribute("href")).toBe("#projects");
    expect(container.querySelector("#projects")).toBe(section("Другие проекты").parentElement);
  });

  test("without projects there is no project area and no «Проекты» button", () => {
    const { container } = renderView({});

    expect(container.querySelector("#projects")).toBeNull();
    expect(screen.queryByRole("link", { name: "Проекты" })).toBeNull();
    expect(screen.queryByText("Главные проекты")).toBeNull();
    expect(screen.queryByText("Другие проекты")).toBeNull();
  });

  test("skills and GitHub data are not rendered", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(screen.queryByText(/Скилы/i)).toBeNull();
    expect(screen.queryByText(/Данные GitHub/i)).toBeNull();
  });
});
