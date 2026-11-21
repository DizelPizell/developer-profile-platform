import { fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { AnalyticsTracker } from "./analytics-tracker";

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

const PAGE_PROJECT = "11111111-1111-4111-8111-111111111111";
const CARD_PROJECT = "22222222-2222-4222-8222-222222222222";

const sent = () => fetchMock.mock.calls.map(([, init]) => JSON.parse(init?.body as string));

function Page({ projectId }: { projectId?: string }) {
  return (
    <>
      <AnalyticsTracker slug="ann" projectId={projectId} />
      <a href="https://github.com/ann" data-analytics="GITHUB_CLICK">
        GitHub
      </a>
      <a href="https://demo.example" data-analytics="DEMO_CLICK">
        <span>Открыть демо</span>
      </a>
      <article data-analytics-project={CARD_PROJECT}>
        <p data-analytics="GITHUB_CLICK">
          <a href="https://github.com/ann/repo">ann/repo</a>
        </p>
      </article>
      <p data-analytics="GITHUB_CLICK">без ссылки</p>
      <a href="#contacts">Контакты</a>
    </>
  );
}

describe("AnalyticsTracker", () => {
  test("a profile page sends one PROFILE_VIEW, also under Strict Mode", () => {
    render(
      <StrictMode>
        <Page />
      </StrictMode>,
    );

    expect(sent()).toEqual([{ type: "PROFILE_VIEW", slug: "ann", project_id: null }]);
  });

  test("a project page sends PROJECT_VIEW with its id", () => {
    render(<Page projectId={PAGE_PROJECT} />);

    expect(sent()).toEqual([{ type: "PROJECT_VIEW", slug: "ann", project_id: PAGE_PROJECT }]);
  });

  test("a marked link sends its type; the project is the nearest marked one, else none", () => {
    render(<Page />);
    fetchMock.mockClear();

    fireEvent.click(screen.getByText("GitHub"));
    fireEvent.click(screen.getByText("ann/repo"));

    expect(sent()).toEqual([
      { type: "GITHUB_CLICK", slug: "ann", project_id: null },
      { type: "GITHUB_CLICK", slug: "ann", project_id: CARD_PROJECT },
    ]);
  });

  test("on a project page a click inside the link counts with the page's project", () => {
    render(<Page projectId={PAGE_PROJECT} />);
    fetchMock.mockClear();

    fireEvent.click(screen.getByText("Открыть демо"));

    expect(sent()).toEqual([{ type: "DEMO_CLICK", slug: "ann", project_id: PAGE_PROJECT }]);
  });

  test("the middle button counts, the right one does not", () => {
    render(<Page />);
    fetchMock.mockClear();

    fireEvent(screen.getByText("GitHub"), new MouseEvent("auxclick", { bubbles: true, button: 1 }));
    fireEvent(screen.getByText("GitHub"), new MouseEvent("auxclick", { bubbles: true, button: 2 }));

    expect(sent()).toEqual([{ type: "GITHUB_CLICK", slug: "ann", project_id: null }]);
  });

  test("an unmarked link and marked text without a link send nothing", () => {
    render(<Page />);
    fetchMock.mockClear();

    fireEvent.click(screen.getByText("Контакты"));
    fireEvent.click(screen.getByText("без ссылки"));

    expect(fetchMock).not.toHaveBeenCalled();
  });

  test("after unmount clicks are not listened to", () => {
    const { unmount } = render(<AnalyticsTracker slug="ann" />);
    const link = document.body.appendChild(document.createElement("a"));
    link.href = "https://github.com/ann";
    link.dataset.analytics = "GITHUB_CLICK";
    unmount();
    fetchMock.mockClear();

    fireEvent.click(link);

    expect(fetchMock).not.toHaveBeenCalled();
    link.remove();
  });
});
