import { cn } from "cn";

import { LANGUAGES_CAPTION, SOURCE_GITHUB } from "@/components/github-texts";
import type { GitHubLanguage } from "@/lib/api";
import { languageShares, shareText } from "@/lib/github-languages";

import { BADGE } from "./projects/project-texts";

// Texts and marks for GitHub data in the cabinet ("GitHub in the cabinet" in
// DESIGN.md). Text from GitHub is rendered as text, never as HTML.

export const NO_DESCRIPTION = "У этого репозитория нет описания на GitHub";

export const UNAVAILABLE_WARNING =
  "Репозиторий недоступен: удалён или стал приватным. Публично данные GitHub не показываются.";
export const NO_RELATION_WARNING =
  "По данным GitHub вы сейчас не владелец репозитория и не в списке его контрибьюторов. " +
  "Публично данные GitHub не показываются, пока связь не найдётся снова.";
/** Shown instead of languages until the first successful sync (synced_at null). */
export const NOT_SYNCED_TEXT =
  "Языки и другие данные появятся после первой синхронизации с GitHub. Сейчас данные ещё не загружены.";

export const NO_LANGUAGES_TEXT = "GitHub не нашёл в репозитории кода на известных ему языках.";

const DATE_FORMAT = new Intl.DateTimeFormat("ru-RU");

/** «Обновлён: 30.10.2026» in the user's time zone; null hides the line. */
export function pushedAtText(pushedAt: string | null): string | null {
  if (pushedAt === null) {
    return null;
  }
  const date = new Date(pushedAt);
  return Number.isNaN(date.getTime()) ? null : `Обновлён: ${DATE_FORMAT.format(date)}`;
}

const DATE_TIME_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** «01.11.2026, 12:30» in the user's time zone; null for a value that is not a date. */
export function dateTimeText(value: string): string | null {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : DATE_TIME_FORMAT.format(date);
}

/**
 * «Данные GitHub от 01.11.2026, 12:30» from synced_at, so old data reads as old
 * (ADR-019); null hides the line.
 */
export function syncedAtText(syncedAt: string | null): string | null {
  const text = syncedAt === null ? null : dateTimeText(syncedAt);
  return text === null ? null : `Данные GitHub от ${text}`;
}

export function SourceBadge() {
  return <span className={cn(BADGE, "bg-bg text-label")}>{SOURCE_GITHUB}</span>;
}

/** «Форк {parent}» (or «Форк» without a parent, as in the list) and «В архиве на GitHub». */
export function RepositoryLabels({
  fork,
  parent = null,
  archived,
}: {
  fork: boolean;
  parent?: string | null;
  archived: boolean;
}) {
  return (
    <>
      {fork && (
        <span className={cn(BADGE, "break-all bg-frame text-text")}>
          {parent === null ? "Форк" : `Форк ${parent}`}
        </span>
      )}
      {archived && <span className={cn(BADGE, "bg-bg text-text-muted")}>В архиве на GitHub</span>}
    </>
  );
}

/** The dashed box of a placeholder: no data yet, or no languages. */
export function DataPlaceholder({ children }: { children: string }) {
  return (
    <p className="border-4 border-dashed border-frame px-4 py-3 text-sm text-text-muted">
      {children}
    </p>
  );
}

/**
 * The first 6 languages as chips «Python 62 %», the rest as one «Другие — N %».
 * Names come from GitHub and are rendered as text.
 */
export function RepositoryLanguages({ languages }: { languages: GitHubLanguage[] }) {
  if (languages.length === 0) {
    return <DataPlaceholder>{NO_LANGUAGES_TEXT}</DataPlaceholder>;
  }
  const { shown, others } = languageShares(languages);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-text-muted">{LANGUAGES_CAPTION}</p>
      <ul aria-label="Языки" className="flex flex-wrap gap-2">
        {shown.map(({ name, percent }, index) => (
          <li key={index} className={cn(BADGE, "break-all bg-panel text-text")}>
            {percent === null ? name : `${name} ${shareText(percent)}`}
          </li>
        ))}
        {others && (
          <li className={cn(BADGE, "bg-frame text-text-muted")}>
            {others.percent === null ? "Другие" : `Другие — ${shareText(others.percent)}`}
          </li>
        )}
      </ul>
    </div>
  );
}
