/** The API answered with an error status. Fields follow the shared error format. */
export class ApiError extends Error {
  override name = "ApiError";
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details: Record<string, unknown>;
    requestId: string | null;
  }) {
    super(init.message);
    this.status = init.status;
    this.code = init.code;
    this.details = init.details;
    this.requestId = init.requestId;
  }
}

/**
 * No readable response: the API is unreachable, or the browser blocked the
 * response. A 403 CSRF_ORIGIN_INVALID has no CORS headers (ADR-013), so it
 * also ends up here and its code cannot be read.
 */
export class NetworkError extends Error {
  override name = "NetworkError";

  constructor(cause: unknown) {
    super("Network request failed", { cause });
  }
}
