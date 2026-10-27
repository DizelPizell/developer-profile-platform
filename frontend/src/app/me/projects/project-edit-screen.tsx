"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, getProject, type ProjectResponse } from "@/lib/api";

import { CabinetPage, LoadErrorPanel, LoadingPanel, useAccount } from "../cabinet-page";
import { ProjectEditor } from "./project-editor";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; project: ProjectResponse | null }
  | { status: "not-found" }
  | { status: "error"; error: unknown };

/** /me/projects/new without projectId, /me/projects/[id] with it. */
export function ProjectEditScreen({ projectId }: { projectId?: string }) {
  const router = useRouter();
  const account = useAccount();
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>(
    projectId === undefined ? { status: "ready", project: null } : { status: "loading" },
  );

  useEffect(() => {
    if (projectId === undefined) {
      return;
    }
    const controller = new AbortController();
    getProject(projectId, { signal: controller.signal }).then(
      (project) => setLoaded({ status: "ready", project }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          router.replace("/login");
          return;
        }
        if (error instanceof ApiError && error.code === "NOT_FOUND") {
          setLoaded({ status: "not-found" });
          return;
        }
        setLoaded({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [projectId, attempt, router]);

  function retry() {
    setLoaded({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  return (
    <CabinetPage account={account}>
      <Link
        href="/me/projects"
        className="self-start text-text-muted underline underline-offset-4"
      >
        <span aria-hidden="true">‹ </span>Назад к проектам
      </Link>
      {loaded.status === "loading" && <LoadingPanel />}
      {loaded.status === "error" && <LoadErrorPanel error={loaded.error} onRetry={retry} />}
      {loaded.status === "not-found" && (
        <section className="flex flex-col items-start gap-6 bg-panel px-8 py-10 shadow-panel">
          <h1 className="font-heading text-lg leading-relaxed uppercase">Проект не найден</h1>
          <p className="text-lg">Такого проекта нет среди ваших.</p>
          <Button asChild>
            <Link href="/me/projects">Мои проекты</Link>
          </Button>
        </section>
      )}
      {loaded.status === "ready" && (
        <ProjectEditor
          initialProject={loaded.project}
          onNotFound={() => setLoaded({ status: "not-found" })}
        />
      )}
    </CabinetPage>
  );
}
