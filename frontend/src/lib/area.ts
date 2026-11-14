// Area selection: bbox parsing/validation, polygons from clicked vertices, query strings.
// Pure functions (no React) so they are unit-tested without a browser.

export interface BBox {
  west: number;
  south: number;
  east: number;
  north: number;
}

export type AreaSelection =
  | { kind: "bbox"; bbox: BBox; label?: string }
  | { kind: "aoi"; id: number; name: string; bbox: BBox };

export interface AreaQuery {
  area: AreaSelection;
  start: string; // YYYY-MM-DD (UTC)
  end: string;
  platforms: string[]; // empty = all
}

export type Result<T> = { ok: true; value: T } | { ok: false; error: string };

export function parseBBox(text: string): Result<BBox> {
  const parts = text.split(",").map((p) => p.trim());
  if (parts.length !== 4 || parts.some((p) => p === "")) {
    return { ok: false, error: "Enter four numbers: west,south,east,north" };
  }
  const [west, south, east, north] = parts.map(Number);
  return validateBBox({ west, south, east, north });
}

export function validateBBox(b: BBox): Result<BBox> {
  const values = [b.west, b.south, b.east, b.north];
  if (values.some((v) => !Number.isFinite(v))) {
    return { ok: false, error: "Coordinates must be numbers" };
  }
  if (Math.abs(b.west) > 180 || Math.abs(b.east) > 180) {
    return { ok: false, error: "Longitude must be between -180 and 180" };
  }
  if (Math.abs(b.south) > 90 || Math.abs(b.north) > 90) {
    return { ok: false, error: "Latitude must be between -90 and 90" };
  }
  if (b.south >= b.north) {
    return { ok: false, error: "South must be less than north" };
  }
  if (b.west === b.east) {
    return { ok: false, error: "West and east must differ" };
  }
  return { ok: true, value: b };
}

export function bboxText(b: BBox): string {
  const f = (v: number) => String(Math.round(v * 1e5) / 1e5);
  return [b.west, b.south, b.east, b.north].map(f).join(",");
}

/** True when west > east, i.e. the box crosses the 180° meridian. */
export function crossesAntimeridian(b: BBox): boolean {
  return b.west > b.east;
}

/** Bounding box from two clicked map corners (any order). */
export function bboxFromCorners(a: [number, number], b: [number, number]): BBox {
  const [lat1, lon1] = a;
  const [lat2, lon2] = b;
  return {
    west: Math.min(lon1, lon2),
    east: Math.max(lon1, lon2),
    south: Math.min(lat1, lat2),
    north: Math.max(lat1, lat2),
  };
}

/** Closed GeoJSON polygon from clicked [lat, lon] vertices (≥ 3). */
export function polygonFromVertices(vertices: [number, number][]): Result<{
  type: "Polygon";
  coordinates: number[][][];
}> {
  if (vertices.length < 3) {
    return { ok: false, error: "A polygon needs at least 3 points" };
  }
  const ring = vertices.map(([lat, lon]) => [lon, lat]);
  ring.push([...ring[0]]);
  return { ok: true, value: { type: "Polygon", coordinates: [ring] } };
}

export function validateDates(start: string, end: string, today: string): Result<null> {
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  if (!iso.test(start) || !iso.test(end)) {
    return { ok: false, error: "Dates must be YYYY-MM-DD" };
  }
  if (end < start) return { ok: false, error: "End date is before start date" };
  if (end > today) return { ok: false, error: "End date is in the future" };
  return { ok: true, value: null };
}

/** URLSearchParams for the API's common area parameters (+ extras). */
export function areaParams(
  q: AreaQuery,
  extra: Record<string, string | number | boolean | string[] | undefined> = {},
): URLSearchParams {
  const params = new URLSearchParams();
  if (q.area.kind === "bbox") params.set("bbox", bboxText(q.area.bbox));
  else params.set("aoi_id", String(q.area.id));
  params.set("start", q.start);
  params.set("end", q.end);
  for (const p of q.platforms) params.append("platform", p);
  for (const [key, value] of Object.entries(extra)) {
    if (value === undefined) continue;
    if (Array.isArray(value)) value.forEach((v) => params.append(key, v));
    else params.set(key, String(value));
  }
  return params;
}

export function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function daysBefore(today: Date, days: number): string {
  const d = new Date(today.getTime());
  d.setUTCDate(d.getUTCDate() - days);
  return isoDay(d);
}

/** Optional example presets. FIRETRACE has no default region. */
export const EXAMPLE_AREAS: { label: string; bbox: BBox }[] = [
  { label: "Example: Andhra Pradesh, India (approx. bbox)", bbox: { west: 76.7, south: 12.6, east: 84.8, north: 19.9 } },
  { label: "Example: Amazon arc of deforestation, Brazil", bbox: { west: -65, south: -15, east: -45, north: -3 } },
  { label: "Example: Northern Australia", bbox: { west: 120, south: -20, east: 145, north: -11 } },
  { label: "Example: Fiji (crosses 180°)", bbox: { west: 176, south: -21, east: -178, north: -15 } },
];
