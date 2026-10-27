"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { BrandMark } from "@/components/brand-mark";
import { PixelAvatar } from "@/components/pixel-avatar";
import { RequestErrorAlert } from "@/components/request-error";
import { Button } from "@/components/ui/button";
import { ApiError, getProfile, logout, type OwnProfileResponse } from "@/lib/api";

/** What the header shows: GitHub data from the own profile. */
export type Account = Pick<OwnProfileResponse, "avatar_url" | "github_login">;

/**
 * Loads the header's account for screens that do not load the profile
 * themselves. A 401 leaves for /login; any other failure leaves the header
 * with only «Выйти» (DESIGN.md).
 */
export function useAccount(): Account | null {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getProfile({ signal: controller.signal }).then(
      (profile) => setAccount(profile),
      (error: unknown) => {
        if (!controller.signal.aborted && error instanceof ApiError && error.status === 401) {
          router.replace("/login");
        }
      },
    );
    return () => controller.abort();
  }, [router]);

  return account;
}

/** The cabinet frame: header, optional tabs, then the screen. */
export function CabinetPage({
  account,
  tab,
  children,
}: {
  account: Account | null;
  /** The active tab; the project form has no tabs (mockup project-form.png). */
  tab?: "profile" | "projects";
  children: ReactNode;
}) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col gap-6 p-6">
      <CabinetHeader account={account} />
      {tab && <CabinetTabs active={tab} />}
      <main className="flex flex-col gap-6">{children}</main>
    </div>
  );
}

const TABS = [
  { key: "profile", href: "/me", label: "Профиль" },
  { key: "projects", href: "/me/projects", label: "Проекты" },
] as const;

function CabinetTabs({ active }: { active: "profile" | "projects" }) {
  return (
    <nav aria-label="Кабинет">
      <ul className="flex flex-wrap gap-4">
        {TABS.map((tab) => {
          const current = tab.key === active;
          return (
            <li key={tab.key}>
              <Button asChild variant={current ? "default" : "secondary"}>
                <Link href={tab.href} aria-current={current ? "page" : undefined}>
                  {tab.label}
                </Link>
              </Button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function CabinetHeader({ account }: { account: Account | null }) {
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
          {account && (
            <>
              {account.avatar_url ? (
                // A small avatar from GitHub; next/image would need a remote host config.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={account.avatar_url}
                  alt=""
                  referrerPolicy="no-referrer"
                  className="size-12 rounded-full border-4 border-accent bg-panel shadow-pixel"
                />
              ) : (
                <PixelAvatar className="size-12" />
              )}
              <div className="flex flex-col">
                <span className="text-lg break-all">@{account.github_login}</span>
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

/** A panel with «Загрузка…», shared by the cabinet screens. */
export function LoadingPanel() {
  return (
    <section className="bg-panel px-8 py-10 shadow-panel">
      <p role="status" className="text-xl">
        Загрузка…
      </p>
    </section>
  );
}

/** A load failure with «Повторить». */
export function LoadErrorPanel({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  return (
    <section className="flex flex-col items-start gap-6 bg-panel px-8 py-10 shadow-panel">
      <RequestErrorAlert error={error} />
      <Button onClick={onRetry}>Повторить</Button>
    </section>
  );
}
