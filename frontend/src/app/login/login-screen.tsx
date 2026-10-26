"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { BrandMark } from "@/components/brand-mark";
import { PixelAvatar } from "@/components/pixel-avatar";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { getMe, githubLoginUrl, NetworkError } from "@/lib/api";

import { loginErrorMessage } from "./error-messages";

// checking: GET /auth/me is in flight, the button stays disabled (DESIGN.md).
type Session = "checking" | "signed-out" | "unreachable";

export function LoginScreen() {
  const router = useRouter();
  const errorMessage = loginErrorMessage(useSearchParams().get("error"));
  const [session, setSession] = useState<Session>("checking");

  useEffect(() => {
    const controller = new AbortController();
    getMe({ signal: controller.signal }).then(
      () => router.replace("/me"),
      (error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setSession(error instanceof NetworkError ? "unreachable" : "signed-out");
      },
    );
    return () => controller.abort();
  }, [router]);

  return (
    <LoginLayout
      errorMessage={errorMessage}
      loginUrl={session === "checking" ? undefined : githubLoginUrl()}
      unreachable={session === "unreachable"}
    />
  );
}

export function LoginLayout({
  errorMessage,
  loginUrl,
  unreachable = false,
}: {
  errorMessage: string | null;
  /** Computed in the browser only, so prerendering needs no API address. */
  loginUrl?: string;
  unreachable?: boolean;
}) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 p-6">
      <BrandMark />
      <section className="flex w-full max-w-2xl flex-col items-center gap-6 bg-panel px-8 py-10 text-center shadow-panel">
        <PixelAvatar />
        <h1 className="font-heading text-2xl leading-relaxed uppercase">Новая игра</h1>
        <p className="text-xl leading-relaxed">
          Профиль разработчика с проектами и данными из GitHub. Войдите, чтобы создать свой.
        </p>
        {errorMessage && <Alert>{errorMessage}</Alert>}
        {unreachable && <Alert>Не удалось связаться с сервером.</Alert>}
        {loginUrl ? (
          <Button asChild size="lg">
            <a href={loginUrl}>Войти через GitHub</a>
          </Button>
        ) : (
          <Button size="lg" disabled>
            Войти через GitHub
          </Button>
        )}
        <p className="text-base leading-relaxed text-text-muted">
          Мы получаем только публичные данные GitHub: логин, аватар и email, если он открыт.
          Доступа к вашим репозиториям нет.
        </p>
      </section>
    </main>
  );
}
