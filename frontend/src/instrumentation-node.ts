import { assertApiEnv } from "@/lib/api/config";

// An error thrown from register() only makes Next.js answer every request with
// 500 while the server keeps running; a missing API address must stop it.
try {
  assertApiEnv(process.env);
} catch (error) {
  console.error((error as Error).message);
  process.exit(1);
}
