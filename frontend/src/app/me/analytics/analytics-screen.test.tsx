import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { AnalyticsScreen } from "./analytics-screen";

const { replace, router } = vi.hoisted(() => {
  const replace = vi.fn();
  return { replace, router: { replace } };
});

vi.mock("next/navigation", () => ({ useRouter: () => router }));

const fetchMock = vi.fn<typeof fetch>();
const API = "http://api.test/api/v1";

const PROFILE = {
  slug: "ann",
  status: "PUBLISHED",
  display_name: "Ann",
  headline: null,
  bio: null,
  location: null,
  avatar_url: null,
  github_login: "ann-gh",
  contacts: [],
};

const ZERO = { project_views: 0, demo_clicks: 0, github_clicks: 0 };
const ZERO_TOTALS = { ...ZERO, profile_views: 0, contact_clicks: 0 };

function period(days: number, start = "2026-10-23", end = "2026-11-21") {
  return { days, start, end };
}

function item(id: string, title: string | null, fields: object = {}) {
  return { id, title, status: "PUBLISHED", visibility: "PUBLIC", counts: ZERO, ...fields };
}

// The API order: a quiet project before a busy one, so a sort by numbers would show.
const QUIET = item("q", "Quiet");
const BUSY = item("b", "Busy", { counts: { project_views: 72, demo_clicks: 21, github_clicks: 9 } });
const DRAFT = item("d", null, { status: "DRAFT", visibility: "PRIVATE" });

function profileAnalytics(fields: object = {}) {
  return {
    period: period(30),
    totals: {
      profile_views: 248,
      project_views: 131,
      demo_clicks: 34,
      github_clicks: 23,
      contact_clicks: 9,
    },
    projects: [QUIET, BUSY, DRAFT],
    ...fields,
  };
}

function day(date: string, views: number, demo = 0, github = 0) {
  return { day: date, counts: { project_views: views, demo_clicks: demo, github_clicks: github } };
}

function projectAnalytics(daily = [day("2026-11-19", 4, 1), day("2026-11-20", 0), day("2026-11-21", 8, 2, 1)]) {
  return {
    period: period(daily.length, daily[0].day, daily[daily.length - 1].day),
    totals: { project_views: 12, demo_clicks: 3, github_clicks: 1 },
    daily,
  };
}

function apiError(status: number, code: string) {
  return Response.json({ error: { code, message: code, details: {}, request_id: "r-1" } }, { status });
}

type Reply = Response | Promise<Response>;

/** Answers by "/path?query"; each route answers its replies in order, then repeats the last. */
function routes(table: Record<string, Reply[]>) {
  const queues = new Map(Object.entries(table).map(([key, replies]) => [key, [...replies]]));
  fetchMock.mockImplementation(async (url) => {
    const key = String(url).replace(API, "");
    const queue = queues.get(key);
    if (!queue) {
      throw new Error(`unexpected request ${key}`);
    }
    const reply = queue.length > 1 ? queue.shift()! : queue[0];
    return (await reply).clone();
  });
}

