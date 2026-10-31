import { cn } from "cn";

import type { GitHubRelation } from "@/lib/api";

import { BADGE } from "./projects/project-texts";

// Texts and marks for GitHub data in the cabinet ("GitHub in the cabinet" in
// DESIGN.md). Text from GitHub is rendered as text, never as HTML.

export const SOURCE_GITHUB = "Источник: GitHub";
export const NO_DESCRIPTION = "У этого репозитория нет описания на GitHub";

/**
 * The relation states a fact (ADR-017, ADR-019); NONE has no label, only the
 * warning below. Never «подтверждено»: a link does not confirm the project's text.
 */
export const RELATION_LABEL: Partial<Record<GitHubRelation, string>> = {
  OWNER: "Владелец репозитория",
  CONTRIBUTOR: "В списке контрибьюторов (по данным GitHub)",
};

export const UNAVAILABLE_WARNING =
  "Репозиторий недоступен: удалён или стал приватным. Публично данные GitHub не показываются.";
export const NO_RELATION_WARNING =
  "По данным GitHub вы сейчас не владелец репозитория и не в списке его контрибьюторов. " +
  "Публично данные GitHub не показываются, пока связь не найдётся снова.";
/** Shown instead of languages until the first successful sync (synced_at null). */
export const NOT_SYNCED_TEXT =
  "Языки и другие данные появятся после первой синхронизации с GitHub. Сейчас данные ещё не загружены.";

/** Links only to GitHub itself; any other URL from the API stays plain text. */
export function isGitHubUrl(url: string): boolean {
  return url.startsWith("https://github.com/");
}

/** `full_name`, linking to `html_url` in a new tab when it is a GitHub URL. */
export function RepositoryName({ fullName, htmlUrl }: { fullName: string; htmlUrl: string }) {
  if (!isGitHubUrl(htmlUrl)) {
    return <span className="break-all">{fullName}</span>;
  }
  return (
    <a
      href={htmlUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="break-all underline underline-offset-4"
    >
      {fullName}
    </a>
  );
}

const DATE_FORMAT = new Intl.DateTimeFormat("ru-RU");

/** «Обновлён: 30.10.2026» in the user's time zone; null hides the line. */
export function pushedAtText(pushedAt: string | null): string | null {
  if (pushedAt === null) {
    return null;
  }
  const date = new Date(pushedAt);
  return Number.isNaN(date.getTime()) ? null : `Обновлён: ${DATE_FORMAT.format(date)}`;
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
