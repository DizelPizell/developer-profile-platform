import {
  LANGUAGES_CAPTION,
  RELATION_LABEL,
  RepositoryName,
  SOURCE_GITHUB,
} from "@/components/github-texts";
import type { PublicGitHub } from "@/lib/api";
import { languageShares, shareText } from "@/lib/github-languages";

// The GitHub block of public project cards (ADR-019, public-cards.png; DESIGN.md,
// "GitHub on public cards"). Server rendered: the date is a day in UTC, so the server
// and the reader see the same text. Every value from GitHub is rendered as React text.
// `pushed_at` is not read and not shown.

export const CHIP = "border-2 border-outline bg-bg px-2 py-1 text-sm break-all";

/** Language chips on a card; the rest make one «Другие». */
const CARD_LANGUAGES = 3;

const SOURCE = "font-heading text-[10px] leading-normal text-text-muted uppercase";
const DIVIDER = "border-t-4 border-outline";

/** «01.11.2026», the day in UTC; the time is not shown. */
const DATE_FORMAT = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "UTC",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

/** The reader lets through only a valid date, so format() does not throw here. */
function DataDate({ syncedAt }: { syncedAt: string }) {
  return (
    <p className="text-sm text-text-muted">
      Данные GitHub от <time dateTime={syncedAt}>{DATE_FORMAT.format(new Date(syncedAt))}</time>
    </p>
  );
}

/** «Форк {parent}», or «Форк» when GitHub gave no parent, and «В архиве на GitHub». */
function RepositoryMarks({ github }: { github: PublicGitHub }) {
  return (
    <>
      {github.is_fork && (
        <span className={CHIP}>
          {github.parent_full_name ? `Форк ${github.parent_full_name}` : "Форк"}
        </span>
      )}
      {github.is_archived && <span className={CHIP}>В архиве на GitHub</span>}
    </>
  );
}

/** Shares of bytes, never levels or bars; hidden with its caption when there are none. */
function CardLanguages({ github }: { github: PublicGitHub }) {
  if (github.languages.length === 0) {
    return null;
  }
  const { shown, others } = languageShares(github.languages, CARD_LANGUAGES);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm text-text-muted">{LANGUAGES_CAPTION}</p>
      <ul aria-label="Языки" className="flex flex-wrap gap-2">
        {shown.map(({ name, percent }, index) => (
          <li key={index} className={CHIP}>
            {percent === null ? name : `${name} ${shareText(percent)}`}
          </li>
        ))}
        {others && (
          <li className={`${CHIP} text-text-muted`}>
            {others.percent === null ? "Другие" : `Другие — ${shareText(others.percent)}`}
          </li>
        )}
      </ul>
    </div>
  );
}

/** The full block, at the bottom of a featured card. */
export function CardGitHub({ github }: { github: PublicGitHub }) {
  const hasMarks = github.is_fork || github.is_archived;
  return (
    <div className={`flex flex-col gap-3 pt-4 ${DIVIDER}`}>
      <p className={SOURCE}>{SOURCE_GITHUB}</p>
      <p className="text-text-muted">
        <RepositoryName fullName={github.full_name} htmlUrl={github.html_url} />
      </p>
      <p className="break-words">{RELATION_LABEL[github.relation]}</p>
      {hasMarks && (
        <div className="flex flex-wrap gap-2">
          <RepositoryMarks github={github} />
        </div>
      )}
      {github.description && <p className="line-clamp-2 break-words">{github.description}</p>}
      <CardLanguages github={github} />
      <DataDate syncedAt={github.synced_at} />
    </div>
  );
}

/** The compact block of a row: no description and no languages. */
export function RowGitHub({ github }: { github: PublicGitHub }) {
  return (
    <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 pt-3 ${DIVIDER}`}>
      <p className={SOURCE}>{SOURCE_GITHUB}</p>
      <p className="min-w-0 text-text-muted">
        <RepositoryName fullName={github.full_name} htmlUrl={github.html_url} />
      </p>
      <p className="min-w-0 break-words">{RELATION_LABEL[github.relation]}</p>
      <RepositoryMarks github={github} />
      <DataDate syncedAt={github.synced_at} />
    </div>
  );
}
