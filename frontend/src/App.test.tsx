// App shell tests. Every API payload here is SYNTHETIC TEST DATA, not a backend response.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { AreaQuery } from "./lib/area";

const SYNTHETIC_HEALTH = {
  status: "ok",
  app: "FIRETRACE",
  version: "0.1.0-synthetic",
  server_time_utc: "2000-01-01T00:00:00Z",
  firms_map_key_configured: false,
};
const SYNTHETIC_AVAILABILITY = {
  firms: { available: false, error: "FIRMS_MAP_KEY not configured on the server" },
  imported_coverage: [],
  latest_completed_import_utc: null,
  note: "synthetic",
};
const SYNTHETIC_CALENDAR = {
  metric: "detections",
  cells: [
    { platform: "NOAA-20", year: 2026, month: 10, state: "missing", value: null, coverage_status: "missing",
      days_covered: 0, days_in_range: 31, modified_z: null, anomaly: "not assessed", anomaly_status: "incomplete_coverage" },
    { platform: "NOAA-20", year: 2026, month: 11, state: "partial", value: 462, coverage_status: "partial",
      days_covered: 3, days_in_range: 14, modified_z: null, anomaly: "not assessed", anomaly_status: "incomplete_coverage" },
  ],
};

const H = { platform: "Harmonized", coverage_status: "complete", days_covered: 30, days_in_range: 30,
  modified_z: null, anomaly: "not assessed", anomaly_status: "insufficient_history", state: "value" };
const SYNTHETIC_HARMONIZED = {
  status: "EXPERIMENTAL", reference: "modis", reference_source: "MODIS (Terra+Aqua)",
  unit: "MODIS (Terra+Aqua)-equivalent detections", metric: "detections",
  priority: ["MODIS (Terra+Aqua)", "NOAA-20"],
  fits: [
    { source: "MODIS (Terra+Aqua)", reference: "MODIS (Terra+Aqua)", status: "reference", reason: "reference unit",
      factor: 1, n_train: 0, n_validation: 0, train_years: "", validation_years: "", bias: 0, mae: 0, rmse: 0,
      relative_rmse: 0, log_correlation: null },
    { source: "NOAA-20", reference: "MODIS (Terra+Aqua)", status: "estimated", reason: "ratio of sums",
      factor: 0.5, n_train: 24, n_validation: 12, train_years: "2020,2022", validation_years: "2021", bias: 1,
      mae: 2, rmse: 3, relative_rmse: 0.2, log_correlation: 0.9 },
  ],
  cells: [
    { ...H, year: 2024, month: 11, value: 100, source: "MODIS (Terra+Aqua)", source_value: 100, factor: 1,
      relative_uncertainty: 0, converted: false, note: "reference sensor" },
    { ...H, year: 2025, month: 11, value: 100, source: "MODIS (Terra+Aqua)", source_value: 100, factor: 1,
      relative_uncertainty: 0, converted: false, note: "reference sensor" },
    { ...H, year: 2026, month: 11, value: 150, source: "NOAA-20", source_value: 300, factor: 0.5,
      relative_uncertainty: 0.2, converted: true, note: "converted from NOAA-20 × 0.5" },
  ],
};

function respond(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function routeFetch(overrides: Record<string, () => Promise<Response>> = {}) {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    for (const [prefix, handler] of Object.entries(overrides)) if (url.startsWith(prefix)) return handler();
    if (url.startsWith("/api/health")) return respond(SYNTHETIC_HEALTH);
    if (url.startsWith("/api/aoi")) return respond([]);
    if (url.startsWith("/api/data/availability")) return respond(SYNTHETIC_AVAILABILITY);
    if (url.startsWith("/api/ingest/history")) return respond({ total: 0, page: 1, page_size: 50, items: [] });
    if (url.startsWith("/api/calendar/harmonized")) return respond(SYNTHETIC_HARMONIZED);
    if (url.startsWith("/api/calendar")) return respond(SYNTHETIC_CALENDAR);
    return respond({ detail: "not mocked" }, 404);
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows backend status from the health endpoint", async () => {
    vi.stubGlobal("fetch", routeFetch());
    render(<App />);
    expect(screen.getByText("FIRETRACE")).toBeTruthy();
    expect(await screen.findByText("0.1.0-synthetic")).toBeTruthy();
    expect(screen.getByText("not configured")).toBeTruthy();
  });

  it("reports an unreachable backend instead of failing silently", async () => {
    vi.stubGlobal("fetch", routeFetch({ "/api/health": () => Promise.resolve(new Response("", { status: 503 })) }));
    render(<App />);
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => (a.textContent ?? "").includes("HTTP 503"))).toBe(true);
  });

  it("asks for an area instead of assuming a default region", async () => {
    vi.stubGlobal("fetch", routeFetch());
    render(<App />);
    expect(await screen.findByText(/FIRETRACE has no default region/)).toBeTruthy();
    expect(screen.getByText("No data imported yet — no coverage is claimed.", { exact: false })).toBeTruthy();
  });

  it("navigates to the calendar and distinguishes missing from partial months", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const query: AreaQuery = {
      area: { kind: "bbox", bbox: { west: 76.7, south: 12.6, east: 84.8, north: 19.9 } },
      start: "2026-10-01",
      end: "2026-11-14",
      platforms: ["NOAA-20"],
    };
    render(<App initialQuery={query} />);
    fireEvent.click(screen.getByRole("button", { name: "Calendar" }));
    fireEvent.click(await screen.findByRole("radio", { name: "Per satellite" }));
    const partial = await screen.findByRole("button", { name: /Nov 2026: Partly covered/ });
    expect(partial.getAttribute("data-state")).toBe("partial");
    const missing = screen.getByRole("button", { name: /Oct 2026: No data — unknown, not zero/ });
    expect(missing.textContent).toContain("—");
  });

  it("shows one harmonized calendar with converted months and the latest month vs history", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const query: AreaQuery = {
      area: { kind: "bbox", bbox: { west: 76.7, south: 12.6, east: 84.8, north: 19.9 } },
      start: "2024-11-01",
      end: "2026-11-30",
      platforms: [],
    };
    render(<App initialQuery={query} />);
    fireEvent.click(screen.getByRole("button", { name: "Calendar" }));
    const converted = await screen.findByRole("button", { name: /Nov 2026: Covered, detections; 150/ });
    expect(converted.getAttribute("aria-label")).toContain("from NOAA-20");
    expect(converted.textContent).toContain("≈");
    expect(converted.textContent).toContain("N20");
    expect(screen.getByText(/1\.50 × the median/)).toBeTruthy();
    expect(screen.getByRole("radio", { name: "Harmonized (one calendar)" }).getAttribute("aria-checked")).toBe("true");
  });
});
