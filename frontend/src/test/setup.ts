import { cleanup, configure, getConfig } from "@testing-library/react";
import { afterEach } from "vitest";

// Vitest globals are off, so React Testing Library cannot register this itself.
afterEach(cleanup);

// An update that lands outside act() (a fetch answer) commits in a Scheduler task,
// and its passive effects (a countdown's setInterval) may run in the next one: under
// load Scheduler yields to setImmediate, and RTL's setTimeout(0) drain can resolve
// findBy* first, so a test ticks fake timers before the timer exists. One
// setImmediate queued after Scheduler's lets that task run before findBy* resolves.
const asyncWrapper = getConfig().asyncWrapper;
configure({
  asyncWrapper: (callback) =>
    asyncWrapper(async () => {
      const result = await callback();
      await new Promise((resolve) => setImmediate(resolve));
      return result;
    }),
});
