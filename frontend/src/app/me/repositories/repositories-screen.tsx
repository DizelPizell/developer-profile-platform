"use client";

import { cn } from "cn";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ApiError,
  githubErrorCode,
  importRepository,
  linkedProjectId,
  listProjects,
  listRepositories,
  PROJECTS_MAX,
  REPOSITORY_PAGE_MAX,
  type GitHubRepository,
  type GitHubRepositoryPage,
  type ProjectResponse,
  type ProjectSummary,
} from "@/lib/api";

import { CabinetPage, LoadErrorPanel, LoadingPanel, useAccount } from "../cabinet-page";
import { GitHubErrorAlert, useRetryCountdown } from "../github-error";
import {
  NO_DESCRIPTION,
  pushedAtText,
  RepositoryLabels,
  RepositoryName,
  SourceBadge,
} from "../github-texts";
import { importedProjectHref } from "../projects/imported-marker";
import { BADGE, PROJECT_LIMIT_TEXT, UNTITLED } from "../projects/project-texts";
import { LinkDialog } from "./link-dialog";

type Result<T> = { status: "ready"; data: T } | { status: "error"; error: unknown };

/** A loaded list page, kept with the page and attempt it answers. */
type ListResult = { page: number; attempt: number; result: Result<GitHubRepositoryPage> };

/** The repository a failed import was for, kept for «Повторить». */
type ActionError = { error: unknown; repository: GitHubRepository };

type LinkedNotice = { title: string; fullName: string };

