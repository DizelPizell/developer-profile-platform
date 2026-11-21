import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type {
  PublicFeaturedProject,
  PublicGitHub,
  PublicProfile,
  PublicProject,
} from "@/lib/api";

import { ProfileView } from "./profile-view";

const PROFILE: PublicProfile = {
  slug: "ann",
  display_name: "Ann Lee",
  headline: "Backend",
  bio: null,
  location: null,
  avatar_url: null,
  github_login: "ann-gh",
  contacts: [],
  featured: [],
  other: [],
};

const GITHUB: PublicGitHub = {
  full_name: "ann/shop",
  html_url: "https://github.com/ann/shop",
  description: "A small shop",
  languages: [{ name: "Python", bytes: 10 }],
  is_fork: false,
  parent_full_name: null,
  is_archived: false,
  relation: "OWNER",
  synced_at: "2026-11-01T12:00:00Z",
};

function project(id: string, title: string, overrides: Partial<PublicProject> = {}): PublicProject {
  return {
    id,
    title,
    summary: `${title} summary`,
    role: `${title} role`,
    technologies: ["Python"],
    github: null,
    ...overrides,
  };
}

function featured(position: number, title: string, overrides: Partial<PublicProject> = {}) {
  return { ...project(`f${position}`, title, overrides), position } satisfies PublicFeaturedProject;
}

// The analytics tracker posts events from the page.
const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://api.test");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue(new Response(null, { status: 202 }));
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
});

const sentEvents = () =>
  fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith("/analytics/events"))
    .map(([, init]) => JSON.parse(init?.body as string));

describe("analytics", () => {
  test("the page sends PROFILE_VIEW; GitHub links send clicks with the card's project", () => {
    renderView({
      featured: [featured(1, "Shop", { github: GITHUB })],
      other: [project("o1", "Tracker", { github: { ...GITHUB, full_name: "ann/tracker" } })],
    });

    fireEvent.click(screen.getByRole("link", { name: "GitHub" }));
    fireEvent.click(screen.getByRole("link", { name: "ann/shop" }));
    fireEvent.click(screen.getByRole("link", { name: "ann/tracker" }));
    // The project page link and the hero anchor are not counted.
    fireEvent.click(screen.getByRole("link", { name: "Shop" }));
    fireEvent.click(screen.getByRole("link", { name: "Проекты" }));

    expect(sentEvents()).toEqual([
      { type: "PROFILE_VIEW", slug: "ann", project_id: null },
      { type: "GITHUB_CLICK", slug: "ann", project_id: null },
      { type: "GITHUB_CLICK", slug: "ann", project_id: "f1" },
      { type: "GITHUB_CLICK", slug: "ann", project_id: "o1" },
    ]);
  });

  test("a contact link and the reveal button send CONTACT_CLICK", async () => {
    renderView({
      contacts: [
        { type: "TELEGRAM", value: "ann_dev", label: null, url: "https://t.me/ann_dev" },
        { type: "EMAIL", value: null, label: null, url: null },
      ],
    });
    fetchMock.mockClear();
    fetchMock.mockImplementation(async (url) =>
      String(url).includes("/contacts")
        ? Response.json({ type: "EMAIL", value: "ann@example.com", url: "mailto:ann@example.com" })
        : new Response(null, { status: 202 }),
    );

    fireEvent.click(screen.getByRole("link", { name: "@ann_dev" }));
    fireEvent.click(screen.getByRole("button", { name: "Показать email" }));
    // The revealed mailto: link is not counted a second time.
    fireEvent.click(await screen.findByRole("link", { name: "ann@example.com" }));

    expect(sentEvents()).toEqual([
      { type: "CONTACT_CLICK", slug: "ann", project_id: null },
      { type: "CONTACT_CLICK", slug: "ann", project_id: null },
    ]);
  });
});

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

  test("the title of a card and of a row is the one link to the project page", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(screen.queryByText(/Открыть проект/)).toBeNull();
    const links = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(links).toEqual([
      "/login",
      "https://github.com/ann-gh",
      "#projects",
      "/u/ann/projects/f1",
      "/u/ann/projects/o1",
    ]);
    expect(screen.getByRole("heading", { level: 3, name: "Shop" }).querySelector("a")?.textContent).toBe("Shop");
    expect(screen.getByRole("heading", { level: 3, name: "Bot" }).querySelector("a")?.textContent).toBe("Bot");
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

  test("skills are not rendered", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(screen.queryByText(/Скилы/i)).toBeNull();
  });
});

