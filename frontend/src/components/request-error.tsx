import { Alert } from "@/components/ui/alert";
import { ApiError, NetworkError } from "@/lib/api";

// Texts for a failed API call (DESIGN.md). A NetworkError also covers a 403
// CSRF_ORIGIN_INVALID, which the browser cannot read (ADR-013).
export const NETWORK_ERROR_MESSAGE = "Не удалось связаться с сервером.";
export const GENERIC_ERROR_MESSAGE = "Что-то пошло не так. Попробуйте ещё раз.";

export function RequestErrorAlert({ error }: { error: unknown }) {
  const requestId = error instanceof ApiError ? error.requestId : null;
  return (
    <Alert>
      <p>{error instanceof NetworkError ? NETWORK_ERROR_MESSAGE : GENERIC_ERROR_MESSAGE}</p>
      {requestId && <p className="mt-1 text-sm text-text-muted">Код запроса: {requestId}</p>}
    </Alert>
  );
}
