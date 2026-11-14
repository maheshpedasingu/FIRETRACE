import { Suspense, lazy, useEffect, useState } from "react";
import { AreaBar } from "./components/AreaBar";
import { Loading } from "./components/Status";
import { useAsync } from "./hooks/useAsync";
import type { AreaQuery } from "./lib/area";
import { CalendarPage } from "./pages/CalendarPage";
import { ExplorerPage } from "./pages/ExplorerPage";
import { ExportPage } from "./pages/ExportPage";
import { IngestionPage } from "./pages/IngestionPage";
import { OverviewPage } from "./pages/OverviewPage";
import { fetchAOIs, fetchHealth } from "./services/api";
import { AreaProvider, useArea } from "./state/AreaContext";
import type { HealthResponse } from "./types/api";

// Map (Leaflet) and Analytics (Recharts) load on first use, keeping the initial bundle small.
const MapPage = lazy(() => import("./maps/MapPage"));
const AnalyticsPage = lazy(() =>
  import("./pages/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage })),
);

const PAGES = [
  { id: "overview", label: "Overview" },
  { id: "map", label: "Map" },
  { id: "calendar", label: "Calendar" },
  { id: "analytics", label: "Analytics" },
  { id: "explorer", label: "Data explorer" },
  { id: "ingestion", label: "Ingestion" },
  { id: "export", label: "Export" },
] as const;
type PageId = (typeof PAGES)[number]["id"];

type BackendState =
  | { kind: "loading" }
  | { kind: "ok"; health: HealthResponse }
  | { kind: "error"; message: string };

function BackendStatus() {
  const [backend, setBackend] = useState<BackendState>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then((health) => setBackend({ kind: "ok", health }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setBackend({ kind: "error", message: error instanceof Error ? error.message : "Unknown error" });
      });
    return () => controller.abort();
  }, []);

  return (
    <section aria-label="Backend status" className="text-xs">
      {backend.kind === "loading" && <span>Checking backend…</span>}
      {backend.kind === "error" && (
        <span role="alert" className="text-red-300">
          Backend unreachable: {backend.message}
        </span>
      )}
      {backend.kind === "ok" && (
        <dl className="flex gap-x-3">
          <dt className="text-[var(--text-secondary)]">Status</dt>
          <dd>{backend.health.status}</dd>
          <dt className="text-[var(--text-secondary)]">Version</dt>
          <dd>{backend.health.version}</dd>
          <dt className="text-[var(--text-secondary)]">FIRMS MAP_KEY</dt>
          <dd>{backend.health.firms_map_key_configured ? "configured" : "not configured"}</dd>
        </dl>
      )}
    </section>
  );
}

function Shell() {
  const [page, setPage] = useState<PageId>("overview");
  const { query, setQuery } = useArea();
  const [aoiVersion, setAoiVersion] = useState(0);
  const aois = useAsync(`aois-${aoiVersion}-${query?.area.kind === "aoi" ? query.area.id : ""}`, (s) => fetchAOIs(s));
  const savedAois = aois.kind === "ok" ? aois.data : [];

  const apply = (q: AreaQuery) => {
    setQuery(q);
    setAoiVersion((v) => v + 1);
  };

  return (
    <div className="min-h-screen bg-[var(--surface)] text-[var(--text-primary)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border)] px-6 py-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-wide text-[#eb8a5a]">FIRETRACE</h1>
          <p className="text-xs text-[var(--text-secondary)]">
            Global satellite fire intelligence — NASA FIRMS MODIS and VIIRS active-fire detections
          </p>
        </div>
        <BackendStatus />
      </header>
      <nav aria-label="Pages" className="flex gap-1 border-b border-[var(--border)] px-6">
        {PAGES.map((p) => (
          <button
            key={p.id}
            type="button"
            aria-current={page === p.id ? "page" : undefined}
            onClick={() => setPage(p.id)}
            className={`border-b-2 px-3 py-2 text-sm ${
              page === p.id ? "border-[#eb8a5a] text-[var(--text-primary)]" : "border-transparent text-[var(--text-secondary)]"
            }`}
          >
            {p.label}
          </button>
        ))}
      </nav>
      {page !== "ingestion" && <AreaBar query={query} onApply={apply} savedAois={savedAois} />}
      <main className="px-6 py-6">
        {page === "overview" && <OverviewPage />}
        {page === "map" && (
          <Suspense fallback={<Loading what="the map" />}>
            <MapPage />
          </Suspense>
        )}
        {page === "calendar" && <CalendarPage />}
        {page === "analytics" && (
          <Suspense fallback={<Loading what="analytics" />}>
            <AnalyticsPage />
          </Suspense>
        )}
        {page === "explorer" && <ExplorerPage />}
        {page === "ingestion" && <IngestionPage />}
        {page === "export" && <ExportPage />}
      </main>
      <footer className="border-t border-[var(--border)] px-6 py-3 text-xs text-[var(--text-secondary)]">
        Data: NASA FIRMS (LANCE / MODAPS). Detections are not fire incidents; FRP is not burned area; missing data is
        not zero. Coverage is shown only for imported areas and dates.
      </footer>
    </div>
  );
}

export default function App({ initialQuery = null }: { initialQuery?: AreaQuery | null }) {
  return (
    <AreaProvider initial={initialQuery}>
      <Shell />
    </AreaProvider>
  );
}
