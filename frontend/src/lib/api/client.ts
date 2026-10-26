import { apiUrl } from "./config";
import { ApiError, NetworkError } from "./errors";

export type ApiRequestInit = Omit<RequestInit, "body" | "credentials"> & {
  /** Sent as a JSON body with Content-Type: application/json. */
  json?: unknown;
};

type ErrorBody = {
  error: { code: string; message: string; details?: Record<string, unknown>; request_id?: string };
};

function isErrorBody(body: unknown): body is ErrorBody {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return false;
  }
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

async function readJson(response: Response): Promise<unknown> {
  const text = await response.text();
  return text ? JSON.parse(text) : undefined;
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await readJson(response);
  } catch {
    body = undefined;
  }
  const error = isErrorBody(body) ? body.error : undefined;
  return new ApiError({
    status: response.status,
    code: error?.code ?? "UNKNOWN_ERROR",
    message: error?.message ?? `HTTP ${response.status}`,
    details: error?.details ?? {},
    requestId: error?.request_id ?? response.headers.get("X-Request-ID"),
  });
}

/**
 * Calls an API path such as "/auth/me" with the session cookie.
 *
 * Throws ApiError for an error response and NetworkError when there is no
 * readable response. Returns undefined for an empty body (204).
 */
export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const requestHeaders = new Headers(headers);
  requestHeaders.set("Accept", "application/json");
  if (json !== undefined) {
    // The only request header the API's CORS policy allows (ADR-013).
    requestHeaders.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...rest,
      headers: requestHeaders,
      body: json === undefined ? undefined : JSON.stringify(json),
      credentials: "include",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new NetworkError(error);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  try {
    return (await readJson(response)) as T;
  } catch {
    throw new ApiError({
      status: response.status,
      code: "INVALID_RESPONSE",
      message: "Response body is not valid JSON",
      details: {},
      requestId: response.headers.get("X-Request-ID"),
    });
  }
}
