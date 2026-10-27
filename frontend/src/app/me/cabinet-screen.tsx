"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ApiError, getProfile, type OwnProfileResponse } from "@/lib/api";

import { CabinetPage, LoadErrorPanel, LoadingPanel } from "./cabinet-page";
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
    <CabinetPage account={loaded.status === "ready" ? loaded.profile : null} tab="profile">
      {loaded.status === "loading" && <LoadingPanel />}
      {loaded.status === "error" && <LoadErrorPanel error={loaded.error} onRetry={retry} />}
      {loaded.status === "ready" && <ProfileEditor initialProfile={loaded.profile} />}
    </CabinetPage>
  );
}
