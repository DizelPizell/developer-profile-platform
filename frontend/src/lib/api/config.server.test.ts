// @vitest-environment node
import { afterEach, expect, test, vi } from "vitest";

import { apiUrl, browserApiUrl } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

test("on the server uses API_INTERNAL_URL, not NEXT_PUBLIC_API_URL", () => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
  vi.stubEnv("API_INTERNAL_URL", "http://backend:8000");

  expect(apiUrl("/public/profiles/ann")).toBe("http://backend:8000/api/v1/public/profiles/ann");
});

test("browserApiUrl uses NEXT_PUBLIC_API_URL even on the server", () => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000");
  vi.stubEnv("API_INTERNAL_URL", "http://backend:8000");

  expect(browserApiUrl("/auth/github/login")).toBe(
    "http://localhost:8000/api/v1/auth/github/login",
  );
});

test("a missing server address names the variable", () => {
  vi.stubEnv("API_INTERNAL_URL", "");
  expect(() => apiUrl("/public/profiles/ann")).toThrow(/API_INTERNAL_URL is not set/);
});
