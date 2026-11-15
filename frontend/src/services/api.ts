// Typed client for the FIRETRACE REST API. All requests go to /api (proxied by Vite to
// the backend); no credentials are ever handled in the browser.
import { areaParams, type AreaQuery } from "../lib/area";
import type {
  Anomalies,
  Availability,
  CalendarCell,
  HarmonizedCalendar,
  HarmonizedReference,
  HealthResponse,
  Hotspot,
  IngestRun,
  Metric,
  MonthRow,
  Page,
  SavedAOI,
  SensorInfo,
  Summary,
  YearRow,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = `${detail}: ${body.detail}`;
      else if (body.detail) detail = `${detail}: ${JSON.stringify(body.detail)}`;
    } catch {
      // body was not JSON; keep the status text
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

const get = <T>(path: string, params?: URLSearchParams, signal?: AbortSignal) =>
  request<T>(params ? `${path}?${params.toString()}` : path, { signal });

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch("/api/health", { signal });
  if (!response.ok) {
    throw new Error(`Backend health check failed: HTTP ${response.status}`);
  }
  return (await response.json()) as HealthResponse;
}

export const fetchSensors = (signal?: AbortSignal) => get<SensorInfo[]>("/api/sensors", undefined, signal);
export const fetchAvailability = (signal?: AbortSignal) =>
  get<Availability>("/api/data/availability", undefined, signal);
export const fetchSummary = (q: AreaQuery, signal?: AbortSignal) =>
  get<Summary>("/api/hotspots/summary", areaParams(q), signal);

export const fetchHotspots = (
  q: AreaQuery,
  opts: { page: number; pageSize: number; confidence?: string[]; daynight?: string[]; includeSource?: boolean },
  signal?: AbortSignal,
) =>
  get<Page<Hotspot>>(
    "/api/hotspots",
    areaParams(q, {
      page: opts.page,
      page_size: opts.pageSize,
      confidence: opts.confidence,
      daynight: opts.daynight,
      include_source: opts.includeSource ? true : undefined,
    }),
    signal,
  );

export const fetchCalendar = (q: AreaQuery, metric: Metric, signal?: AbortSignal) =>
  get<{ metric: Metric; cells: CalendarCell[] }>("/api/calendar", areaParams(q, { metric }), signal);
export const fetchHarmonizedCalendar = (
  q: AreaQuery,
  metric: Metric,
  reference: HarmonizedReference,
  signal?: AbortSignal,
) => get<HarmonizedCalendar>("/api/calendar/harmonized", areaParams(q, { metric, reference }), signal);
export const fetchMonthly = (q: AreaQuery, signal?: AbortSignal) =>
  get<{ months: MonthRow[] }>("/api/analytics/monthly", areaParams(q), signal);
export const fetchYearly = (q: AreaQuery, metric: Metric, signal?: AbortSignal) =>
  get<{ metric: Metric; years: YearRow[] }>("/api/analytics/yearly", areaParams(q, { metric }), signal);
export const fetchAnomalies = (q: AreaQuery, metric: Metric, target?: string, signal?: AbortSignal) =>
  get<Anomalies>("/api/analytics/anomalies", areaParams(q, { metric, target }), signal);
export const fetchSensorComparison = (q: AreaQuery, signal?: AbortSignal) =>
  get<{ status: string; calibration: Record<string, unknown>[]; matching: Record<string, unknown>[] }>(
    "/api/analytics/sensor-comparison",
    areaParams(q),
    signal,
  );

export const fetchAOIs = (signal?: AbortSignal) => get<SavedAOI[]>("/api/aoi", undefined, signal);
export const createAOI = (body: { name: string; bbox?: string; geojson?: unknown; country?: string }) =>
  request<SavedAOI>("/api/aoi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const fetchHistory = (page: number, signal?: AbortSignal) =>
  get<Page<IngestRun>>("/api/ingest/history", new URLSearchParams({ page: String(page) }), signal);

export const uploadFile = (form: FormData) =>
  request<Record<string, unknown>>("/api/ingest/upload", { method: "POST", body: form });

export const fetchFirms = (body: {
  sources: string[];
  bbox?: string;
  world?: boolean;
  start: string;
  end: string;
}) =>
  request<{ warnings: string[]; windows: Record<string, unknown>[] }>("/api/ingest/firms", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export function exportCsvUrl(
  q: AreaQuery,
  kind: "hotspots" | "calendar" | "harmonized_calendar",
  opts: {
    bundle?: boolean;
    metric?: Metric;
    reference?: HarmonizedReference;
    confidence?: string[];
    daynight?: string[];
  } = {},
): string {
  const params = areaParams(q, {
    kind,
    bundle: opts.bundle ? true : undefined,
    metric: opts.metric,
    reference: opts.reference,
    confidence: opts.confidence,
    daynight: opts.daynight,
  });
  return `/api/export/csv?${params.toString()}`;
}

export function reportUrl(q: AreaQuery, format: "json" | "md", target?: string): string {
  return `/api/export/report?${areaParams(q, { format, target }).toString()}`;
}
