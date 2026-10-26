import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import Home from "./page";

test("start page shows the project name", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
    "Developer Profile Platform",
  );
});
