"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { RequestErrorAlert } from "@/components/request-error";
import { SectionHeading } from "@/components/section-heading";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, deleteAccount } from "@/lib/api";

const GITHUB_APPLICATIONS = "https://github.com/settings/applications";

/**
 * «Удаление аккаунта» under the profile form (DESIGN.md, ADR-0028). The dialog
 * asks for the GitHub login: the API deletes at once and for good.
 */
export function AccountDeletion({ githubLogin }: { githubLogin: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // GitHub logins ignore case.
  const confirmed = typed.trim().toLowerCase() === githubLogin.toLowerCase();

  function openChange(next: boolean) {
    if (pending) {
      return;
    }
    setOpen(next);
    setTyped("");
    setError(null);
  }

  async function handleDelete() {
    if (!confirmed || pending) {
      return;
    }
    setPending(true);
    setError(null);
    try {
      await deleteAccount();
      router.replace("/login");
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) {
        // No session: nothing left to delete here.
        router.replace("/login");
        return;
      }
      setError(failure);
      setPending(false);
    }
  }

  return (
    <section aria-labelledby="account-deletion" className="flex flex-col gap-4">
      <SectionHeading id="account-deletion" marker="muted">
        Удаление аккаунта
      </SectionHeading>
      <div className="flex flex-col items-start gap-4 bg-panel px-8 py-8 shadow-panel">
        <p className="text-lg leading-relaxed">
          Удалятся профиль, контакты, проекты со скриншотами и привязки репозиториев. Публичная
          страница перестанет открываться. Отменить нельзя.
        </p>
        <p className="text-base leading-relaxed text-text-muted">
          Что мы храним и как долго — в <Link href="/privacy" className="underline underline-offset-4">политике данных</Link>.
        </p>
        <Button variant="destructive" onClick={() => openChange(true)}>
          Удалить аккаунт
        </Button>
      </div>
      <AlertDialog open={open} onOpenChange={openChange}>
        <AlertDialogContent>
          <AlertDialogTitle>Удалить аккаунт?</AlertDialogTitle>
          <AlertDialogDescription>
            Профиль, контакты, проекты и скриншоты удалятся сразу и навсегда. Отменить нельзя.
          </AlertDialogDescription>
          <p className="text-base leading-relaxed text-text-muted">
            Доступ приложения к GitHub отзывается отдельно — в{" "}
            <a href={GITHUB_APPLICATIONS} target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-4"
            >
              настройках GitHub
            </a>
            .
          </p>
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void handleDelete();
            }}
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="account-deletion-login">
                Введите логин «{githubLogin}», чтобы подтвердить
              </Label>
              <Input
                id="account-deletion-login"
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={typed}
                disabled={pending}
                onChange={(event) => setTyped(event.target.value)}
              />
            </div>
            {error !== null && <RequestErrorAlert error={error} />}
            <div className="flex flex-wrap gap-4">
              <Button type="submit" variant="destructive" disabled={!confirmed || pending}>
                {pending ? "Удаляем…" : "Удалить навсегда"}
              </Button>
              <AlertDialogCancel asChild>
                <Button variant="secondary" disabled={pending}>
                  Отмена
                </Button>
              </AlertDialogCancel>
            </div>
          </form>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
