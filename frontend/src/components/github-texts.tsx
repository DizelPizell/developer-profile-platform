import type { GitHubRelation } from "@/lib/api";

// GitHub texts shared by the cabinet and the public page (DESIGN.md). Text from
// GitHub is rendered as text, never as HTML.

export const SOURCE_GITHUB = "Источник: GitHub";

/** Languages are shares of bytes, labelled as such (ADR-019); never skills or levels. */
export const LANGUAGES_CAPTION = "Доля кода в байтах, по данным GitHub";

/**
 * The relation states a fact (ADR-017, ADR-019). NONE has no label: the cabinet shows
 * a warning, and the public API returns no `github` for it. Never «подтверждено»: a
 * link does not confirm the project's text.
 */
export const RELATION_LABEL: Record<Exclude<GitHubRelation, "NONE">, string> = {
  OWNER: "Владелец репозитория",
  CONTRIBUTOR: "В списке контрибьюторов (по данным GitHub)",
};

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
