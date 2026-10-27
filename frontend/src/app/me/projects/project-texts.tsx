import { cn } from "cn";

import {
  ApiError,
  FEATURED_MAX,
  PROJECTS_MAX,
  type ProjectField,
  type ProjectStatus,
  type ProjectVisibility,
} from "@/lib/api";

// Texts and badges shared by the project list and the project form
// (mockups my-projects.png and project-form.png, DESIGN.md).

export const PROJECT_FIELD_TEXT: Record<
  ProjectField,
  {
    label: string;
    /** For «Чтобы опубликовать, не хватает: …» on a list card. */
    short: string;
    hint: string;
    placeholder: string;
    required?: boolean;
  }
> = {
  title: {
    label: "Название",
    short: "название",
    hint: "Обязательно для публикации",
    placeholder: "Как называется проект",
    required: true,
  },
  summary: {
    label: "Коротко о проекте",
    short: "коротко о проекте",
    hint: "Показывается в карточке проекта. Обязательно для публикации",
    placeholder: "Одна-две строки: что это и зачем",
    required: true,
  },
  role: {
    label: "Роль",
    short: "роль",
    hint: "Обязательно для публикации",
    placeholder: "Например: бэкенд-разработчик",
    required: true,
  },
  technologies: {
    label: "Технологии",
    short: "технологии",
    hint: "До 20. Первая показывается в списке проектов на публичной странице",
    placeholder: "Например: Python",
    required: true,
  },
  contribution: {
    label: "Ваш вклад",
    short: "вклад",
    hint: "Обязательно для публикации",
    placeholder: "Что именно сделали вы лично",
    required: true,
  },
  description: {
    label: "Подробное описание",
    short: "подробное описание",
    hint: "Необязательно",
    placeholder: "Расскажите о проекте подробнее",
  },
  problem: {
    label: "Какую задачу решали",
    short: "задача",
    hint: "Необязательно",
    placeholder: "Какая была проблема",
  },
  results: {
    label: "Результат",
    short: "результат",
    hint: "Необязательно",
    placeholder: "К чему пришли",
  },
};

export const UNTITLED = "[Без названия]";
export const PROJECT_LIMIT_TEXT = `Можно создать не больше ${PROJECTS_MAX} проектов.`;
export const FEATURED_LIMIT_TEXT = `В главных уже ${FEATURED_MAX} проекта. Уберите один, чтобы добавить другой.`;

/**
 * Texts for API errors of project actions. reload: the screen's data is stale
 * and is loaded again. null for errors shown elsewhere (fields, PROJECT_INCOMPLETE,
 * network and unexpected errors).
 */
export function projectActionError(error: unknown): { text: string; reload: boolean } | null {
  if (!(error instanceof ApiError)) {
    return null;
  }
  switch (error.code) {
    case "PROJECT_LIMIT_REACHED":
      return { text: PROJECT_LIMIT_TEXT, reload: false };
    case "PROJECT_TRANSITION_INVALID":
      return {
        text: "Это действие недоступно в текущем состоянии проекта. Данные загружены заново.",
        reload: true,
      };
    case "PROJECT_NOT_FEATURABLE":
      return {
        text: "Главным можно сделать только опубликованный и видимый проект. Данные загружены заново.",
        reload: true,
      };
    case "FEATURED_LIMIT_REACHED":
      return { text: FEATURED_LIMIT_TEXT, reload: true };
    case "FEATURED_ORDER_MISMATCH":
      return { text: "Список главных изменился, порядок загружен заново.", reload: true };
    case "NOT_FOUND":
      return { text: "Проект не найден. Данные загружены заново.", reload: true };
    default:
      return null;
  }
}

const STATE_BADGE: Record<string, { label: string; className: string }> = {
  "DRAFT PRIVATE": { label: "Черновик", className: "bg-frame text-text" },
  "PUBLISHED PUBLIC": { label: "Опубликован", className: "bg-success text-outline" },
  "PUBLISHED PRIVATE": { label: "Скрыт", className: "bg-text-muted text-outline" },
  "ARCHIVED PRIVATE": { label: "В архиве", className: "bg-bg text-text-muted" },
};

const BADGE = "border-2 border-outline px-2 py-1 font-heading text-[0.625rem] leading-normal";

export function ProjectStateBadge({
  status,
  visibility,
}: {
  status: ProjectStatus;
  visibility: ProjectVisibility;
}) {
  // An unknown pair cannot come from the API (ADR-015); it is shown as text.
  const badge = STATE_BADGE[`${status} ${visibility}`] ?? {
    label: `${status} · ${visibility}`,
    className: "bg-bg text-text",
  };
  return <span className={cn(BADGE, badge.className)}>{badge.label}</span>;
}

export function FeaturedBadge({ position }: { position: number }) {
  return <span className={cn(BADGE, "bg-label text-outline")}>Главный: {position}</span>;
}

/** A section heading with the square marker of the mockups. */
export function SectionHeading({
  id,
  marker,
  children,
}: {
  id: string;
  marker: "label" | "muted";
  children: string;
}) {
  return (
    <div className="flex items-center gap-4">
      <span
        aria-hidden="true"
        className={cn("size-4 shrink-0", marker === "label" ? "bg-label" : "bg-text-muted")}
      />
      <h2 id={id} className="font-heading text-sm leading-normal uppercase">
        {children}
      </h2>
      <span aria-hidden="true" className="h-1 grow bg-frame" />
    </div>
  );
}
