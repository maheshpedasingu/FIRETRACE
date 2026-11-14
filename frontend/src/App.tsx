import { useEffect, useState } from "react";
import { fetchHealth } from "./services/api";
import type { HealthResponse } from "./types/api";

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error"; message: string };

export default function App() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => setBackend({ kind: "ok", health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setBackend({
          kind: "error",
          message: error instanceof Error ? error.message : "Unknown error",
        });
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 px-6 py-4">
        <h1 className="text-2xl font-semibold tracking-wide text-orange-400">FIRETRACE</h1>
        <p className="text-sm text-slate-400">
          Global satellite fire intelligence — NASA FIRMS MODIS and VIIRS active-fire detections
        </p>
      </header>

      <main className="space-y-4 px-6 py-6">
        <section aria-label="Backend status" className="rounded-lg border border-slate-800 p-4">
          <h2 className="mb-2 text-lg font-medium">Backend status</h2>
          {backend.kind === "loading" && <p>Checking backend…</p>}
          {backend.kind === "error" && (
            <p role="alert" className="text-red-400">
              Backend unreachable: {backend.message}
            </p>
          )}
          {backend.kind === "ok" && (
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
              <dt className="text-slate-400">Status</dt>
              <dd>{backend.health.status}</dd>
              <dt className="text-slate-400">Version</dt>
              <dd>{backend.health.version}</dd>
              <dt className="text-slate-400">FIRMS MAP_KEY</dt>
              <dd>{backend.health.firms_map_key_configured ? "configured" : "not configured"}</dd>
            </dl>
          )}
        </section>

        <section aria-label="Data coverage" className="rounded-lg border border-slate-800 p-4">
          <h2 className="mb-2 text-lg font-medium">Data coverage</h2>
          <p className="text-sm text-slate-400">
            No NASA FIRMS data has been imported yet. Coverage is reported only for sensors,
            areas and dates that have actually been imported.
          </p>
        </section>
      </main>
    </div>
  );
}
