"use client";

import { cn } from "cn";

import type { GitHubSyncStatus, ProjectGitHub } from "@/lib/api";

import { dateTimeText } from "../github-texts";

// The sync state of a linked repository in the project form (DESIGN.md, "Sync
// status, languages and «Обновить данные»"; ADR-018). The job's error is never
// shown: the API does not return it.

/** A job is waiting or running: «Обновить данные» is not offered, the form polls. */
export function isSyncActive(status: GitHubSyncStatus): boolean {
  return status === "QUEUED" || status === "SYNCING";
}

type Message = { tone: "progress" | "plain" | "error"; text: string };

function syncMessage(github: ProjectGitHub): Message | null {
  const { status } = github.sync;
  if (isSyncActive(status)) {
    // One message for both: a failed attempt goes back to QUEUED.
    return { tone: "progress", text: "Получаем данные с GitHub…" };
  }
  if (status === "NOT_SYNCED") {
    return { tone: "plain", text: "Ещё не синхронизирован с GitHub." };
  }
  if (status === "FAILED") {
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

/** The message by sync status, in a live region so a change is announced. */
export function SyncMessage({ github }: { github: ProjectGitHub }) {
  const message = syncMessage(github);
  return (
    <div role="status">
      {message && (
        <div
          className={cn(
            "flex items-center gap-3 border-4 px-4 py-3",
            message.tone === "error" ? "border-error bg-bg" : "border-text-muted bg-panel",
          )}
        >
          {message.tone === "progress" && <ProgressSquares />}
          <p>{message.text}</p>
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
