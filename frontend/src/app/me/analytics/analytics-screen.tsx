"use client";

import { cn } from "cn";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { SectionHeading } from "@/components/section-heading";
import { Button } from "@/components/ui/button";
import {
  ANALYTICS_PERIODS,
  ApiError,
  getProfileAnalytics,
  type AnalyticsDays,
  type ProfileAnalytics,
  type ProjectAnalyticsItem,
} from "@/lib/api";

import { CabinetPage, LoadErrorPanel, LoadingPanel, useAccount, type Account } from "../cabinet-page";
import { ProjectStateBadge, UNTITLED } from "../projects/project-texts";
import { fullDate } from "./dates";
import { ProjectDays } from "./project-days";

// The owner's counters (DESIGN.md, "Analytics"; mockup analytics.png; ADR-0029).
// Every number is a sum of events, not of people, and the screen never ranks:
// no percentages between the funnel stages, projects in the API order.

const DEFAULT_DAYS: AnalyticsDays = 30;

type Loaded =
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; data: ProfileAnalytics };

export function AnalyticsScreen() {
  const router = useRouter();
  const account = useAccount();
  const [days, setDays] = useState<AnalyticsDays>(DEFAULT_DAYS);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  // A period change keeps the shown numbers until its answer comes.
  const [pending, setPending] = useState(false);
  const [refreshError, setRefreshError] = useState<unknown>(null);
  const shown = useRef(false);

  useEffect(() => {
    // Aborting the older request means its late answer never replaces a newer one.
    const controller = new AbortController();
    getProfileAnalytics(days, { signal: controller.signal }).then(
      (data) => {
        // An answer read after the abort is dropped too.
        if (controller.signal.aborted) {
          return;
        }
        shown.current = true;
        setLoaded({ status: "ready", data });
        setPending(false);
      },
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setPending(false);
        // After a failed period change the shown numbers stay, with the error above them.
        if (shown.current) {
          setRefreshError(error);
        } else {
          setLoaded({ status: "error", error });
        }
      },
    );
    return () => controller.abort();
  }, [days, attempt, router]);

  function choose(next: AnalyticsDays) {
    if (next === days || pending) {
      return;
    }
    setPending(true);
    setRefreshError(null);
    setDays(next);
  }

  function retry() {
    setLoaded({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  return (
    <CabinetPage account={account} tab="analytics">
      {loaded.status === "loading" && <LoadingPanel />}
      {loaded.status === "error" && <LoadErrorPanel error={loaded.error} onRetry={retry} />}
      {loaded.status === "ready" && (
        <AnalyticsBoard
          data={loaded.data}
          days={days}
          pending={pending}
          refreshError={refreshError}
          account={account}
          onChoose={choose}
        />
      )}
    </CabinetPage>
  );
}

function AnalyticsBoard({
  data,
  days,
  pending,
  refreshError,
  account,
  onChoose,
}: {
  data: ProfileAnalytics;
  days: AnalyticsDays;
  pending: boolean;
  refreshError: unknown;
  account: Account | null;
  onChoose: (days: AnalyticsDays) => void;
}) {
  const { period, totals, projects } = data;
  const empty = Object.values(totals).every((count) => count === 0);

  return (
    <section
      aria-labelledby="analytics-title"
      className="flex flex-col gap-6 bg-panel px-4 py-6 shadow-panel sm:px-8 sm:py-8"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 id="analytics-title" className="font-heading text-xl leading-normal uppercase">
            Аналитика
          </h1>
          <p className="text-sm text-text-muted">
            С {fullDate(period.start)} по {fullDate(period.end)} · дни по UTC, сегодня включительно
          </p>
        </div>
        <div role="group" aria-label="Период" className="flex flex-wrap gap-3">
          {ANALYTICS_PERIODS.map((option) => (
            <Button
              key={option}
              variant={option === days ? "default" : "secondary"}
              aria-pressed={option === days}
              disabled={pending}
              onClick={() => onChoose(option)}
            >
              {option} дней
            </Button>
          ))}
        </div>
      </div>
      {pending && (
        <p role="status" className="text-sm text-text-muted">
          Загрузка…
        </p>
      )}
      {refreshError !== null && <RequestErrorAlert error={refreshError} />}

      <SectionHeading id="funnel-title" marker="label">
        Воронка
      </SectionHeading>
      <Funnel data={data} />
      <p className="text-sm text-text-muted">
        Это суммы событий за период, а не люди: одно обновление страницы — ещё один просмотр. Ваши
        собственные просмотры не считаются. Посетители с блокировщиками не видны, поэтому цифры —
        нижняя граница.
      </p>

      <SectionHeading id="projects-title" marker="label">
        Проекты
      </SectionHeading>
      {empty && <EmptyNote account={account} />}
      {projects.length === 0 ? (
        <p>
          Проектов пока нет.{" "}
          <Link href="/me/projects" className="underline underline-offset-4">
            Мои проекты
          </Link>
        </p>
      ) : (
        <ProjectTable projects={projects} days={days} pending={pending} />
      )}
      <p className="text-sm text-text-muted">
        Счётчики идут только у опубликованных и видимых проектов. Порядок — как в «Мои проекты».
      </p>
      <p className="text-sm text-text-muted">
        GitHub в воронке — это ещё и кнопка «GitHub» в шапке профиля, поэтому сумма может быть
        больше, чем по проектам.
      </p>
    </section>
  );
}

function Funnel({ data: { totals } }: { data: ProfileAnalytics }) {
  const stages = [
    { label: "Профиль", value: totals.profile_views, note: "просмотров профиля" },
    { label: "Проекты", value: totals.project_views, note: "просмотров проектов" },
    {
      label: "Демо и GitHub",
      value: totals.demo_clicks + totals.github_clicks,
      note: `демо ${totals.demo_clicks} · GitHub ${totals.github_clicks}`,
    },
    { label: "Контакты", value: totals.contact_clicks, note: "кликов по контактам" },
  ];
  return (
    <ol
      aria-labelledby="funnel-title"
      className="grid grid-cols-2 gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr]"
    >
      {stages.map((stage, index) => (
        <Fragment key={stage.label}>
          {index > 0 && (
            <li aria-hidden="true" className="hidden self-center text-2xl text-text-muted md:block">
              ›
            </li>
          )}
          <li className="flex flex-col gap-1 border-2 border-outline bg-bg p-3 md:p-4">
            <span className="caps-label">{stage.label}</span>
            <span
              className={cn(
                "font-heading text-2xl leading-tight md:text-3xl",
                stage.value === 0 && "text-text-muted",
              )}
            >
              {stage.value}
            </span>
            <span className="text-sm text-text-muted">{stage.note}</span>
          </li>
        </Fragment>
      ))}
    </ol>
  );
}

function EmptyNote({ account }: { account: Account | null }) {
  return (
    <div className="flex flex-col gap-2 border-2 border-dashed border-frame p-4">
      <p>За этот период событий нет.</p>
      {account?.status === "PRIVATE" && (
        <p className="text-sm text-text-muted">
          Профиль скрыт — счётчики появятся после публикации.{" "}
          <Link href="/me" className="underline underline-offset-4">
            Открыть профиль
          </Link>
        </p>
      )}
      {account?.status === "PUBLISHED" && (
        <p className="text-sm text-text-muted">Счётчики растут, когда профиль открывают посетители.</p>
      )}
    </div>
  );
}

const CELL = "px-3 py-3 max-lg:px-0 max-lg:py-1";
const NUMBER = cn(CELL, "text-right tabular-nums max-lg:text-left");

// One markup for both widths: a table from 1024 px, stacked rows below it (six
// columns with the badge do not fit the panel narrower than that).
function ProjectTable({
  projects,
  days,
  pending,
}: {
  projects: ProjectAnalyticsItem[];
  days: AnalyticsDays;
  pending: boolean;
}) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <table className="w-full border-collapse max-lg:block">
      <thead className="max-lg:sr-only">
        <tr className="border-b-4 border-outline text-left text-sm text-text-muted uppercase">
          <th className="px-3 pb-2 font-medium">Проект</th>
          <th className="px-3 pb-2 font-medium">Статус</th>
          <th className="px-3 pb-2 text-right font-medium">Просмотры</th>
          <th className="px-3 pb-2 text-right font-medium">Демо</th>
          <th className="px-3 pb-2 text-right font-medium">GitHub</th>
          <th className="px-3 pb-2">
            <span className="sr-only">По дням</span>
          </th>
        </tr>
      </thead>
      <tbody className="max-lg:block">
        {projects.map((project) => {
          const open = project.id === openId;
          const title = project.title ?? UNTITLED;
          const panelId = `days-${project.id}`;
          return (
            <Fragment key={project.id}>
              <tr
                className={cn(
                  "border-b-2 border-frame max-lg:flex max-lg:flex-wrap max-lg:gap-x-6 max-lg:py-3",
                  open && "bg-bg",
                )}
              >
                <td className={cn(CELL, "break-words max-lg:w-full")}>{title}</td>
                <td className={cn(CELL, "max-lg:w-full")}>
                  <ProjectStateBadge status={project.status} visibility={project.visibility} />
                </td>
                <CountCell label="Просмотры" value={project.counts.project_views} />
                <CountCell label="Демо" value={project.counts.demo_clicks} />
                <CountCell label="GitHub" value={project.counts.github_clicks} />
                <td className={cn(CELL, "text-right max-lg:w-full max-lg:text-left")}>
                  <Button
                    variant={open ? "default" : "secondary"}
                    aria-expanded={open}
                    aria-controls={open ? panelId : undefined}
                    disabled={pending}
                    onClick={() => setOpenId(open ? null : project.id)}
                  >
                    По дням {open ? "▴" : "▾"}
                    <span className="sr-only">: {title}</span>
                  </Button>
                </td>
              </tr>
              {open && (
                <tr className="border-b-2 border-frame max-lg:block">
                  <td colSpan={6} className="pb-4 max-lg:block">
                    <ProjectDays
                      key={days}
                      id={project.id}
                      panelId={panelId}
                      title={title}
                      days={days}
                    />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

function CountCell({ label, value }: { label: string; value: number }) {
  return (
    <td className={cn(NUMBER, value === 0 && "text-text-muted")}>
      <span className="block text-sm text-text-muted lg:hidden">{label}</span>
      {value}
    </td>
  );
}