describe("the GitHub block", () => {
  function follows(later: Element, earlier: Element) {
    return (earlier.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING) !== 0;
  }

  test("a featured card has the full block after «Моя роль»", () => {
    renderView({ featured: [featured(1, "Shop", { github: GITHUB })] });

    const card = within(cards("Главные проекты")[0]);
    const source = card.getByText("Источник: GitHub");
    expect(follows(source, card.getByText("Моя роль: Shop role"))).toBe(true);
    expect(card.getByRole("link", { name: "ann/shop" })).toBeTruthy();
    expect(card.getByText("A small shop")).toBeTruthy();
    expect(card.getByRole("list", { name: "Языки" })).toBeTruthy();
  });

  test("the role stays pushed down with the block under it", () => {
    renderView({ featured: [featured(1, "Shop", { github: GITHUB })] });

    expect(screen.getByText("Моя роль: Shop role").className).toContain("mt-auto");
  });

  test("a row keeps its line and has the compact block under it", () => {
    renderView({ other: [project("o1", "Bot", { github: GITHUB })] });

    const row = cards("Другие проекты")[0];
    const view = within(row);
    expect(row.className).not.toContain("sm:flex-row");
    expect(view.getByRole("heading", { level: 3 }).closest(".sm\\:flex-row")).not.toBeNull();
    expect(follows(view.getByText("Источник: GitHub"), view.getByText("Python"))).toBe(true);
    expect(view.getByRole("link", { name: "ann/shop" })).toBeTruthy();
    expect(view.queryByText("A small shop")).toBeNull();
    expect(view.queryByRole("list", { name: "Языки" })).toBeNull();
  });

  test("null shows no block in a card and in a row", () => {
    renderView({ featured: [featured(1, "Shop")], other: [project("o1", "Bot")] });

    expect(cards("Главные проекты")[0].textContent).not.toContain("GitHub");
    expect(cards("Другие проекты")[0].textContent).not.toContain("GitHub");
  });

  test("each project has its own block", () => {
    renderView({
      featured: [
        featured(1, "Shop", { github: GITHUB }),
        featured(2, "Tracker"),
        featured(3, "Blog", { github: { ...GITHUB, full_name: "ann/blog" } }),
      ],
    });

    const items = cards("Главные проекты");
    expect(within(items[0]).getByRole("link", { name: "ann/shop" })).toBeTruthy();
    expect(items[1].textContent).not.toContain("GitHub");
    expect(within(items[2]).getByRole("link", { name: "ann/blog" })).toBeTruthy();
  });

  test("the block is not marked as the author's", () => {
    renderView({ featured: [featured(1, "Shop", { github: GITHUB })] });

    expect(cards("Главные проекты")[0].textContent).not.toContain("От автора");
  });
});

describe("contacts", () => {
  const TELEGRAM = { type: "TELEGRAM", value: "ann_dev", label: null, url: "https://t.me/ann_dev" } as const;
  const LINKEDIN = {
    type: "LINKEDIN",
    value: "ann-dev",
    label: null,
    url: "https://www.linkedin.com/in/ann-dev",
  } as const;
  const OTHER = {
    type: "OTHER",
    value: "https://a.example/blog",
    label: "Blog",
    url: "https://a.example/blog",
  } as const;
  const EMAIL = { type: "EMAIL", value: null, label: null, url: null } as const;
  const PHONE = { type: "PHONE", value: null, label: null, url: null } as const;

  test("without contacts there is no section and no hero button", () => {
    const { container } = renderView({ bio: "Hello" });

    expect(container.querySelector("#contacts")).toBeNull();
    expect(screen.queryByRole("link", { name: "Контакты" })).toBeNull();
    expect(screen.queryByText("Контакты")).toBeNull();
  });

  test("the section is marked «От автора» and the hero button leads to it", () => {
    const { container } = renderView({ contacts: [TELEGRAM] });

    expect(container.querySelector("#contacts")).toBe(section("Контакты"));
    expect(within(section("Контакты")).getByText("От автора")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Контакты" }).getAttribute("href")).toBe("#contacts");
  });

  test("public links are rendered in API order, in a new tab with the full rel", () => {
    renderView({ contacts: [OTHER, TELEGRAM, LINKEDIN] });

    const view = within(section("Контакты"));
    const links = view.getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["Blog", "https://a.example/blog"],
      ["@ann_dev", "https://t.me/ann_dev"],
      ["in/ann-dev", "https://www.linkedin.com/in/ann-dev"],
    ]);
    for (const link of links) {
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer nofollow ugc");
    }
    expect(section("Контакты").textContent).toContain("Blog · a.example");
  });

  test.each([
    ["a Telegram link to another host", { ...TELEGRAM, url: "https://t.me.evil.example/ann_dev" }, "@ann_dev"],
    ["a LinkedIn link to another path", { ...LINKEDIN, url: "https://www.linkedin.com/company/x" }, "in/ann-dev"],
    ["a javascript: link", { ...OTHER, url: "javascript:alert(1)" }, "Blog"],
    ["an ftp link", { ...OTHER, url: "ftp://a.example/" }, "Blog"],
    ["a broken link", { ...OTHER, url: "not a url" }, "Blog"],
  ])("%s stays text", (_name, contact, text) => {
    renderView({ contacts: [contact] });

    const view = within(section("Контакты"));
    expect(view.queryByRole("link")).toBeNull();
    expect(view.getByText(text)).toBeTruthy();
    expect(section("Контакты").textContent).not.toContain("·");
  });

  test("email and phone are buttons; the markup holds no value and no link for them", () => {
    const { container } = renderView({ contacts: [EMAIL, PHONE] });

    expect(screen.getByRole("button", { name: "Показать email" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Показать телефон" })).toBeTruthy();
    expect(container.innerHTML).not.toMatch(/mailto:|tel:/);
    expect(within(section("Контакты")).queryByRole("link")).toBeNull();
  });

  test("long values wrap", () => {
    renderView({ contacts: [{ ...TELEGRAM, value: "a".repeat(32) }] });

    expect(within(section("Контакты")).getByRole("link").className).toContain("break-all");
  });
});
