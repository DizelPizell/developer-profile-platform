"use client";

import { cn } from "cn";
import { useEffect, useEffectEvent, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  ApiError,
  getProject,
  type GitHubSyncStatus,
  type ProjectGitHub,
  type ProjectResponse,
} from "@/lib/api";

import { dateTimeText } from "../github-texts";

// The sync state of a linked repository in the project form (DESIGN.md, "Sync
// status, languages and «Обновить данные»"; ADR-018). The job's error is never
// shown: the API does not return it.

/** A job is waiting or running: «Обновить данные» is not offered, the form polls. */
export function isSyncActive(status: GitHubSyncStatus): boolean {
  return status === "QUEUED" || status === "SYNCING";
}

export const POLL_INTERVAL_MS = 5_000;
/** 2 minutes of a visible tab; a job left QUEUED with no worker running stops here. */
export const POLL_MAX_READS = 24;
export const POLL_MAX_FAILURES = 3;

/** Why polling stopped while the job is still active. */
export type PollStop = "time" | "failures";

/**
 * Reads GET /projects/{id} every 5 seconds while the job is QUEUED or SYNCING,
 * only while the tab is visible, and gives the form only `github` back.
 *
 * A request of the form or the block (busy) cancels the read in flight and pauses
 * polling; an answer is taken only while the form still shows the repository the
 * read was sent for, so a late answer cannot bring back an unlinked repository.
 */
export function useSyncPolling({
  projectId,
  github,
  busy,
  onGitHub,
  onUnauthorized,
  onNotFound,
}: {
  projectId: string | null;
  github: ProjectGitHub | null;
  busy: boolean;
  onGitHub: (update: (current: ProjectGitHub | null) => ProjectGitHub | null) => void;
  onUnauthorized: () => void;
  onNotFound: () => void;
}): { stop: PollStop | null; checkAgain: () => void } {
  const repoId = github?.github_repo_id ?? null;
  const active = github !== null && isSyncActive(github.sync.status);
  // «Проверить снова» starts a new series with an immediate read.
  const [series, setSeries] = useState(0);
  const immediate = useRef(false);
  const [stopped, setStopped] = useState<{ series: number; repoId: number; why: PollStop } | null>(
    null,
  );
  const stop =
    active && stopped !== null && stopped.series === series && stopped.repoId === repoId
      ? stopped.why
      : null;

  const take = useEffectEvent((answer: ProjectResponse, sentFor: number) => {
    onGitHub((current) => (current?.github_repo_id === sentFor ? answer.github : current));
  });
  const leave = useEffectEvent((error: unknown): boolean => {
    if (error instanceof ApiError && error.status === 401) {
      onUnauthorized();
      return true;
    }
    if (error instanceof ApiError && error.code === "NOT_FOUND") {
      onNotFound();
      return true;
    }
    return false;
  });

  useEffect(() => {
    if (projectId === null || repoId === null || !active || busy || stop !== null) {
      return;
    }
    const sentFor = repoId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | null = null;
    let waitingForTab = false;
    let reads = 0;
    let failures = 0;

    const halt = (why: PollStop) => setStopped({ series, repoId: sentFor, why });

    async function read() {
      if (document.hidden) {
        // A hidden tab sends nothing; it reads once when it is shown again.
        waitingForTab = true;
        return;
      }
      reads += 1;
      controller = new AbortController();
      try {
        const answer = await getProject(projectId!, { signal: controller.signal });
        if (cancelled) {
          return;
        }
        failures = 0;
        take(answer, sentFor);
        const next = answer.github;
        if (next?.github_repo_id !== sentFor || !isSyncActive(next.sync.status)) {
          // Done, unlinked or replaced: the form's new github ends this series.
          return;
        }
      } catch (error) {
        if (cancelled || leave(error)) {
          return;
        }
        failures += 1;
        if (failures >= POLL_MAX_FAILURES) {
          halt("failures");
          return;
        }
      }
      if (reads >= POLL_MAX_READS) {
        halt("time");
        return;
      }
      timer = setTimeout(read, POLL_INTERVAL_MS);
    }

    function onVisibility() {
      if (!document.hidden && waitingForTab) {
        waitingForTab = false;
        void read();
      }
    }

    document.addEventListener("visibilitychange", onVisibility);
    timer = setTimeout(read, immediate.current ? 0 : POLL_INTERVAL_MS);
    immediate.current = false;
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [projectId, repoId, active, busy, stop, series]);

  function checkAgain() {
    immediate.current = true;
    setSeries((current) => current + 1);
  }

  return { stop, checkAgain };
}

type Message = { tone: "progress" | "plain" | "label" | "error"; text: string };

function syncMessage(github: ProjectGitHub, stop: PollStop | null): Message | null {
  const { status } = github.sync;
  if (stop === "time") {
    // The job may still finish: a label, not an error.
    return { tone: "label", text: "Синхронизация идёт дольше обычного. Проверьте позже." };
  }
  if (stop === "failures") {
    return { tone: "error", text: "Не удалось узнать статус синхронизации." };
  }
  if (isSyncActive(status)) {
    // One message for both: a failed attempt goes back to QUEUED.
    return { tone: "progress", text: "Получаем данные с GitHub…" };
  }
  if (status === "NOT_SYNCED") {
    return { tone: "plain", text: "Ещё не синхронизирован с GitHub." };
  }
  if (status === "FAILED") {
    // The unavailable warning says it, and such a repository's job fails every day.
    if (github.unavailable) {
      return null;
    }
    const shown = github.synced_at === null ? null : dateTimeText(github.synced_at);
    return {
      tone: "error",
      text:
        shown === null
          ? "Не удалось получить данные с GitHub. Попробуйте обновить позже."
          : `Не удалось обновить данные с GitHub. Показаны данные от ${shown}.`,
    };
  }
  // SYNCED: the data date says it.
  return null;
}

/**
 * The message by sync status, in a live region so a change is announced. A
 * stopped poll replaces it with «Проверить снова».
 */
export function SyncMessage({
  github,
  stop = null,
  busy = false,
  onCheckAgain,
}: {
  github: ProjectGitHub;
  stop?: PollStop | null;
  busy?: boolean;
  onCheckAgain?: () => void;
}) {
  const message = syncMessage(github, stop);
  return (
    <div role="status">
      {message && (
        <div
          className={cn(
            "flex flex-col items-start gap-3 border-4 px-4 py-3",
            message.tone === "error" && "border-error bg-bg",
            message.tone === "label" && "border-label bg-bg",
            (message.tone === "progress" || message.tone === "plain") && "border-text-muted bg-panel",
          )}
        >
          <div className="flex items-center gap-3">
            {message.tone === "progress" && <ProgressSquares />}
            <p>{message.text}</p>
          </div>
          {stop !== null && (
            <Button type="button" variant="secondary" disabled={busy} onClick={onCheckAgain}>
              Проверить снова
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/** Three squares stepping through brightness; static with prefers-reduced-motion. */
function ProgressSquares() {
  return (
    <span aria-hidden="true" className="flex shrink-0 gap-1">
      <span className="size-3 bg-text-muted motion-safe:animate-sync-step" />
      <span className="size-3 bg-text-muted opacity-60 motion-safe:animate-sync-step motion-safe:[animation-delay:300ms]" />
      <span className="size-3 bg-text-muted opacity-30 motion-safe:animate-sync-step motion-safe:[animation-delay:600ms]" />
    </span>
  );
}
