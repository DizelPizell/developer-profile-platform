"use client";

import { MessageScreen } from "@/components/message-screen";
import { Button } from "@/components/ui/button";

// Any failure other than 404: API unreachable, timeout, 5xx, unexpected body.
// The error itself is not shown (DESIGN.md).
export default function ProfileError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <MessageScreen title="Не удалось загрузить профиль">
      <Button onClick={() => retry()}>Повторить</Button>
    </MessageScreen>
  );
}
