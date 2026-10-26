import type { Metadata } from "next";
import Link from "next/link";

import { MessageScreen } from "@/components/message-screen";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Страница не найдена — Developer Profile Platform",
};

// Any unknown route. Public profiles have their own text (u/[slug]/not-found.tsx).
export default function NotFound() {
  return (
    <MessageScreen code="404" title="Страница не найдена" text="Проверьте ссылку.">
      <Button asChild>
        <Link href="/">На главную</Link>
      </Button>
    </MessageScreen>
  );
}
