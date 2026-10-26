import Link from "next/link";

import { MessageScreen } from "@/components/message-screen";
import { Button } from "@/components/ui/button";

// The same screen for a missing, unpublished or malformed slug: the API does
// not tell them apart either (ADR-013).
export default function ProfileNotFound() {
  return (
    <MessageScreen
      code="404"
      title="Профиль не найден"
      text="Такого профиля нет или он не опубликован. Проверьте ссылку."
    >
      <Button asChild>
        <Link href="/">На главную</Link>
      </Button>
      <Button asChild variant="secondary">
        <Link href="/login">Создать свой</Link>
      </Button>
    </MessageScreen>
  );
}
