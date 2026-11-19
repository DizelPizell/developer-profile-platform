import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { Button } from "@/components/ui/button";

/** The top bar of the public pages: the profile and its projects. */
export function PublicHeader() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-4">
      <BrandMark />
      <Button asChild>
        <Link href="/login">Войти через GitHub</Link>
      </Button>
    </header>
  );
}

/** The developer is the source of these blocks (DESIGN.md, content rules). */
export function AuthorMark() {
  return (
    <span className="shrink-0 border-2 border-text-muted px-2 py-1 caps-label text-text-muted">
      От автора
    </span>
  );
}
