// API addresses (ADR-014). Both hold the base address without the /api/v1 prefix:
// NEXT_PUBLIC_API_URL for code in the browser, API_INTERNAL_URL for server code
// (inside Docker it names the backend service instead of localhost).

const API_PREFIX = "/api/v1";

export const API_ENV_NAMES = ["NEXT_PUBLIC_API_URL", "API_INTERNAL_URL"] as const;

export class ApiConfigError extends Error {
  override name = "ApiConfigError";
}

function parseBaseUrl(name: string, value: string | undefined): string {
  if (!value) {
    throw new ApiConfigError(`${name} is not set`);
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ApiConfigError(`${name} is not a valid URL`);
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ApiConfigError(`${name} must be an http or https URL`);
  }
  return value.replace(/\/+$/, "");
}

export function apiBaseUrl(): string {
  // Written out literally: Next.js inlines only literal process.env.NEXT_PUBLIC_*
  // references into the browser bundle.
  return typeof window === "undefined"
    ? parseBaseUrl("API_INTERNAL_URL", process.env.API_INTERNAL_URL)
    : parseBaseUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL);
}

/** Full URL of an API path such as "/auth/me". */
export function apiUrl(path: string): string {
  if (!path.startsWith("/")) {
    throw new ApiConfigError(`API path must start with "/": ${path}`);
  }
  return `${apiBaseUrl()}${API_PREFIX}${path}`;
}

/** Fails at server start when an address is missing or invalid (src/instrumentation.ts). */
export function assertApiEnv(env: Record<string, string | undefined>): void {
  const problems: string[] = [];
  for (const name of API_ENV_NAMES) {
    try {
      parseBaseUrl(name, env[name]);
    } catch (error) {
      problems.push((error as Error).message);
    }
  }
  if (problems.length > 0) {
    throw new ApiConfigError(`Invalid API configuration: ${problems.join("; ")}`);
  }
}
