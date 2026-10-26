import { afterEach, describe, expect, test, vi } from "vitest";

import { ApiConfigError, apiUrl, assertApiEnv } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("in the browser", () => {
  test("uses NEXT_PUBLIC_API_URL, not API_INTERNAL_URL", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://localhost:8000/");
    vi.stubEnv("API_INTERNAL_URL", "http://backend:8000");

    expect(apiUrl("/auth/me")).toBe("http://localhost:8000/api/v1/auth/me");
  });

  test("a missing address names the variable", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(() => apiUrl("/auth/me")).toThrow(/NEXT_PUBLIC_API_URL is not set/);
  });
});

describe("assertApiEnv", () => {
  const valid = {
    NEXT_PUBLIC_API_URL: "http://localhost:8000",
    API_INTERNAL_URL: "http://backend:8000",
  };

  test("accepts two http(s) addresses", () => {
    expect(() => assertApiEnv(valid)).not.toThrow();
  });

  test("lists every missing variable", () => {
    expect(() => assertApiEnv({})).toThrow(
      /NEXT_PUBLIC_API_URL is not set; API_INTERNAL_URL is not set/,
    );
  });

  test.each(["not a url", "ftp://backend"])("rejects %s", (value) => {
    expect(() => assertApiEnv({ ...valid, API_INTERNAL_URL: value })).toThrow(ApiConfigError);
  });
});
