import { apiFetch } from "./client";
import { browserApiUrl } from "./config";

/** GET /auth/me (API_CONTRACT.md). */
export type MeResponse = {
  id: string;
  github_login: string;
  email: string | null;
  profile_slug: string | null;
};

export function getMe(init: { signal?: AbortSignal } = {}): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/me", { signal: init.signal });
}

/** POST /auth/logout: 204 on success, also without a session. */
export function logout(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

/** Sign-in starts with a full-page navigation to this address, not a fetch (ADR-014). */
export function githubLoginUrl(): string {
  return browserApiUrl("/auth/github/login");
}
