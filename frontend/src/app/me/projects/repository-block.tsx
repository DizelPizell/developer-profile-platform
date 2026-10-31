"use client";

import { cn } from "cn";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  githubErrorCode,
  isRepositoryFullName,
  linkedProjectId,
  linkRepository,
  listProjects,
  unlinkRepository,
  type ProjectGitHub,
  type ProjectResponse,
  type ProjectSummary,
} from "@/lib/api";

import { GitHubErrorAlert, useRetryCountdown } from "../github-error";
import {
  NO_DESCRIPTION,
  NO_RELATION_WARNING,
  NOT_SYNCED_TEXT,
  pushedAtText,
  RELATION_LABEL,
  RepositoryLabels,
  RepositoryName,
  SourceBadge,
  UNAVAILABLE_WARNING,
} from "../github-texts";
import { BADGE } from "./project-texts";

const FORMAT_ERROR = "Формат: владелец/репозиторий.";

/** A failed link with the name it sent, for «Повторить» after a 502. */
type LinkError = { error: unknown; fullName: string };

/**
 * «Репозиторий GitHub» in the project form (DESIGN.md). Link and unlink act at
 * once, apart from «Сохранить»: the form takes only `github` from their answer,
 * so unsaved edits in the fields stay.
 */
export function RepositoryBlock({
  project,
  busy,
  onPendingChange,
  onGitHub,
  onNotFound,
}: {
  /** The stored project; null on /me/projects/new. */
  project: ProjectResponse | null;
  /** A request of the form itself is in flight. */
  busy: boolean;
  /** Lets the form disable its buttons while a link or unlink runs. */
  onPendingChange: (pending: boolean) => void;
  onGitHub: (github: ProjectGitHub | null) => void;
  onNotFound: () => void;
}) {
  const router = useRouter();
  const [value, setValue] = useState("");
  const [replacing, setReplacing] = useState(false);
  const [formatError, setFormatError] = useState(false);
  const [pending, setPending] = useState<"link" | "unlink" | null>(null);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [linkError, setLinkError] = useState<LinkError | null>(null);
  const [unlinkError, setUnlinkError] = useState<unknown>(null);
  const [confirming, setConfirming] = useState(false);
  // Read only for GITHUB_REPOSITORY_ALREADY_LINKED, to name the other project.
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const { left: waitLeft, start: startWait, stop: stopWait } = useRetryCountdown();
  const input = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  // Where the focus goes once the block shows the other state.
  const focusNext = useRef<"input" | "panel" | null>(null);

  useEffect(() => {
    if (focusNext.current === "input") {
      input.current?.focus();
    } else if (focusNext.current === "panel") {
      panel.current?.focus();
    }
    focusNext.current = null;
  });

  if (project === null) {
    return (
      <RepositorySection>
        <p className="text-text-muted">Репозиторий можно привязать после первого сохранения.</p>
      </RepositorySection>
    );
  }

  const { id: projectId, github } = project;
  const disabled = busy || pending !== null;

  function begin(action: "link" | "unlink") {
    inFlight.current = true;
    setPending(action);
    onPendingChange(true);
    setFormatError(false);
    setLinkError(null);
    setUnlinkError(null);
    stopWait();
  }

  function end() {
    inFlight.current = false;
    setPending(null);
    onPendingChange(false);
  }

  /** 401 and the project's 404 leave the form; true when it is being left. */
  function leaves(error: unknown): boolean {
    if (error instanceof ApiError && error.status === 401) {
      router.replace("/login");
      return true;
    }
    if (error instanceof ApiError && error.code === "NOT_FOUND") {
      onNotFound();
      return true;
    }
    return false;
  }

  function submitLink() {
    const fullName = value.trim();
    // The client check spares a request; the API stays the source of truth.
    if (!isRepositoryFullName(fullName)) {
      setLinkError(null);
      setFormatError(true);
      return;
    }
    void link(fullName);
  }

  async function link(fullName: string) {
    if (inFlight.current) {
      return;
    }
    begin("link");
    try {
      const answer = await linkRepository(projectId, fullName);
      onGitHub(answer.github);
      setValue("");
      setReplacing(false);
      focusNext.current = "panel";
    } catch (error) {
      if (leaves(error)) {
        return;
      }
      if (githubErrorCode(error) === "VALIDATION_ERROR") {
        setFormatError(true);
      } else {
        if (linkedProjectId(error) !== null && (await loadProjects()) === "leave") {
          return;
        }
        setLinkError({ error, fullName });
        startWait(error);
      }
    }
    end();
  }

  async function loadProjects(): Promise<"stay" | "leave"> {
    try {
      setProjects((await listProjects()).items);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return "leave";
      }
      // Without the list the message says «к другому вашему проекту».
    }
    return "stay";
  }

  function retryLink() {
    if (linkError === null) {
      return;
    }
    if (githubErrorCode(linkError.error) === "GITHUB_UNAVAILABLE") {
      void link(linkError.fullName);
    } else {
      // The countdown has ended: the message closes and the user links again.
      setLinkError(null);
    }
  }

  async function unlink() {
    if (inFlight.current) {
      return;
    }
    // Unlink does not read GitHub: only the cabinet errors and the project's 404.
    begin("unlink");
    try {
      const answer = await unlinkRepository(projectId);
      onGitHub(answer.github);
      setReplacing(false);
      focusNext.current = "input";
    } catch (error) {
      if (leaves(error)) {
        return;
      }
      setUnlinkError(error);
    }
    end();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    // Enter links instead of submitting the project form around the block.
    if (event.key === "Enter") {
      event.preventDefault();
      if (!disabled && waitLeft === 0) {
        submitLink();
      }
    }
  }

  function cancelReplace() {
    setReplacing(false);
    setValue("");
    setFormatError(false);
    setLinkError(null);
    stopWait();
  }

  const hintId = "project-repository-hint";
  const errorId = "project-repository-error";

  return (
    <RepositorySection>
      {github === null && (
        <p>
          Привяжите репозиторий, и в проекте появятся факты из GitHub. Привязать можно
          репозиторий, в котором вы владелец или входите в список контрибьюторов.
        </p>
      )}

      {github !== null && <LinkedRepository github={github} panel={panel} />}

      {github !== null && !replacing && (
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="secondary"
            disabled={disabled}
            onClick={() => {
              setReplacing(true);
              focusNext.current = "input";
            }}
          >
            Заменить репозиторий
          </Button>
          <Button type="button" variant="danger" disabled={disabled} onClick={() => setConfirming(true)}>
            {pending === "unlink" ? "Отвязываем…" : "Отвязать"}
          </Button>
        </div>
      )}
      {unlinkError !== null && <RequestErrorAlert error={unlinkError} />}

      {(github === null || replacing) && (
        <div className="flex flex-col gap-2">
          <Label htmlFor="project-repository" className="sr-only">
            Репозиторий GitHub
          </Label>
          <div className="flex flex-col gap-3 sm:flex-row">
            <Input
              ref={input}
              id="project-repository"
              type="text"
              value={value}
              placeholder="владелец/репозиторий"
              readOnly={disabled}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={formatError ? true : undefined}
              aria-describedby={formatError ? `${hintId} ${errorId}` : hintId}
              onChange={(event) => {
                setValue(event.target.value);
                setFormatError(false);
              }}
              onKeyDown={handleKeyDown}
            />
            <div className="flex shrink-0 gap-3">
              <Button
                type="button"
                disabled={disabled || waitLeft > 0 || value.trim() === ""}
                onClick={submitLink}
              >
                {pending === "link" ? "Проверяем на GitHub…" : "Привязать"}
              </Button>
              {replacing && (
                <Button type="button" variant="secondary" disabled={disabled} onClick={cancelReplace}>
                  Отмена
                </Button>
              )}
            </div>
          </div>
          <p id={hintId} className="text-sm text-text-muted">
            Только публичные репозитории. Формат: имя владельца, косая черта, имя репозитория. Или{" "}
            <Link href="/me/repositories" className="underline underline-offset-4">
              выберите из своего списка
            </Link>
            .
          </p>
          {formatError && (
            <p id={errorId} className="text-sm text-error">
              {FORMAT_ERROR}
            </p>
          )}
          {linkError !== null && (
            <GitHubErrorAlert
              error={linkError.error}
              request="link"
              projects={projects}
              waitLeft={waitLeft}
              onRetry={retryLink}
            />
          )}
        </div>
      )}

      <p className="text-sm text-text-muted">
        Привязка и отвязка работают сразу и не зависят от кнопки «Сохранить». Они не меняют
        статус, видимость и тексты проекта.
      </p>

      {github !== null && (
        <AlertDialog open={confirming} onOpenChange={setConfirming}>
          <AlertDialogContent>
            <AlertDialogTitle>Отвязать репозиторий?</AlertDialogTitle>
            <AlertDialogDescription>
              Проект и его тексты останутся. Пропадёт только связь с {github.full_name}. Привязать
              можно снова.
            </AlertDialogDescription>
            <div className="flex flex-wrap gap-4">
              <AlertDialogAction asChild>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={(event) => {
                    event.preventDefault();
                    setConfirming(false);
                    void unlink();
                  }}
                >
                  Отвязать
                </Button>
              </AlertDialogAction>
              <AlertDialogCancel asChild>
                <Button type="button" variant="secondary">
                  Отмена
                </Button>
              </AlertDialogCancel>
            </div>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </RepositorySection>
  );
}

function RepositorySection({ children }: { children: ReactNode }) {
  return (
    <section
      aria-labelledby="repository-heading"
      className="flex flex-col gap-4 border-t-4 border-outline pt-6"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="repository-heading" className="font-heading text-xs leading-normal uppercase">
          Репозиторий GitHub
        </h2>
        <SourceBadge />
        <span className="text-sm text-text-muted">Необязательно</span>
      </div>
      {children}
    </section>
  );
}

/** The linked repository as stored: GitHub data only, nothing guessed. */
function LinkedRepository({
  github,
  panel,
}: {
  github: ProjectGitHub;
  panel: RefObject<HTMLDivElement | null>;
}) {
  const pushedAt = pushedAtText(github.pushed_at);
  const relation = RELATION_LABEL[github.relation];
  return (
    <div
      ref={panel}
      tabIndex={-1}
      role="group"
      aria-label="Привязанный репозиторий"
      className="flex flex-col gap-3 border-4 border-outline bg-bg px-4 py-4"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <p className="text-lg">
          <RepositoryName fullName={github.full_name} htmlUrl={github.html_url} />
        </p>
        {pushedAt && <p className="shrink-0 text-sm text-text-muted">{pushedAt}</p>}
      </div>
      <p className={cn("line-clamp-2 break-words", github.description === null && "text-text-muted")}>
        {github.description ?? NO_DESCRIPTION}
      </p>
      {(relation || github.is_fork || github.is_archived) && (
        <div className="flex flex-wrap gap-2">
          {relation && <span className={cn(BADGE, "bg-panel text-text")}>{relation}</span>}
          <RepositoryLabels
            fork={github.is_fork}
            parent={github.parent_full_name}
            archived={github.is_archived}
          />
        </div>
      )}
      {github.synced_at === null && (
        <p className="border-4 border-dashed border-frame px-4 py-3 text-sm text-text-muted">
          {NOT_SYNCED_TEXT}
        </p>
      )}
      {github.unavailable && <Warning>{UNAVAILABLE_WARNING}</Warning>}
      {github.relation === "NONE" && <Warning>{NO_RELATION_WARNING}</Warning>}
    </div>
  );
}

function Warning({ children }: { children: string }) {
  return <p className="border-4 border-label px-4 py-3 text-sm text-label">{children}</p>;
}
