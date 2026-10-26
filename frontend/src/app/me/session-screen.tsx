"use client";

// Temporary F2 page: shows that the session works and allows signing out.
// The F3 cabinet (profile form, status, publication) replaces it.

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { ApiError, getMe, logout, type MeResponse } from "@/lib/api";

type Session =
  | { status: "loading" }
  | { status: "ready"; me: MeResponse }
  | { status: "error"; error: unknown };

export function SessionScreen() {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [session, setSession] = useState<Session>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getMe({ signal: controller.signal }).then(
      (me) => setSession({ status: "ready", me }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          // Stays in "loading" while the browser leaves the page.
          router.replace("/login");
          return;
        }
        setSession({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [attempt, router]);

  function retry() {
    setSession({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <section className="flex w-full max-w-xl flex-col items-center gap-6 bg-panel px-8 py-10 text-center shadow-panel">
        {session.status === "loading" && (
          <p role="status" className="text-xl">
            Загрузка…
          </p>
        )}
        {session.status === "error" && (
          <>
            <RequestErrorAlert error={session.error} />
            <Button onClick={retry}>Повторить</Button>
          </>
        )}
        {session.status === "ready" && <SignedIn me={session.me} />}
      </section>
    </main>
  );
}

function SignedIn({ me }: { me: MeResponse }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);

  async function handleLogout() {
    setPending(true);
    setLogoutError(null);
    try {
      await logout();
      router.replace("/login");
    } catch (error) {
      setLogoutError(error);
      setPending(false);
    }
  }

  return (
    <>
      <div className="flex flex-col items-center gap-3">
        <p className="font-heading text-xs leading-normal text-label">Вы вошли как</p>
        <h1 className="text-3xl break-all">@{me.github_login}</h1>
        <p className="text-sm text-text-muted">Источник: GitHub</p>
      </div>
      {logoutError !== null && <RequestErrorAlert error={logoutError} />}
      <Button variant="secondary" onClick={handleLogout} disabled={pending}>
        Выйти
      </Button>
    </>
  );
}
