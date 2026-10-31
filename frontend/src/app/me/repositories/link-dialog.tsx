"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import {
  ApiError,
  githubErrorCode,
  linkedProjectId,
  linkRepository,
  type GitHubRepository,
  type ProjectResponse,
  type ProjectSummary,
} from "@/lib/api";

import { GitHubErrorAlert, useRetryCountdown } from "../github-error";
import { ProjectStateBadge, UNTITLED } from "../projects/project-texts";

/**
 * «Привязать к проекту»: a modal choice of one of the user's projects. Focus
 * starts on the first project, Escape and «Отмена» close it, and errors stay
 * inside it. It is mounted per repository, so every opening starts clean.
 */
export function LinkDialog({
  repository,
  projects,
  onClose,
  onLinked,
  onAlreadyLinked,
  onCloseAutoFocus,
}: {
  repository: GitHubRepository;
  projects: ProjectSummary[];
  onClose: () => void;
  onLinked: (project: ProjectResponse) => void;
  /** GITHUB_REPOSITORY_ALREADY_LINKED: the repository is linked to this project. */
  onAlreadyLinked: (projectId: string) => void;
  onCloseAutoFocus: (event: Event) => void;
}) {
  const router = useRouter();
  const [selected, setSelected] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [error, setError] = useState<unknown>(null);
  const { left: waitLeft, start: startWait, stop: stopWait } = useRetryCountdown();
  const firstProject = useRef<HTMLInputElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);

  async function link() {
    if (selected === null || inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    setError(null);
    stopWait();
    try {
      // The parent closes the dialog; this component goes away with it.
      onLinked(await linkRepository(selected, repository.full_name));
      return;
    } catch (linkError) {
      if (linkError instanceof ApiError && linkError.status === 401) {
        router.replace("/login");
        return;
      }
      setError(linkError);
      startWait(linkError);
      const projectId = linkedProjectId(linkError);
      if (projectId !== null) {
        onAlreadyLinked(projectId);
      }
    }
    inFlight.current = false;
    setPending(false);
  }

  function retry() {
    if (githubErrorCode(error) === "GITHUB_UNAVAILABLE") {
      void link();
    } else {
      // The countdown has ended: the message closes and the user repeats the link.
      setError(null);
    }
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        // A link in flight finishes first; its answer decides what the page shows.
        if (!open && !pending) {
          onClose();
        }
      }}
    >
      <DialogContent
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          (firstProject.current ?? cancel.current)?.focus();
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        <DialogTitle>Привязать к проекту</DialogTitle>
        <p className="text-lg break-all">Репозиторий: {repository.full_name}</p>

        {projects.length === 0 ? (
          <p className="text-lg text-text-muted">[Пока нет проектов]</p>
        ) : (
          <fieldset className="flex flex-col gap-3">
            <legend className="sr-only">Проект</legend>
            {projects.map((project, index) => {
              const hintId = `link-hint-${project.id}`;
              return (
                <div key={project.id} className="flex flex-col gap-1">
                  <label className="flex cursor-pointer flex-wrap items-center gap-3">
                    <input
                      ref={index === 0 ? firstProject : undefined}
                      type="radio"
                      name="link-project"
                      value={project.id}
                      checked={selected === project.id}
                      disabled={pending}
                      aria-describedby={project.github ? hintId : undefined}
                      onChange={() => setSelected(project.id)}
                      className="size-5 accent-accent"
                    />
                    <span className="text-lg break-words">{project.title ?? UNTITLED}</span>
                    <ProjectStateBadge status={project.status} visibility={project.visibility} />
                  </label>
                  {project.github && (
                    <p id={hintId} className="pl-8 text-sm break-words text-label">
                      Уже привязан к {project.github.full_name}. Новая привязка заменит старую.
                    </p>
                  )}
                </div>
              );
            })}
          </fieldset>
        )}

        <DialogDescription>Привязка не меняет статус, видимость и тексты проекта.</DialogDescription>

        {error !== null && (
          <GitHubErrorAlert
            error={error}
            request="link"
            projects={projects}
            waitLeft={waitLeft}
            onRetry={retry}
          />
        )}

        <div className="flex flex-wrap gap-3">
          {projects.length > 0 && (
            <Button disabled={selected === null || pending || waitLeft > 0} onClick={() => void link()}>
              {pending ? "Проверяем на GitHub…" : "Привязать"}
            </Button>
          )}
          <Button ref={cancel} variant="secondary" disabled={pending} onClick={onClose}>
            Отмена
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
