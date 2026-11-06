import type { GitHubLanguage } from "@/lib/api";

/*
 * Languages of a repository as shares of GitHub's byte counts (ADR-019, DESIGN.md):
 * "доля кода в байтах, по данным GitHub". They are not skills and are never
 * levels or bars. The cabinet form shows 6 languages, a public card 3.
 */

/** How many languages get their own chip by default; the rest make one «Другие». */
export const LANGUAGES_SHOWN = 6;

export type LanguageShare = {
  name: string;
  /** Percent of all the repository's bytes; null when the sum is 0. */
  percent: number | null;
};

export type LanguageShares = {
  /** The first languages, in the given order (bytes descending). */
  shown: LanguageShare[];
  /** The rest summed, or null when there is no rest. */
  others: { percent: number | null } | null;
};

/** Shares of the languages in the API's order. The shares are not rounded here. */
export function languageShares(
  languages: GitHubLanguage[],
  shown: number = LANGUAGES_SHOWN,
): LanguageShares {
  const total = languages.reduce((sum, language) => sum + language.bytes, 0);
  const percent = (bytes: number) => (total === 0 ? null : (bytes / total) * 100);
  const rest = languages.slice(shown);
  return {
    shown: languages
      .slice(0, shown)
      .map((language) => ({ name: language.name, percent: percent(language.bytes) })),
    others:
      rest.length === 0
        ? null
        : { percent: percent(rest.reduce((sum, language) => sum + language.bytes, 0)) },
  };
}

/**
 * «62 %»: a whole percent with a non-breaking space; a share under 0.5 % is «<1 %».
 * The shares are not adjusted to add up to 100.
 */
export function shareText(percent: number): string {
  return percent < 0.5 ? "<1 %" : `${Math.round(percent)} %`;
}
