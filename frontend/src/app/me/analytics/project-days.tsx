"use client";

import { cn } from "cn";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  getProjectAnalytics,
  type AnalyticsDays,
  type ProjectAnalytics,
  type ProjectDay,
} from "@/lib/api";

import { dayMonth } from "./dates";

// One project by UTC day, opened under its row (DESIGN.md, "Analytics"). The chart
// shows one series, the views; the clicks are numbers and in «Таблица по дням»,
// which is also the keyboard and screen reader version of the chart.

type Loaded =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error"; error: unknown }
  | { status: "ready"; data: ProjectAnalytics };

export function ProjectDays({
  id,
  panelId,
  title,
  days,
}: {
  id: string;
  panelId: string;
  title: string;
  days: AnalyticsDays;
}) {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });

  useEffect(() => {
    // A new period remounts the panel (its key holds the days), so it starts from «Загрузка…».
    const controller = new AbortController();
    getProjectAnalytics(id, days, { signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted) {
          setLoaded({ status: "ready", data });
        }
      },
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        if (error instanceof ApiError && error.status === 404) {
          setLoaded({ status: "not-found" });
          return;
        }
        setLoaded({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [id, days, attempt, router]);

  return (
    <div
      id={panelId}
      role="region"
      aria-label={`${title}: просмотры по дням`}
      className="flex flex-col gap-4 border-2 border-outline bg-bg p-3 sm:p-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="caps-label break-words">{title} · просмотры по дням</h3>
        <span className="text-sm text-text-muted">дни по UTC</span>
      </div>
      {loaded.status === "loading" && <p role="status">Загрузка…</p>}
      {loaded.status === "not-found" && (
        <p className="text-error">Проект не найден — возможно, он удалён.</p>
      )}
      {loaded.status === "error" && (
        <div className="flex flex-col items-start gap-4">
          <RequestErrorAlert error={loaded.error} />
          <Button
            onClick={() => {
              setLoaded({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          >
            Повторить
          </Button>
        </div>
      )}
      {loaded.status === "ready" && <DaysChart data={loaded.data} />}
    </div>
  );
}

function DaysChart({ data: { daily, totals } }: { data: ProjectAnalytics }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const max = Math.max(0, ...daily.map((day) => day.counts.project_views));
  const middle = daily[Math.floor((daily.length - 1) / 2)];
  const shown = hovered === null ? null : daily[hovered];

  return (
    <>
      {/* The bars are hidden from screen readers: the day table below carries the numbers. */}
      <div aria-hidden="true" className="flex flex-col gap-2 pt-14">
        <div className="relative grid h-36 grid-cols-[2rem_1fr] gap-2 sm:h-44 sm:grid-cols-[2.5rem_1fr]">
          <div className="-my-2 flex flex-col justify-between text-right text-sm leading-none text-text-muted tabular-nums">
            <span>{max}</span>
            <span>0</span>
          </div>
          <div
            className={cn(
              "relative flex items-end border-b-2 border-text-muted",
              daily.length > 60 ? "gap-px" : "gap-0.5",
            )}
            onMouseLeave={() => setHovered(null)}
          >
            <span className="absolute inset-x-0 top-0 border-t-2 border-dashed border-frame" />
            {daily.map((day, index) => {
              const views = day.counts.project_views;
              return (
                <span
                  key={day.day}
                  data-day={day.day}
                  onMouseEnter={() => setHovered(index)}
                  className={cn(
                    "flex-1",
                    views === 0
                      ? "h-0.5 bg-frame"
                      : cn("rounded-t", index === hovered ? "bg-label" : "bg-accent"),
                  )}
                  style={views === 0 ? undefined : { height: `${(views / max) * 100}%` }}
                />
              );
            })}
            {shown && hovered !== null && (
              <Tooltip day={shown} left={(hovered + 0.5) / daily.length} />
            )}
          </div>
        </div>
        <div className="ml-10 flex justify-between text-sm text-text-muted sm:ml-12">
          <span>{dayMonth(daily[0].day)}</span>
          <span>{dayMonth(middle.day)}</span>
          <span>{dayMonth(daily[daily.length - 1].day)}</span>
        </div>
      </div>

      <p className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
        <span className="text-text-muted">За {daily.length} дней:</span>
        <span>просмотры {totals.project_views}</span>
        <span>демо {totals.demo_clicks}</span>
        <span>GitHub {totals.github_clicks}</span>
      </p>

      <details>
        <summary className="cursor-pointer underline underline-offset-4">Таблица по дням</summary>
        <table className="mt-3 w-full border-collapse text-sm">
          <thead>
            <tr className="border-b-4 border-outline text-left text-text-muted uppercase">
              <th className="py-1 pr-3 font-medium">День</th>
              <th className="px-3 py-1 text-right font-medium">Просмотры</th>
              <th className="px-3 py-1 text-right font-medium">Демо</th>
              <th className="py-1 pl-3 text-right font-medium">GitHub</th>
            </tr>
          </thead>
          <tbody>
            {daily.map((day) => (
              <tr key={day.day} className="border-b-2 border-frame tabular-nums">
                <td className="py-1 pr-3">{dayMonth(day.day)}</td>
                <td className="px-3 py-1 text-right">{day.counts.project_views}</td>
                <td className="px-3 py-1 text-right">{day.counts.demo_clicks}</td>
                <td className="py-1 pl-3 text-right">{day.counts.github_clicks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}

function Tooltip({ day, left }: { day: ProjectDay; left: number }) {
  return (
    <div
      data-testid="day-tooltip"
      className="pointer-events-none absolute bottom-full mb-2 -translate-x-1/2 border-4 border-outline bg-panel px-3 py-2 text-sm whitespace-nowrap shadow-pixel"
      // Kept inside the plot at its edges, so the first and last days stay readable.
      style={{ left: `clamp(4.5rem, ${left * 100}%, calc(100% - 4.5rem))` }}
    >
      <span className="font-medium">{dayMonth(day.day)}</span> · просмотры{" "}
      {day.counts.project_views}
      <br />
      <span className="text-text-muted">
        демо {day.counts.demo_clicks} · GitHub {day.counts.github_clicks}
      </span>
    </div>
  );
}