export function RepositoriesScreen({ page }: { page: number }) {
  const router = useRouter();
  const account = useAccount();
  const [projects, setProjects] = useState<Result<ProjectSummary[]> | null>(null);
  const [projectsAttempt, setProjectsAttempt] = useState(0);
  const [list, setList] = useState<ListResult | null>(null);
  const [listAttempt, setListAttempt] = useState(0);
  const { left: listWaitLeft, start: startListWait, stop: stopListWait } = useRetryCountdown();

  useEffect(() => {
    const controller = new AbortController();
    listProjects({ signal: controller.signal }).then(
      ({ items }) => setProjects({ status: "ready", data: items }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setProjects({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [projectsAttempt, router]);

  // A page change loads only the repository list (DESIGN.md).
  useEffect(() => {
    const controller = new AbortController();
    listRepositories(page, { signal: controller.signal }).then(
      (data) => setList({ page, attempt: listAttempt, result: { status: "ready", data } }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        startListWait(error);
        setList({ page, attempt: listAttempt, result: { status: "error", error } });
      },
    );
    return () => controller.abort();
  }, [page, listAttempt, router, startListWait]);

  // null while the current page is loading.
  const current = list && list.page === page && list.attempt === listAttempt ? list.result : null;

  function retryProjects() {
    setProjects(null);
    setProjectsAttempt((n) => n + 1);
  }

  function retryList() {
    stopListWait();
    setListAttempt((n) => n + 1);
  }

  /** Local changes of the loaded page: link and ALREADY_LINKED, nothing is reloaded. */
  function updateRepositories(change: (items: GitHubRepository[]) => GitHubRepository[]) {
    setList((state) =>
      state && state.result.status === "ready"
        ? {
            ...state,
            result: {
              status: "ready",
              data: { ...state.result.data, items: change(state.result.data.items) },
            },
          }
        : state,
    );
  }

  /** After a link, GET /projects is read again for titles and «Уже привязан к …». */
  function reloadProjects() {
    listProjects().then(
      ({ items }) => setProjects({ status: "ready", data: items }),
      (error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
        }
        // Otherwise the list updated locally from the link answer stays.
      },
    );
  }

  return (
    <CabinetPage account={account}>
      <Link href="/me/projects" className="self-start text-text-muted underline underline-offset-4">
        <span aria-hidden="true">‹ </span>Назад к проектам
      </Link>

      <section className="flex flex-col gap-4 bg-panel px-6 py-6 shadow-panel sm:px-8">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="font-heading text-lg leading-relaxed uppercase">Репозитории GitHub</h1>
          <SourceBadge />
        </div>
        <p className="text-lg">
          Ваши публичные репозитории. Мы только читаем данные, ничего не меняем на GitHub.
        </p>
        <p className="text-text-muted">
          Привязать можно репозиторий, в котором вы владелец или входите в список
          контрибьюторов. Список обновляется раз в 5 минут: новый репозиторий появится не
          сразу.
        </p>
      </section>

      {projects?.status === "error" ? (
        <LoadErrorPanel error={projects.error} onRetry={retryProjects} />
      ) : current?.status === "error" ? (
        <section className="bg-panel px-6 py-6 shadow-panel sm:px-8">
          <GitHubErrorAlert
            error={current.error}
            request="list"
            projects={projects?.status === "ready" ? projects.data : []}
            waitLeft={listWaitLeft}
            onRetry={retryList}
          />
        </section>
      ) : projects === null || current === null ? (
        <LoadingPanel />
      ) : (
        <RepositoryList
          page={page}
          repositories={current.data}
          projects={projects.data}
          onRepositories={updateRepositories}
          onProjects={(change) =>
            setProjects((state) =>
              state?.status === "ready" ? { status: "ready", data: change(state.data) } : state,
            )
          }
          onReloadProjects={reloadProjects}
        />
      )}
    </CabinetPage>
  );
}

function RepositoryList({
  page,
  repositories,
  projects,
  onRepositories,
  onProjects,
  onReloadProjects,
}: {
  page: number;
  repositories: GitHubRepositoryPage;
  projects: ProjectSummary[];
  onRepositories: (change: (items: GitHubRepository[]) => GitHubRepository[]) => void;
  onProjects: (change: (items: ProjectSummary[]) => ProjectSummary[]) => void;
  onReloadProjects: () => void;
}) {
  const router = useRouter();
  // The repository being imported; every action is disabled meanwhile.
  const [importing, setImporting] = useState<number | null>(null);
  // Blocks a second request before the disabled state reaches the DOM.
  const inFlight = useRef(false);
  const [actionError, setActionError] = useState<ActionError | null>(null);
  const { left: waitLeft, start: startWait, stop: stopWait } = useRetryCountdown();
  const [linking, setLinking] = useState<GitHubRepository | null>(null);
  const [linkedNotice, setLinkedNotice] = useState<LinkedNotice | null>(null);
  const alerts = useRef<HTMLDivElement>(null);
  const notice = useRef<HTMLDivElement>(null);
  const focusNotice = useRef(false);

  const busy = importing !== null;
  // A 429 or 503 is about GitHub as a whole, so both actions wait it out.
  const waiting = waitLeft > 0;
  const atLimit = projects.length >= PROJECTS_MAX;
  const nextPage = repositories.next_page;
  const hasAlert = actionError !== null || linkedNotice !== null;

  useEffect(() => {
    if (hasAlert) {
      alerts.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [hasAlert, actionError, linkedNotice]);

  function markLinked(githubRepoId: number, projectId: string) {
    onRepositories((items) =>
      items.map((item) => {
        if (item.github_repo_id === githubRepoId) {
          return { ...item, linked_project_id: projectId };
        }
        // A link replaces the project's previous repository.
        return item.linked_project_id === projectId ? { ...item, linked_project_id: null } : item;
      }),
    );
  }

  async function importAsProject(repository: GitHubRepository) {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setImporting(repository.github_repo_id);
    setActionError(null);
    setLinkedNotice(null);
    stopWait();
    try {
      const project = await importRepository(repository.github_repo_id);
      // The form takes over and shows «Проект создан» once; the button stays disabled.
      router.push(importedProjectHref(project.id));
      return;
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setActionError({ error, repository });
      startWait(error);
      const projectId = linkedProjectId(error);
      if (projectId !== null) {
        markLinked(repository.github_repo_id, projectId);
      }
    }
    inFlight.current = false;
    setImporting(null);
  }

  function retryAction() {
    if (actionError === null) {
      return;
    }
    if (githubErrorCode(actionError.error) === "GITHUB_UNAVAILABLE") {
      void importAsProject(actionError.repository);
    } else {
      // The countdown has ended: the message closes and the user repeats the action.
      setActionError(null);
    }
  }

  function openLink(repository: GitHubRepository) {
    setActionError(null);
    setLinkedNotice(null);
    setLinking(repository);
  }

  function handleLinked(project: ProjectResponse, repository: GitHubRepository) {
    const github = project.github ?? {
      github_repo_id: repository.github_repo_id,
      full_name: repository.full_name,
      html_url: repository.html_url,
    };
    markLinked(github.github_repo_id, project.id);
    onProjects((items) =>
      items.map((item) =>
        item.id === project.id
          ? { ...item, github: { full_name: github.full_name, html_url: github.html_url } }
          : item,
      ),
    );
    setLinkedNotice({ title: project.title ?? UNTITLED, fullName: github.full_name });
    focusNotice.current = true;
    setLinking(null);
    onReloadProjects();
  }

  function goTo(target: number) {
    setActionError(null);
    setLinkedNotice(null);
    router.push(`/me/repositories?page=${target}`);
  }

  const { items } = repositories;
  const canGoForward = nextPage !== null && nextPage <= REPOSITORY_PAGE_MAX;

  return (
    <>
      {hasAlert && (
        <div ref={alerts} className="flex flex-col gap-4">
          {actionError !== null && (
            <GitHubErrorAlert
              error={actionError.error}
              request="import"
              projects={projects}
              waitLeft={waitLeft}
              onRetry={retryAction}
            />
          )}
          {linkedNotice !== null && (
            <div
              ref={notice}
              role="status"
              tabIndex={-1}
              className="flex flex-col gap-3 border-4 border-success bg-bg px-4 py-4"
            >
              <p className="font-heading text-xs leading-normal text-success uppercase">
                Репозиторий привязан
              </p>
              <p className="break-words">
                Проект «{linkedNotice.title}» привязан к {linkedNotice.fullName}. Статус,
                видимость и тексты проекта не менялись.
              </p>
            </div>
          )}
        </div>
      )}

      {items.length === 0 ? (
        page === 1 ? (
          <section className="flex flex-col items-start gap-4 border-4 border-dashed border-frame px-6 py-6">
            <p className="text-lg">
              На вашем аккаунте GitHub нет публичных репозиториев. Приватные мы не показываем.
              Проект можно создать и без репозитория.
            </p>
            <Link href="/me/projects/new" className="underline underline-offset-4">
              Создать проект вручную
            </Link>
          </section>
        ) : (
          <p className="text-lg text-text-muted">На этой странице репозиториев нет.</p>
        )
      ) : (
        <ul aria-label="Репозитории" className="flex flex-col gap-6">
          {items.map((repository) => (
            <RepositoryCard
              key={repository.github_repo_id}
              repository={repository}
              projects={projects}
              importing={importing === repository.github_repo_id}
              importDisabled={busy || waiting || atLimit}
              atLimit={atLimit}
              linkDisabled={busy || waiting}
              onImport={() => void importAsProject(repository)}
              onLink={() => openLink(repository)}
            />
          ))}
        </ul>
      )}

      {(items.length > 0 || page > 1) && (
        <nav aria-label="Страницы списка" className="flex items-center justify-between gap-4">
          <Button variant="secondary" disabled={busy || page <= 1} onClick={() => goTo(page - 1)}>
            <span aria-hidden="true">‹ </span>Назад
          </Button>
          <p className="text-text-muted">Страница {page}</p>
          <Button
            variant="secondary"
            disabled={busy || !canGoForward}
            onClick={() => canGoForward && goTo(nextPage)}
          >
            Вперёд<span aria-hidden="true"> ›</span>
          </Button>
        </nav>
      )}

      {linking !== null && (
        <LinkDialog
          repository={linking}
          projects={projects}
          onClose={() => setLinking(null)}
          onLinked={(project) => handleLinked(project, linking)}
          onAlreadyLinked={(projectId) => markLinked(linking.github_repo_id, projectId)}
          onCloseAutoFocus={(event) => {
            // The card's trigger is gone after a link; the confirmation takes the focus.
            if (focusNotice.current) {
              focusNotice.current = false;
              event.preventDefault();
              notice.current?.focus();
            }
          }}
        />
      )}
    </>
  );
}

function RepositoryCard({
  repository,
  projects,
  importing,
  importDisabled,
  atLimit,
  linkDisabled,
  onImport,
  onLink,
}: {
  repository: GitHubRepository;
  projects: ProjectSummary[];
  importing: boolean;
  importDisabled: boolean;
  atLimit: boolean;
  linkDisabled: boolean;
  onImport: () => void;
  onLink: () => void;
}) {
  const { github_repo_id: id, linked_project_id: linkedId } = repository;
  const pushedAt = pushedAtText(repository.pushed_at);
  const hintId = `import-hint-${id}`;
  const limitId = `import-limit-${id}`;

  return (
    <li className="flex flex-col gap-4 bg-panel px-6 py-6 shadow-panel">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <h2 className="text-lg">
            <RepositoryName fullName={repository.full_name} htmlUrl={repository.html_url} />
          </h2>
          <RepositoryLabels fork={repository.is_fork} archived={repository.is_archived} />
        </div>
        {pushedAt && <p className="shrink-0 text-sm text-text-muted">{pushedAt}</p>}
      </div>
      <p className={cn("line-clamp-2 break-words", repository.description === null && "text-text-muted")}>
        {repository.description ?? NO_DESCRIPTION}
      </p>

      {linkedId !== null ? (
        <LinkedProject projectId={linkedId} projects={projects} />
      ) : (
        <>
          <div className="flex flex-wrap gap-3">
            <Button
              variant="label"
              disabled={importDisabled}
              aria-describedby={atLimit ? `${limitId} ${hintId}` : hintId}
              onClick={onImport}
            >
              {importing ? "Импортируем…" : "Импортировать как проект"}
            </Button>
            <Button variant="secondary" disabled={linkDisabled} onClick={onLink}>
              Привязать к проекту…
            </Button>
          </div>
          {atLimit && (
            <p id={limitId} className="text-sm text-text-muted">
              {PROJECT_LIMIT_TEXT}
            </p>
          )}
          <p id={hintId} className="text-sm text-text-muted">
            Импорт создаёт черновик с названием репозитория. Остальное вы заполняете сами.
          </p>
        </>
      )}
    </li>
  );
}

/** «Привязан · Проект: {title}»; the title comes from GET /projects. */
function LinkedProject({ projectId, projects }: { projectId: string; projects: ProjectSummary[] }) {
  const project = projects.find((p) => p.id === projectId);
  const href = `/me/projects/${encodeURIComponent(projectId)}`;
  return (
    <div className="flex flex-wrap items-center gap-3 border-t-4 border-outline pt-4">
      <span className={cn(BADGE, "bg-bg text-success")}>Привязан</span>
      {project ? (
        <p className="break-words">
          Проект:{" "}
          <Link href={href} className="underline underline-offset-4">
            {project.title ?? UNTITLED}
          </Link>
        </p>
      ) : (
        // Not in the loaded list (for example, created in another tab): no title is guessed.
        <Link href={href} className="underline underline-offset-4">
          Открыть проект
        </Link>
      )}
    </div>
  );
}
