"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { SectionHeading } from "@/components/section-heading";
import { Alert } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  ApiError,
  archiveProject,
  deleteProject,
  FEATURED_MAX,
  featureProject,
  listProjects,
  missingProjectFields,
  PROJECTS_MAX,
  publishProject,
  reorderFeatured,
  setProjectVisibility,
  unfeatureProject,
  type FeaturedProjectsResponse,
  type ProjectField,
  type ProjectResponse,
  type ProjectSummary,
} from "@/lib/api";

import { CabinetPage, LoadErrorPanel, LoadingPanel, useAccount } from "../cabinet-page";
import {
  FEATURED_LIMIT_TEXT,
  FeaturedBadge,
  PROJECT_FIELD_TEXT,
  PROJECT_LIMIT_TEXT,
  projectActionError,
  ProjectStateBadge,
  UNTITLED,
} from "./project-texts";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; projects: ProjectSummary[] }
  | { status: "error"; error: unknown };

export function ProjectsScreen() {
  const router = useRouter();
  const account = useAccount();
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    listProjects({ signal: controller.signal }).then(
      (list) => setLoaded({ status: "ready", projects: list.items }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setLoaded({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [attempt, router]);

  function retry() {
    setLoaded({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  return (
    <CabinetPage account={account} tab="projects">
      {loaded.status === "loading" && <LoadingPanel />}
      {loaded.status === "error" && <LoadErrorPanel error={loaded.error} onRetry={retry} />}
      {loaded.status === "ready" && <ProjectsBoard initialProjects={loaded.projects} />}
    </CabinetPage>
  );
}

function toSummary(project: ProjectResponse): ProjectSummary {
  const { id, status, visibility, title, summary, technologies, featured_position } = project;
  const github = project.github && {
    full_name: project.github.full_name,
    html_url: project.github.html_url,
  };
  return { id, status, visibility, title, summary, technologies, featured_position, github };
}

function byPosition(projects: ProjectSummary[]): ProjectSummary[] {
  return projects
    .filter((project) => project.featured_position !== null)
    .sort((a, b) => a.featured_position! - b.featured_position!);
}

function ProjectsBoard({ initialProjects }: { initialProjects: ProjectSummary[] }) {
  const router = useRouter();
  const [projects, setProjects] = useState(initialProjects);
  // The action in flight, such as "publish:<id>"; every control is disabled meanwhile.
  const [pending, setPending] = useState<string | null>(null);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [message, setMessage] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<unknown>(null);
  const [incomplete, setIncomplete] = useState<{ id: string; fields: ProjectField[] } | null>(
    null,
  );
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null);

  const featured = byPosition(projects);
  const busy = pending !== null;
  const canFeature = featured.length < FEATURED_MAX;

  async function reload() {
    const list = await listProjects();
    setProjects(list.items);
  }

  async function run(key: string, call: () => Promise<void>) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(key);
    setMessage(null);
    setRequestError(null);
    setIncomplete(null);
    try {
      try {
        await call();
      } catch (error) {
        const missing = missingProjectFields(error);
        const known = projectActionError(error);
        if (missing.length > 0) {
          setIncomplete({ id: key.split(":")[1], fields: missing });
        } else if (known) {
          setMessage(known.text);
          if (known.reload) {
            await reload();
          }
        } else {
          throw error;
        }
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setRequestError(error);
    } finally {
      inFlight.current = false;
      setPending(null);
    }
  }

  function applyProject(project: ProjectResponse) {
    setProjects((current) => current.map((p) => (p.id === project.id ? toSummary(project) : p)));
  }

  /** Positions come from the server's response, never computed here. */
  function applyFeatured(response: FeaturedProjectsResponse) {
    const positions = new Map(response.items.map((item) => [item.project_id, item.position]));
    setProjects((current) =>
      current.map((p) => ({ ...p, featured_position: positions.get(p.id) ?? null })),
    );
  }

  /** A lifecycle action; a featured project leaves the featured set, so the list is reloaded. */
  function lifecycle(
    action: string,
    project: ProjectSummary,
    call: (id: string) => Promise<ProjectResponse>,
  ) {
    void run(`${action}:${project.id}`, async () => {
      applyProject(await call(project.id));
      if (project.featured_position !== null) {
        await reload();
      }
    });
  }

  function move(index: number, offset: -1 | 1) {
    const ids = featured.map((p) => p.id);
    [ids[index], ids[index + offset]] = [ids[index + offset], ids[index]];
    void run(`reorder:${ids[index]}`, async () => applyFeatured(await reorderFeatured(ids)));
  }

  function confirmDelete(project: ProjectSummary) {
    void run(`delete:${project.id}`, async () => {
      await deleteProject(project.id);
      setProjects((current) => current.filter((p) => p.id !== project.id));
    });
  }

  const atLimit = projects.length >= PROJECTS_MAX;

  return (
    <>
      <section className="flex flex-col gap-4 bg-panel px-6 py-6 shadow-panel sm:flex-row sm:items-center sm:justify-between sm:px-8">
        <div className="flex flex-col gap-3">
          <h1 className="font-heading text-lg leading-relaxed uppercase">Мои проекты</h1>
          <p className="text-base text-text-muted">
            Проектов: {projects.length} из {PROJECTS_MAX} · Главных: {featured.length} из{" "}
            {FEATURED_MAX}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          {atLimit ? (
            <>
              <Button variant="label" size="lg" disabled aria-describedby="project-limit">
                Новый проект
              </Button>
              <p id="project-limit" className="text-sm text-text-muted">
                {PROJECT_LIMIT_TEXT}
              </p>
            </>
          ) : (
            <Button asChild variant="label" size="lg">
              <Link href="/me/projects/new">Новый проект</Link>
            </Button>
          )}
        </div>
      </section>

      {message !== null && <Alert>{message}</Alert>}
      {requestError !== null && <RequestErrorAlert error={requestError} />}

      <section aria-labelledby="featured-heading" className="flex flex-col gap-4">
        <SectionHeading id="featured-heading" marker="label">
          Главные проекты
        </SectionHeading>
        <p className="text-text-muted">
          Покажутся на публичной странице первыми, в этом порядке. Не больше {FEATURED_MAX}.
          Опубликованный и видимый проект можно сделать главным. Если проект скрыть, отправить в
          архив или удалить, он пропадёт отсюда.
        </p>
        {featured.length > 0 && (
          <ol className="flex flex-col gap-4">
            {featured.map((project, index) => (
              <li
                key={project.id}
                className="flex flex-col gap-4 bg-panel px-4 py-4 shadow-panel sm:flex-row sm:items-center"
              >
                <div className="flex min-w-0 grow items-center gap-4">
                  <span
                    aria-hidden="true"
                    className="flex size-10 shrink-0 items-center justify-center border-4 border-outline bg-label font-heading text-xs text-outline"
                  >
                    {project.featured_position}
                  </span>
                  <div className="flex min-w-0 flex-col">
                    <p className="text-lg break-words">
                      <span className="sr-only">Место {project.featured_position}: </span>
                      {project.title ?? UNTITLED}
                    </p>
                    {project.summary && (
                      <p className="truncate text-text-muted">{project.summary}</p>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-3">
                  <Button
                    variant="secondary"
                    size="icon"
                    aria-label={`Выше: ${project.title ?? UNTITLED}`}
                    disabled={busy || index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <span aria-hidden="true">▲</span>
                  </Button>
                  <Button
                    variant="secondary"
                    size="icon"
                    aria-label={`Ниже: ${project.title ?? UNTITLED}`}
                    disabled={busy || index === featured.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <span aria-hidden="true">▼</span>
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={busy}
                    onClick={() =>
                      void run(`unfeature:${project.id}`, async () =>
                        applyFeatured(await unfeatureProject(project.id)),
                      )
                    }
                  >
                    Убрать из главных
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        )}
        {featured.length < FEATURED_MAX && (
          <p className="border-4 border-dashed border-frame px-4 py-4 text-text-muted">
            Свободное место для главного проекта: {FEATURED_MAX - featured.length} из{" "}
            {FEATURED_MAX}
          </p>
        )}
      </section>

      <section aria-labelledby="all-heading" className="flex flex-col gap-4">
        <SectionHeading id="all-heading" marker="muted">
          Все проекты
        </SectionHeading>
        {projects.length === 0 ? (
          <p className="text-lg text-text-muted">[Пока нет проектов]</p>
        ) : (
          <ul className="flex flex-col gap-6">
            {projects.map((project) => (
              <ProjectCard
                key={project.id}
                project={project}
                busy={busy}
                canFeature={canFeature}
                missing={incomplete?.id === project.id ? incomplete.fields : null}
                onPublish={() => lifecycle("publish", project, publishProject)}
                onHide={() =>
                  lifecycle("hide", project, (id) => setProjectVisibility(id, "PRIVATE"))
                }
                onShow={() =>
                  lifecycle("show", project, (id) => setProjectVisibility(id, "PUBLIC"))
                }
                onArchive={() => lifecycle("archive", project, archiveProject)}
                onFeature={() =>
                  void run(`feature:${project.id}`, async () =>
                    applyFeatured(await featureProject(project.id)),
                  )
                }
                onDelete={() => setDeleting(project)}
              />
            ))}
          </ul>
        )}
      </section>

      <DeleteDialog
        project={deleting}
        onCancel={() => setDeleting(null)}
        onConfirm={(project) => {
          setDeleting(null);
          confirmDelete(project);
        }}
      />
    </>
  );
}

function ProjectCard({
  project,
  busy,
  canFeature,
  missing,
  onPublish,
  onHide,
  onShow,
  onArchive,
  onFeature,
  onDelete,
}: {
  project: ProjectSummary;
  busy: boolean;
  canFeature: boolean;
  /** Fields from a failed publish of this project. */
  missing: ProjectField[] | null;
  onPublish: () => void;
  onHide: () => void;
  onShow: () => void;
  onArchive: () => void;
  onFeature: () => void;
  onDelete: () => void;
}) {
  const { id, status, visibility, featured_position: position } = project;
  const live = status === "PUBLISHED" && visibility === "PUBLIC";
  const hidden = status === "PUBLISHED" && visibility === "PRIVATE";
  const title = project.title ?? UNTITLED;
  const featureHintId = `feature-hint-${id}`;

  return (
    <li className="flex flex-col gap-4 bg-panel px-6 py-6 shadow-panel">
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-start sm:justify-between">
        <h3 className="text-xl break-words">{title}</h3>
        <div className="flex shrink-0 flex-wrap gap-2">
          <ProjectStateBadge status={status} visibility={visibility} />
          {position !== null && <FeaturedBadge position={position} />}
        </div>
      </div>
      {project.summary && <p className="break-words">{project.summary}</p>}
      {project.technologies.length > 0 && (
        <ul aria-label="Технологии" className="flex flex-wrap gap-2">
          {project.technologies.map((name) => (
            <li key={name} className="border-2 border-outline bg-bg px-2 py-1 text-sm">
              {name}
            </li>
          ))}
        </ul>
      )}
      {hidden && (
        <p className="text-sm text-text-muted">
          Опубликован, но не виден посетителям. Из главных убран.
        </p>
      )}
      {missing && (
        <p role="alert" className="text-sm text-error">
          Чтобы опубликовать, не хватает: {missing.map((f) => PROJECT_FIELD_TEXT[f].short).join(", ")}.
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href={`/me/projects/${encodeURIComponent(id)}`} aria-label={`Редактировать: ${title}`}>
            Редактировать
          </Link>
        </Button>
        {status === "DRAFT" && (
          <Button variant="label" disabled={busy} onClick={onPublish}>
            Опубликовать
          </Button>
        )}
        {status === "ARCHIVED" && (
          <Button variant="label" disabled={busy} onClick={onPublish}>
            Опубликовать снова
          </Button>
        )}
        {live && position === null && (
          <Button
            variant="label"
            disabled={busy || !canFeature}
            aria-describedby={canFeature ? undefined : featureHintId}
            onClick={onFeature}
          >
            Сделать главным
          </Button>
        )}
        {live && (
          <Button variant="secondary" disabled={busy} onClick={onHide}>
            Скрыть
          </Button>
        )}
        {hidden && (
          <Button variant="secondary" disabled={busy} onClick={onShow}>
            Показать
          </Button>
        )}
        {status === "PUBLISHED" && (
          <Button variant="secondary" disabled={busy} onClick={onArchive}>
            В архив
          </Button>
        )}
        {(status === "DRAFT" || status === "ARCHIVED") && (
          <Button variant="danger" disabled={busy} onClick={onDelete}>
            Удалить
          </Button>
        )}
      </div>
      {live && position === null && !canFeature && (
        <p id={featureHintId} className="text-sm text-text-muted">
          {FEATURED_LIMIT_TEXT}
        </p>
      )}
      {position !== null && (
        <p className="text-sm text-text-muted">«Скрыть» и «В архив» уберут проект из главных.</p>
      )}
    </li>
  );
}

function DeleteDialog({
  project,
  onCancel,
  onConfirm,
}: {
  project: ProjectSummary | null;
  onCancel: () => void;
  onConfirm: (project: ProjectSummary) => void;
}) {
  return (
    <AlertDialog
      open={project !== null}
      onOpenChange={(open) => {
        if (!open) {
          onCancel();
        }
      }}
    >
      {project && (
        <AlertDialogContent>
          <AlertDialogTitle>Удалить проект?</AlertDialogTitle>
          {/* Only drafts and archived projects are deleted here, so the text
              says nothing about featured projects or the archive (DESIGN.md). */}
          <AlertDialogDescription>
            Проект «{project.title ?? UNTITLED}» удалится навсегда вместе со своими данными.
            Отменить нельзя.
          </AlertDialogDescription>
          <div className="flex flex-wrap gap-4">
            <AlertDialogAction asChild>
              <Button
                variant="destructive"
                onClick={(event) => {
                  event.preventDefault();
                  onConfirm(project);
                }}
              >
                Удалить навсегда
              </Button>
            </AlertDialogAction>
            <AlertDialogCancel asChild>
              <Button variant="secondary">Отмена</Button>
            </AlertDialogCancel>
          </div>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}
