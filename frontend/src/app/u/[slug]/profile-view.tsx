import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { PixelAvatar } from "@/components/pixel-avatar";
import { Button } from "@/components/ui/button";
import type { PublicProfile } from "@/lib/api";

// Public profile per public-profile.png, only the blocks that have API data
// (DESIGN.md). Every value is rendered as React text, never as HTML.
export function ProfileView({ profile }: { profile: PublicProfile }) {
  // Only an https avatar is loaded; anything else falls back to the pixel avatar.
  const avatarUrl = profile.avatar_url?.startsWith("https://") ? profile.avatar_url : null;

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
            <div>
              <Button asChild>
                <a
                  href={`https://github.com/${encodeURIComponent(profile.github_login)}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  GitHub
                </a>
              </Button>
            </div>
          </div>
        </section>

        {profile.bio && (
          <section aria-labelledby="about-title" className="flex flex-col gap-4 bg-panel px-8 py-8 shadow-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="about-title" className="font-heading text-sm leading-normal uppercase">
                О себе
              </h2>
              <span className="border-2 border-text-muted px-2 py-1 font-heading text-[10px] leading-normal text-text-muted uppercase">
                От автора
              </span>
            </div>
            <p className="text-lg leading-relaxed break-words whitespace-pre-line">{profile.bio}</p>
          </section>
        )}
      </main>
    </div>
  );
}
