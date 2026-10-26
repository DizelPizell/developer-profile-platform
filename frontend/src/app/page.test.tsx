import { expect, test, vi } from "vitest";

import Home from "./page";

const redirect = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ redirect }));

test("the start page redirects to /me", () => {
  Home();
  expect(redirect).toHaveBeenCalledWith("/me");
});
