// @vitest-environment node
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "vitest";

// next/font calls cannot run outside the Next.js compiler, so the configuration
// is checked as source. `next build` separately fails if a font lacks a subset.
const source = readFileSync(join(import.meta.dirname, "fonts.ts"), "utf8");

test.each(["Press_Start_2P", "Pixelify_Sans"])("%s loads the cyrillic subset", (font) => {
  const call = source.match(new RegExp(`${font}\\(\\{[^}]*\\}\\)`));
  expect(call, `${font}(...) call not found`).not.toBeNull();
  const subsets = call![0].match(/subsets:\s*\[([^\]]*)\]/);
  expect(subsets?.[1]).toContain('"cyrillic"');
});
