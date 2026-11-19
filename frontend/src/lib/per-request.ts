import { headers } from "next/headers";

// One API call per request, shared by generateMetadata and the page.
// React cache() is not enough: after an error Next renders the error page in a
// second pass with a fresh cache, and generateMetadata would call the API
// again (two requests to a failing API, two timeouts in a row). The headers()
// object lives for the whole request, so it keys the call instead. If Next
// changes that, this degrades to a second call, never to another request's data.
const callsByRequest = new WeakMap<object, Map<string, Promise<unknown>>>();

/** The promise of `load` for this request and `key`; `load` runs once per request. */
export async function perRequest<T>(key: string, load: () => Promise<T>): Promise<T> {
  const request = await headers();
  let calls = callsByRequest.get(request);
  if (!calls) {
    calls = new Map();
    callsByRequest.set(request, calls);
  }
  let call = calls.get(key) as Promise<T> | undefined;
  if (!call) {
    call = load();
    calls.set(key, call);
  }
  return call;
}
