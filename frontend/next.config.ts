import type { NextConfig } from "next";
import { PHASE_PRODUCTION_BUILD } from "next/constants";

import { assertApiEnv } from "./src/lib/api/config";

export default function nextConfig(phase: string): NextConfig {
  // NEXT_PUBLIC_API_URL is inlined into the browser bundle at build time, so a
  // build without it would ship a broken client even if the server has it later.
  if (phase === PHASE_PRODUCTION_BUILD) {
    assertApiEnv(process.env);
  }

  return {
    // Otherwise `next dev` writes an AGENTS.md into the project on every start.
    agentRules: false,
    turbopack: {
      rules: {
        "*.css": {
          loaders: ["@tailwindcss/turbopack"],
          as: "*.css",
        },
      },
    },
  };
}
