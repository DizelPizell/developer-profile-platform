// Runs once when the Next.js server starts. The check lives in a Node.js-only
// module because it stops the process, which the Edge runtime cannot do.
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./instrumentation-node");
  }
}
