import Link from "next/link";

import { SectionHeading } from "@/components/section-heading";
import { Button } from "@/components/ui/button";
import { mediaUrl, type PublicProjectPage, type PublicScreenshot } from "@/lib/api";

import { CardGitHub, CHIP } from "../../project-github";
import { AnalyticsTracker } from "../../analytics-tracker";
import { AuthorMark, PublicHeader } from "../../public-parts";

const PANEL = "bg-panel px-6 py-6 shadow-panel sm:px-8 sm:py-8";
const SHOT_IMAGE = "h-auto w-full border-4 border-outline bg-bg";

// The public project page per project-page.png (DESIGN.md, "Public project page"):
// the demo first, then the screenshots, the developer's texts and the GitHub data.
// Server rendered; the only client JavaScript is the analytics tracker. Every value
// is React text.
export function ProjectView({ project }: { project: PublicProjectPage }) {
  const { demo_url: demoUrl, screenshots } = project;
  // With a demo the first screenshot is its preview and the gallery starts from the second.
  const preview = demoUrl ? (screenshots[0] ?? null) : null;
  const gallery = preview ? screenshots.slice(1) : screenshots;
  const firstNumber = preview ? 2 : 1;

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-8 p-4 sm:p-6">
      <AnalyticsTracker slug={project.owner.slug} projectId={project.id} />
      <PublicHeader />

      <main className="flex flex-col gap-8">
        <Link
          href={`/u/${encodeURIComponent(project.owner.slug)}`}
          className="self-start text-lg break-all underline underline-offset-4"
        >
          ‹ {project.owner.display_name}
        </Link>

        <section className={`flex flex-col gap-4 ${PANEL}`}>
          {/* A row of its own, so the mark keeps its width in the column. */}
          <div className="flex">
            <AuthorMark />
          </div>
          <h1 className="text-3xl font-medium wrap-anywhere sm:text-4xl">{project.title}</h1>
          <p className="text-lg break-words whitespace-pre-line">{project.summary}</p>
          {project.technologies.length > 0 && (
            <ul aria-label="Технологии" className="flex flex-wrap gap-2">
              {project.technologies.map((name) => (
                <li key={name} className={CHIP}>
                  {name}
                </li>
              ))}
            </ul>
          )}
          <p className="break-words text-text-muted">Моя роль: {project.role}</p>
        </section>

        {demoUrl && <DemoBlock url={demoUrl} preview={preview} title={project.title} />}

        {gallery.length > 0 && (
          <section aria-labelledby="shots-title" className="flex flex-col gap-6">
            <SectionHeading id="shots-title" marker="label" aside={<AuthorMark />}>
              Скриншоты
            </SectionHeading>
            <ul className={gallery.length > 1 ? "grid gap-6 sm:grid-cols-2" : "grid gap-6"}>
              {gallery.map((shot, index) => (
                <li key={shot.url}>
                  <Screenshot shot={shot} number={firstNumber + index} title={project.title} />
                </li>
              ))}
            </ul>
          </section>
        )}

        <TextBlock id="problem-title" title="Задача" text={project.problem} />
        <TextBlock id="contribution-title" title="Мой вклад" text={project.contribution} />
        <TextBlock id="results-title" title="Результат" text={project.results} />
        <TextBlock id="description-title" title="Подробнее" text={project.description} />

        {project.github && (
          <section aria-labelledby="github-title" className="flex flex-col gap-6">
            <SectionHeading id="github-title" marker="muted">
              Данные GitHub
            </SectionHeading>
            <div className={PANEL}>
              <CardGitHub github={project.github} divided={false} />
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

function shotAlt(shot: PublicScreenshot, number: number, title: string): string {
  return shot.caption ?? `Скриншот ${number} проекта «${title}»`;
}

function DemoBlock({
  url,
  preview,
  title,
}: {
  url: string;
  preview: PublicScreenshot | null;
  title: string;
}) {
  // An IDN host reads as punycode, so the text cannot hide where the link leads.
  const { host } = new URL(url);
  const previewSrc = preview && mediaUrl(preview.url);
  return (
    <section aria-labelledby="demo-title" className="flex flex-col gap-6">
      <SectionHeading id="demo-title" marker="label" aside={<AuthorMark />}>
        Демо
      </SectionHeading>
      <div className={`grid items-start gap-6 md:grid-cols-[3fr_2fr] md:gap-7 ${PANEL}`}>
        {preview && previewSrc ? (
          // A media file of the API origin; next/image would need a remote host config.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewSrc}
            width={preview.width}
            height={preview.height}
            alt={shotAlt(preview, 1, title)}
            className={SHOT_IMAGE}
          />
        ) : (
          <p className="border-4 border-outline bg-bg px-4 py-6 text-xl font-medium break-all sm:px-6 sm:py-10 sm:text-3xl">
            {host}
          </p>
        )}
        <div className="flex flex-col gap-4">
          {preview?.caption && <p className="text-sm break-words text-text-muted">{preview.caption}</p>}
          <Button asChild size="lg" className="w-full md:w-auto md:self-start">
            <a href={url} target="_blank" rel="noopener noreferrer nofollow ugc" data-analytics="DEMO_CLICK">
              Открыть демо ↗
            </a>
          </Button>
          <p className="text-sm break-all text-text-muted">{host} · откроется в новой вкладке</p>
          <p className="text-sm text-text-muted">Ссылку указал автор, платформа сайт демо не проверяет.</p>
        </div>
      </div>
    </section>
  );
}

function Screenshot({ shot, number, title }: { shot: PublicScreenshot; number: number; title: string }) {
  const src = mediaUrl(shot.url);
  if (!src) {
    return null;
  }
  return (
    <figure className="flex flex-col gap-2">
      <a
        href={src}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Открыть скриншот ${number} в полном размере`}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- see DemoBlock */}
        <img
          src={src}
          width={shot.width}
          height={shot.height}
          loading="lazy"
          alt={shotAlt(shot, number, title)}
          className={SHOT_IMAGE}
        />
      </a>
      {shot.caption && (
        <figcaption className="text-sm break-words text-text-muted">{shot.caption}</figcaption>
      )}
    </figure>
  );
}

/** A text of the developer; null hides the block. */
function TextBlock({ id, title, text }: { id: string; title: string; text: string | null }) {
  if (text === null) {
    return null;
  }
  return (
    <section aria-labelledby={id} className="flex flex-col gap-6">
      <SectionHeading id={id} marker="label" aside={<AuthorMark />}>
        {title}
      </SectionHeading>
      <div className={PANEL}>
        <p className="max-w-[70ch] text-lg leading-relaxed text-pretty break-words whitespace-pre-line">
          {text}
        </p>
      </div>
    </section>
  );
}
