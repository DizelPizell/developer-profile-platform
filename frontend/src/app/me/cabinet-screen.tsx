"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { PixelAvatar } from "@/components/pixel-avatar";
import { RequestErrorAlert } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { ApiError, getProfile, logout, type OwnProfileResponse } from "@/lib/api";

import { ProfileEditor } from "./profile-editor";

type Loaded =
  | { status: "loading" }
  | { status: "ready"; profile: OwnProfileResponse }
  | { status: "error"; error: unknown };

export function CabinetScreen() {
  const router = useRouter();
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    getProfile({ signal: controller.signal }).then(
      (profile) => setLoaded({ status: "ready", profile }),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          // Stays in "loading" while the browser leaves the page.
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
    <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 p-6">
      <CabinetHeader profile={loaded.status === "ready" ? loaded.profile : null} />
      <main className="flex flex-col gap-6">
        {loaded.status === "loading" && (
          <section className="bg-panel px-8 py-10 shadow-panel">
            <p role="status" className="text-xl">
              Загрузка…
            </p>
          </section>
        )}
        {loaded.status === "error" && (
          <section className="flex flex-col items-start gap-6 bg-panel px-8 py-10 shadow-panel">
            <RequestErrorAlert error={loaded.error} />
            <Button onClick={retry}>Повторить</Button>
          </section>
        )}
        {loaded.status === "ready" && <ProfileEditor initialProfile={loaded.profile} />}
      </main>
    </div>
  );
}

function CabinetHeader({ profile }: { profile: OwnProfileResponse | null }) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [logoutError, setLogoutError] = useState<unknown>(null);

  async function handleLogout() {
    if (pending) {
      return;
    }
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
    <header className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <BrandMark />
        <div className="flex items-center gap-4">
          {profile && (
            <>
              {profile.avatar_url ? (
                // A small avatar from GitHub; next/image would need a remote host config.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={profile.avatar_url}
                  alt=""
                  referrerPolicy="no-referrer"
                  className="size-12 rounded-full border-4 border-accent bg-panel shadow-pixel"
                />
              ) : (
                <PixelAvatar className="size-12" />
              )}
              <div className="flex flex-col">
                <span className="text-lg break-all">@{profile.github_login}</span>
                <span className="text-sm text-text-muted">Источник: GitHub</span>
              </div>
            </>
          )}
          <Button variant="secondary" onClick={handleLogout} disabled={pending}>
            Выйти
          </Button>
        </div>
      </div>
      {logoutError !== null && <RequestErrorAlert error={logoutError} />}
    </header>
  );
}
