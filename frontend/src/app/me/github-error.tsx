"use client";

import { cn } from "cn";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { GENERIC_ERROR_MESSAGE, NETWORK_ERROR_MESSAGE } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  githubErrorCode,
  githubLoginUrl,
  linkedProjectId,
  NetworkError,
  projectLimit,
  PROJECTS_MAX,
  retryAfterSeconds,
  type ProjectSummary,
} from "@/lib/api";

import { UNTITLED } from "./projects/project-texts";

/** The request that failed: it picks the 404 text and what «Повторить» means. */
export type GitHubRequest = "list" | "import" | "link";

/** «через {N} мин»: whole minutes, rounded up, at least 1 (DESIGN.md). */
export function retryMinutes(seconds: number): number {
  return Math.max(1, Math.ceil(seconds / 60));
}

/**
 * The wait after a 429 GITHUB_USER_LIMIT_REACHED or a 503 GITHUB_RATE_LIMITED.
 * start(error) begins it from details.retry_after_seconds and does nothing for
 * other errors or a missing value. left is the seconds still to wait, 0 when
 * none. The timer reads the clock on every tick, so it stays right after the
 * tab sleeps, and it is cleared on unmount.
 */
export function useRetryCountdown() {
  const [until, setUntil] = useState<number | null>(null);
  const [now, setNow] = useState(0);

  useEffect(() => {
    if (until === null) {
      return;
    }
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (current >= until) {
        setUntil(null);
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [until]);

  const start = useCallback((error: unknown) => {
    const seconds = retryAfterSeconds(error);
    const current = Date.now();
    setNow(current);
    setUntil(seconds ? current + seconds * 1000 : null);
  }, []);

  const stop = useCallback(() => setUntil(null), []);

  const left = until === null ? 0 : Math.max(0, Math.ceil((until - now) / 1000));
  return { left, start, stop };
}

type Action =
  | { kind: "login" }
  | { kind: "link"; href: string; label: string }
  | { kind: "retry" }
  | { kind: "wait" };

type Message = {
  /** label: the user can act or wait; error: the request cannot succeed as is. */
  tone: "label" | "error";
  title: string | null;
  text: string;
  requestId?: string | null;
  action: Action | null;
};

function waitText(error: unknown, prefix: string, verb: string): string {
  const seconds = retryAfterSeconds(error);
  return seconds === null
    ? `${prefix} Попробуйте позже.`
    : `${prefix} ${verb} через ${retryMinutes(seconds)} мин.`;
}

/** The "Responses → message → user action" table of DESIGN.md. */
function githubMessage(
  error: unknown,
  request: GitHubRequest,
  projects: ProjectSummary[],
): Message {
  switch (githubErrorCode(error)) {
    case "GITHUB_LOGIN_OUTDATED":
      return {
        tone: "label",
        title: "Логин на GitHub изменился",
        text: "Мы запомнили ваш прежний логин и не видим ваши репозитории. Войдите заново, и мы обновим его.",
        action: { kind: "login" },
      };
    case "GITHUB_RELATION_NOT_FOUND":
      return {
        tone: "error",
        title: "Связь с репозиторием не найдена",
        text: "Вы не владелец этого репозитория и не входите в список его контрибьюторов по данным GitHub. Если вы делали коммиты с личной почтой, GitHub может вас не показывать.",
        action: null,
      };
    case "GITHUB_REPOSITORY_ALREADY_LINKED": {
      const projectId = linkedProjectId(error);
      const project = projects.find((p) => p.id === projectId);
      const target = project
        ? `вашему проекту «${project.title ?? UNTITLED}»`
        : "другому вашему проекту";
      return {
        tone: "error",
        title: "Репозиторий уже привязан",
        text: `Этот репозиторий уже привязан к ${target}. Один репозиторий можно привязать только к одному вашему проекту.`,
        action:
          projectId === null
            ? null
            : {
                kind: "link",
                href: `/me/projects/${encodeURIComponent(projectId)}`,
                label: "Открыть проект",
              },
      };
    }
    case "GITHUB_REPOSITORY_NOT_FOUND":
      return {
        tone: "error",
        title: "Репозиторий не найден",
        text: "Такого публичного репозитория нет. Проверьте написание: «владелец/репозиторий». Приватные репозитории мы не читаем.",
        action: null,
      };
    case "NOT_FOUND":
      if (request === "import") {
        return {
          tone: "error",
          title: "Репозиторий не найден",
          text: "GitHub больше не отдаёт этот репозиторий: его могли удалить или сделать приватным. Список обновится в течение 5 минут.",
          action: null,
        };
      }
      if (request === "link") {
        return {
          tone: "error",
          title: "Проект не найден",
          text: "Такого проекта нет среди ваших.",
          action: { kind: "link", href: "/me/projects", label: "Мои проекты" },
        };
      }
      break;
    case "VALIDATION_ERROR":
      if (request === "link") {
        return { tone: "error", title: null, text: "Формат: владелец/репозиторий.", action: null };
      }
      break;
    case "PROJECT_LIMIT_REACHED":
      return {
        tone: "error",
        title: "Достигнут лимит проектов",
        text: `У вас уже ${projectLimit(error) ?? PROJECTS_MAX} проектов, это максимум. Удалите ненужный проект, чтобы импортировать репозиторий.`,
        action: { kind: "link", href: "/me/projects", label: "К моим проектам" },
      };
    case "GITHUB_USER_LIMIT_REACHED":
      return {
        tone: "label",
        title: "Слишком много обращений к GitHub",
        text: waitText(error, "Вы много раз обращались к GitHub за последний час.", "Повторите"),
        action: { kind: "wait" },
      };
    case "GITHUB_RATE_LIMITED":
      return {
        tone: "label",
        title: "GitHub ограничил запросы платформы",
        text: waitText(error, "Это не ваша вина: лимит общий на всех.", "Попробуйте"),
        action: { kind: "wait" },
      };
    case "GITHUB_UNAVAILABLE":
      return {
        tone: "error",
        title: "GitHub сейчас недоступен",
        text: "Не получилось связаться с GitHub. Повторите чуть позже.",
        action: { kind: "retry" },
      };
  }
  // INTERNAL_ERROR, a network failure and anything unexpected: as in the cabinet.
  return {
    tone: "error",
    title: null,
    text: error instanceof NetworkError ? NETWORK_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE,
    requestId: error instanceof ApiError ? error.requestId : null,
    // A failed list has nothing else on the page to click; an action is repeated by its button.
    action: request === "list" ? { kind: "retry" } : null,
  };
}

/**
 * A failed GitHub request: the title, the text and the action from DESIGN.md.
 * onRetry is called by «Повторить»: after GITHUB_UNAVAILABLE or a failed list,
 * and when a countdown has ended.
 */
export function GitHubErrorAlert({
  error,
  request,
  projects,
  waitLeft,
  onRetry,
}: {
  error: unknown;
  request: GitHubRequest;
  /** For the project title of GITHUB_REPOSITORY_ALREADY_LINKED. */
  projects: ProjectSummary[];
  /** Seconds left of the countdown (useRetryCountdown). */
  waitLeft: number;
  onRetry: () => void;
}) {
  const message = githubMessage(error, request, projects);
  const { action } = message;
  return (
    <div
      role="alert"
      className={cn(
        "flex w-full flex-col items-start gap-3 border-4 bg-bg px-4 py-4",
        message.tone === "label" ? "border-label" : "border-error",
      )}
    >
      {message.title && (
        <p
          className={cn(
            "font-heading text-xs leading-normal uppercase",
            message.tone === "label" ? "text-label" : "text-error",
          )}
        >
          {message.title}
        </p>
      )}
      <p className={message.title ? "text-text" : "text-error"}>{message.text}</p>
      {message.requestId && (
        <p className="text-sm text-text-muted">Код запроса: {message.requestId}</p>
      )}
      {action?.kind === "login" && (
        <Button asChild variant="label">
          <a href={githubLoginUrl()}>Войти через GitHub</a>
        </Button>
      )}
      {action?.kind === "link" && (
        <Button asChild variant="secondary">
          <Link href={action.href}>{action.label}</Link>
        </Button>
      )}
      {(action?.kind === "retry" || (action?.kind === "wait" && waitLeft === 0)) && (
        <Button variant="secondary" onClick={onRetry}>
          Повторить
        </Button>
      )}
      {action?.kind === "wait" && waitLeft > 0 && (
        <Button variant="secondary" disabled>
          Повторить через {retryMinutes(waitLeft)} мин
        </Button>
      )}
    </div>
  );
}