function deferred() {
  let resolve!: (response: Response) => void;
  const promise = new Promise<Response>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

const calls = (path: string) =>
  fetchMock.mock.calls.filter(([url]) => String(url).replace(API, "") === path);

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

async function renderScreen(extra: Record<string, Reply[]> = {}) {
  routes({
    "/profile": [Response.json(PROFILE)],
    "/analytics/profile?days=30": [Response.json(profileAnalytics())],
    ...extra,
  });
  render(<AnalyticsScreen />);
  await screen.findByRole("heading", { name: "Аналитика", level: 1 });
}

const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const funnel = () => screen.getByRole("list", { name: "Воронка" });
const rows = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .filter((row) => row.querySelector("button"));

describe("the screen", () => {
  test("the tab is active and the period is 30 days by default", async () => {
    await renderScreen();

    const tab = screen.getByRole("link", { name: "Аналитика" });
    expect(tab.getAttribute("href")).toBe("/me/analytics");
    expect(tab.getAttribute("aria-current")).toBe("page");
    expect(button("30 дней").getAttribute("aria-pressed")).toBe("true");
    expect(button("7 дней").getAttribute("aria-pressed")).toBe("false");
    expect(screen.getByText(/С 23\.10\.2026 по 21\.11\.2026 · дни по UTC/)).toBeTruthy();
  });

  test("the funnel shows four sums, no percentages, and says they are events", async () => {
    await renderScreen();

    const stages = within(funnel())
      .getAllByRole("listitem")
      .filter((li) => li.getAttribute("aria-hidden") !== "true")
      .map((li) => li.textContent);
    expect(stages).toEqual([
      "Профиль248просмотров профиля",
      "Проекты131просмотров проектов",
      "Демо и GitHub57демо 34 · GitHub 23",
      "Контакты9кликов по контактам",
    ]);
    expect(document.body.textContent).not.toContain("%");
    expect(screen.getByText(/суммы событий за период, а не люди/)).toBeTruthy();
  });

  test("projects keep the API order with their badges and counts; a missing title is marked", async () => {
    await renderScreen();

    expect(rows().map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual([
      "Quiet",
      "Busy",
      "[Без названия]",
    ]);
    const busy = within(rows()[1]).getAllByRole("cell").map((cell) => cell.textContent);
    expect(busy.slice(1, 5)).toEqual(["Опубликован", "Просмотры72", "Демо21", "GitHub9"]);
    expect(within(rows()[2]).getByText("Черновик")).toBeTruthy();
  });

  test("a 401 leaves for /login", async () => {
    routes({ "/profile": [Response.json(PROFILE)], "/analytics/profile?days=30": [apiError(401, "UNAUTHORIZED")] });
    render(<AnalyticsScreen />);

    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });

  test("a load error offers «Повторить», which loads again", async () => {
    routes({
      "/profile": [Response.json(PROFILE)],
      "/analytics/profile?days=30": [apiError(500, "INTERNAL_ERROR"), Response.json(profileAnalytics())],
    });
    render(<AnalyticsScreen />);

    fireEvent.click(await screen.findByRole("button", { name: "Повторить" }));

    await screen.findByRole("heading", { name: "Аналитика", level: 1 });
  });
});

describe("the period", () => {
  test("a new period keeps the numbers until its answer, with the buttons disabled", async () => {
    const seven = deferred();
    await renderScreen({ "/analytics/profile?days=7": [seven.promise] });

    fireEvent.click(button("7 дней"));

    expect(button("30 дней").disabled).toBe(true);
    expect(button(/По дням.*Busy/).disabled).toBe(true);
    expect(within(funnel()).getByText("248")).toBeTruthy();

    await act(async () =>
      seven.resolve(Response.json(profileAnalytics({ period: period(7, "2026-11-15"), totals: { ...ZERO_TOTALS, profile_views: 61 } }))),
    );

    expect(within(funnel()).getByText("61")).toBeTruthy();
    expect(button("7 дней").getAttribute("aria-pressed")).toBe("true");
    expect(button("30 дней").disabled).toBe(false);
  });

  test("while a period loads, another one is not requested", async () => {
    const ninety = deferred();
    await renderScreen({
      "/analytics/profile?days=90": [ninety.promise],
      "/analytics/profile?days=7": [Response.json(profileAnalytics({ totals: { ...ZERO_TOTALS, profile_views: 7 } }))],
    });

    fireEvent.click(button("90 дней"));
    // The buttons are disabled, so the answers cannot arrive out of order.
    await act(async () => {
      fireEvent.click(button("7 дней"));
    });
    await act(async () =>
      ninety.resolve(Response.json(profileAnalytics({ totals: { ...ZERO_TOTALS, profile_views: 90 } }))),
    );

    expect(calls("/analytics/profile?days=7")).toHaveLength(0);
    expect(within(funnel()).getByText("90")).toBeTruthy();
  });

  test("a failed change keeps the numbers and shows the error", async () => {
    await renderScreen({ "/analytics/profile?days=90": [apiError(500, "INTERNAL_ERROR")] });

    fireEvent.click(button("90 дней"));

    await screen.findByRole("alert");
    expect(within(funnel()).getByText("248")).toBeTruthy();
    expect(button("90 дней").disabled).toBe(false);
  });
});

describe("empty states", () => {
  test("no events: a note, with the hint for a hidden profile", async () => {
    routes({
      "/profile": [Response.json({ ...PROFILE, status: "PRIVATE" })],
      "/analytics/profile?days=30": [Response.json(profileAnalytics({ totals: ZERO_TOTALS, projects: [QUIET] }))],
    });
    render(<AnalyticsScreen />);

    expect(await screen.findByText("За этот период событий нет.")).toBeTruthy();
    expect(await screen.findByText(/Профиль скрыт — счётчики появятся после публикации/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Открыть профиль" }).getAttribute("href")).toBe("/me");
    expect(rows()).toHaveLength(1);
  });

  test("no projects: a link to «Мои проекты» instead of the table", async () => {
    await renderScreen({
      "/analytics/profile?days=30": [Response.json(profileAnalytics({ projects: [] }))],
    });

    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("link", { name: "Мои проекты" }).getAttribute("href")).toBe("/me/projects");
  });
});

describe("a project by day", () => {
  test("«По дням» opens one project at a time and closes on a second click", async () => {
    await renderScreen({
      "/analytics/projects/b?days=30": [Response.json(projectAnalytics())],
      "/analytics/projects/q?days=30": [Response.json(projectAnalytics())],
    });

    fireEvent.click(button(/По дням.*Busy/));
    expect(button(/По дням.*Busy/).getAttribute("aria-expanded")).toBe("true");
    expect(await screen.findByRole("region", { name: "Busy: просмотры по дням" })).toBeTruthy();

    fireEvent.click(button(/По дням.*Quiet/));
    expect(screen.queryByRole("region", { name: "Busy: просмотры по дням" })).toBeNull();
    expect(screen.getByRole("region", { name: "Quiet: просмотры по дням" })).toBeTruthy();

    fireEvent.click(button(/По дням.*Quiet/));
    expect(screen.queryByRole("region", { name: /просмотры по дням/ })).toBeNull();
  });

  test("the panel shows the sums, every day in the table and the dates without a shift", async () => {
    await renderScreen({ "/analytics/projects/b?days=30": [Response.json(projectAnalytics())] });

    fireEvent.click(button(/По дням.*Busy/));
    const panel = await screen.findByRole("region", { name: "Busy: просмотры по дням" });
    await within(panel).findByText("Таблица по дням");

    expect(within(panel).getByText("За 3 дней:")).toBeTruthy();
    expect(within(panel).getByText("просмотры 12")).toBeTruthy();
    const table = within(panel).getByRole("table");
    expect(
      within(table)
        .getAllByRole("row")
        .slice(1)
        .map((row) => row.textContent),
    ).toEqual(["19.11410", "20.11000", "21.11821"]);
  });

  test("bars: height from the period's maximum, a zero day as a line, a tooltip on hover", async () => {
    await renderScreen({ "/analytics/projects/b?days=30": [Response.json(projectAnalytics())] });

    fireEvent.click(button(/По дням.*Busy/));
    const panel = await screen.findByRole("region", { name: "Busy: просмотры по дням" });
    await within(panel).findByText("Таблица по дням");
    const bar = (date: string) => panel.querySelector<HTMLElement>(`[data-day="${date}"]`)!;

    expect(bar("2026-11-19").style.height).toBe("50%");
    expect(bar("2026-11-21").style.height).toBe("100%");
    expect(bar("2026-11-20").style.height).toBe("");
    expect(bar("2026-11-20").className).toContain("h-0.5");

    fireEvent.mouseEnter(bar("2026-11-21"));
    expect(screen.getByTestId("day-tooltip").textContent).toBe("21.11 · просмотры 8демо 2 · GitHub 1");
    fireEvent.mouseLeave(bar("2026-11-21").parentElement!);
    expect(screen.queryByTestId("day-tooltip")).toBeNull();
  });

  test("a new period loads the opened project again", async () => {
    await renderScreen({
      "/analytics/projects/b?days=30": [Response.json(projectAnalytics())],
      "/analytics/profile?days=7": [Response.json(profileAnalytics({ period: period(7) }))],
      "/analytics/projects/b?days=7": [Response.json(projectAnalytics([day("2026-11-21", 5)]))],
    });

    fireEvent.click(button(/По дням.*Busy/));
    await screen.findByText("Таблица по дням");
    fireEvent.click(button("7 дней"));

    const panel = screen.getByRole("region", { name: "Busy: просмотры по дням" });
    expect(await within(panel).findByText("За 1 дней:")).toBeTruthy();
    expect(calls("/analytics/projects/b?days=7")).toHaveLength(1);
  });

  test("a deleted project shows its own message; the table stays", async () => {
    await renderScreen({ "/analytics/projects/b?days=30": [apiError(404, "NOT_FOUND")] });

    fireEvent.click(button(/По дням.*Busy/));

    expect(await screen.findByText("Проект не найден — возможно, он удалён.")).toBeTruthy();
    expect(rows()).toHaveLength(3);
  });

  test("a failed load offers «Повторить» inside the panel", async () => {
    await renderScreen({
      "/analytics/projects/b?days=30": [apiError(500, "INTERNAL_ERROR"), Response.json(projectAnalytics())],
    });

    fireEvent.click(button(/По дням.*Busy/));
    const panel = await screen.findByRole("region", { name: "Busy: просмотры по дням" });
    fireEvent.click(await within(panel).findByRole("button", { name: "Повторить" }));

    expect(await within(panel).findByText("Таблица по дням")).toBeTruthy();
  });
});
