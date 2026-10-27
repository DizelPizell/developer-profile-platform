import { cn } from "cn";
import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { PixelAvatar } from "@/components/pixel-avatar";
import { SectionHeading } from "@/components/section-heading";
import { Button } from "@/components/ui/button";
import type { PublicFeaturedProject, PublicProfile, PublicProject } from "@/lib/api";

/** Technology chips on a featured card (DESIGN.md). */
const FEATURED_TECHNOLOGIES = 3;

const CHIP = "border-2 border-outline bg-bg px-2 py-1 text-sm break-all";

// Public profile per public-profile.png, only the blocks that have API data
// (DESIGN.md). Every value is rendered as React text, never as HTML.
export function ProfileView({ profile }: { profile: PublicProfile }) {
  // Only an https avatar is loaded; anything else falls back to the pixel avatar.
  const avatarUrl = profile.avatar_url?.startsWith("https://") ? profile.avatar_url : null;
  const hasProjects = profile.featured.length > 0 || profile.other.length > 0;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-8 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <BrandMark />
        <Button asChild>
          <Link href="/login">Войти через GitHub</Link>
        </Button>
      </header>

      <main className="flex flex-col gap-8">
        <section className="flex flex-col gap-8 bg-panel px-8 py-8 shadow-panel sm:flex-row sm:items-center">
          <figure className="flex shrink-0 flex-col items-center gap-2">
            {avatarUrl ? (
              // A GitHub avatar; next/image would need a remote host config.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={avatarUrl}
                alt=""
                referrerPolicy="no-referrer"
                className="size-40 rounded-full border-4 border-accent bg-panel shadow-pixel"
              />
            ) : (
              <PixelAvatar className="size-40" />
            )}
            <figcaption className="text-sm text-text-muted">Источник: GitHub</figcaption>
          </figure>

          <div className="flex min-w-0 flex-col gap-4">
            <h1 className="text-4xl break-words">{profile.display_name ?? `@${profile.github_login}`}</h1>
            <p className="text-lg break-all text-text-muted">
              @{profile.github_login} <span className="text-sm">· Источник: GitHub</span>
            </p>
            {profile.headline && (
              <p className="flex flex-wrap items-center gap-3 text-lg">
                <span className="bg-label px-2 py-1 font-heading text-xs leading-normal text-outline uppercase">
                  Класс
                </span>
                <span className="break-words">{profile.headline}</span>
              </p>
            )}
            {profile.location && (
              <p className="break-words text-text-muted">Локация: {profile.location}</p>
            )}
            <div className="flex flex-wrap gap-4">
              <Button asChild>
                <a
                  href={`https://github.com/${encodeURIComponent(profile.github_login)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  GitHub
                </a>
              </Button>
              {hasProjects && (
                <Button asChild variant="secondary">
                  <a href="#projects">Проекты</a>
                </Button>
              )}
            </div>
          </div>
        </section>

        {profile.bio && (
          <section aria-labelledby="about-title" className="flex flex-col gap-4 bg-panel px-8 py-8 shadow-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="about-title" className="font-heading text-sm leading-normal uppercase">
                О себе
              </h2>
              <AuthorMark />
            </div>
            <p className="text-lg leading-relaxed break-words whitespace-pre-line">{profile.bio}</p>
          </section>
        )}

        {hasProjects && (
          <div id="projects" className="flex scroll-mt-6 flex-col gap-8">
            {profile.featured.length > 0 && <FeaturedProjects projects={profile.featured} />}
            {profile.other.length > 0 && <OtherProjects projects={profile.other} />}
          </div>
        )}
      </main>
    </div>
  );
}

/** The developer is the source of these blocks (DESIGN.md, content rules). */
function AuthorMark() {
  return (
    <span className="shrink-0 border-2 border-text-muted px-2 py-1 font-heading text-[10px] leading-normal text-text-muted uppercase">
      От автора
    </span>
  );
}

// No link to the project page and no image area: both come in Phase 4.
function FeaturedProjects({ projects }: { projects: PublicFeaturedProject[] }) {
  return (
    <section aria-labelledby="featured-title" className="flex flex-col gap-6">
      <SectionHeading id="featured-title" marker="label" aside={<AuthorMark />}>
        Главные проекты
      </SectionHeading>
      <ol className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {projects.map((project) => (
          <li key={project.id} className="flex min-w-0 flex-col gap-4 bg-panel px-6 py-6 shadow-panel">
            <span className="self-start border-2 border-outline bg-label px-2 py-1 font-heading text-[10px] leading-normal text-outline uppercase">
              Главный {project.position}
            </span>
            <h3 className="text-xl break-words">{project.title}</h3>
            <p className="line-clamp-4 break-words">{project.summary}</p>
            {project.technologies.length > 0 && (
              <ul aria-label="Технологии" className="flex flex-wrap gap-2">
                {project.technologies.slice(0, FEATURED_TECHNOLOGIES).map((name) => (
                  <li key={name} className={CHIP}>
                    {name}
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-auto text-sm break-words text-text-muted">Моя роль: {project.role}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

// On narrow screens the badge goes under the text, so a long technology name
// does not squeeze the title.
function OtherProjects({ projects }: { projects: PublicProject[] }) {
  return (
    <section aria-labelledby="other-title" className="flex flex-col gap-6">
      <SectionHeading id="other-title" marker="muted" aside={<AuthorMark />}>
        Другие проекты
      </SectionHeading>
      <ul className="flex flex-col gap-4">
        {projects.map((project) => (
          <li
            key={project.id}
            className="flex flex-col items-start gap-3 bg-panel px-6 py-4 shadow-panel sm:flex-row sm:items-center sm:gap-4"
          >
            <div className="flex w-full min-w-0 grow flex-col gap-1 sm:w-auto">
              <h3 className="text-lg break-words">{project.title}</h3>
              <p className="truncate text-text-muted">{project.summary}</p>
            </div>
            {project.technologies.length > 0 && (
              <span className={cn(CHIP, "shrink-0 sm:max-w-[40%]")}>{project.technologies[0]}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
