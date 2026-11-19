"use client";

import { MessageScreen } from "@/components/message-screen";
import { Button } from "@/components/ui/button";

// Any failure other than 404: API unreachable, timeout, 5xx, unexpected body.
// The error itself is not shown (DESIGN.md).
export default function ProjectError({ retry }: { error: unknown; retry: () => void }) {
  return (
    <MessageScreen title="Не удалось загрузить проект">
      <Button onClick={() => retry()}>Повторить</Button>
    </MessageScreen>
  );
}
