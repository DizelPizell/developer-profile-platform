import { cn } from "cn";

import { BADGE } from "./projects/project-texts";

// Texts and marks for GitHub data in the cabinet ("GitHub in the cabinet" in
// DESIGN.md). Text from GitHub is rendered as text, never as HTML.

export const SOURCE_GITHUB = "Источник: GitHub";
export const NO_DESCRIPTION = "У этого репозитория нет описания на GitHub";

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

/** «Форк» and «В архиве на GitHub»; the list items carry no parent name. */
export function RepositoryLabels({ fork, archived }: { fork: boolean; archived: boolean }) {
  return (
    <>
      {fork && <span className={cn(BADGE, "bg-frame text-text")}>Форк</span>}
      {archived && <span className={cn(BADGE, "bg-bg text-text-muted")}>В архиве на GitHub</span>}
    </>
  );
}
