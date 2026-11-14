import { useEffect, useState } from "react";

export type AsyncState<T> =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: T }
  | { kind: "error"; message: string };

/**
 * Run an async loader whenever ``key`` changes (null key = idle). Cancels the previous
 * request on change/unmount so stale responses never overwrite newer ones.
 */
export function useAsync<T>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ kind: "idle" });
  useEffect(() => {
    if (key === null) {
      setState({ kind: "idle" });
      return;
    }
    const controller = new AbortController();
    setState({ kind: "loading" });
    load(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ kind: "ok", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ kind: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => controller.abort();
    // `load` is intentionally not a dependency: callers pass inline closures and the
    // key captures everything that should trigger a reload.
  }, [key]);
  return state;
}
