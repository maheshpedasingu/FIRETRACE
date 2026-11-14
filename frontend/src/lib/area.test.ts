// Area helper tests. All coordinates are SYNTHETIC TEST DATA.
import { describe, expect, it } from "vitest";
import {
  areaParams,
  bboxFromCorners,
  bboxText,
  crossesAntimeridian,
  daysBefore,
  parseBBox,
  polygonFromVertices,
  validateDates,
} from "./area";

describe("parseBBox", () => {
  it("accepts a valid bbox, including negative (west/south) values", () => {
    const r = parseBBox("-150, -30, -140, -20");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value).toEqual({ west: -150, south: -30, east: -140, north: -20 });
  });

  it("rejects malformed and out-of-range input with a reason", () => {
    expect(parseBBox("1,2,3")).toEqual({ ok: false, error: "Enter four numbers: west,south,east,north" });
    expect(parseBBox("a,1,2,3").ok).toBe(false);
    expect(parseBBox("0,10,5,5")).toEqual({ ok: false, error: "South must be less than north" });
    expect(parseBBox("-190,0,5,5").ok).toBe(false);
    expect(parseBBox("0,-95,5,5").ok).toBe(false);
  });

  it("allows antimeridian-crossing boxes (west > east)", () => {
    const r = parseBBox("176,-21,-178,-15");
    expect(r.ok).toBe(true);
    if (r.ok) expect(crossesAntimeridian(r.value)).toBe(true);
  });
});

describe("map drawing helpers", () => {
  it("builds a bbox from two corners in any order", () => {
    expect(bboxFromCorners([20, 85], [12, 76])).toEqual({ west: 76, south: 12, east: 85, north: 20 });
  });

  it("closes a polygon ring and swaps to [lon, lat]", () => {
    const r = polygonFromVertices([[0, 0], [0, 10], [10, 0]]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.coordinates[0]).toEqual([[0, 0], [10, 0], [0, 10], [0, 0]]);
    expect(polygonFromVertices([[0, 0], [1, 1]]).ok).toBe(false);
  });
});

describe("dates and query parameters", () => {
  it("validates date order and future dates", () => {
    expect(validateDates("2026-11-01", "2026-11-14", "2026-11-14").ok).toBe(true);
    expect(validateDates("2026-11-10", "2026-11-01", "2026-11-14").ok).toBe(false);
    expect(validateDates("2026-11-10", "2026-11-20", "2026-11-14").ok).toBe(false);
    expect(validateDates("2026/11/10", "2026-11-12", "2026-11-14").ok).toBe(false);
  });

  it("computes UTC days before a date", () => {
    expect(daysBefore(new Date("2026-03-01T05:00:00Z"), 1)).toBe("2026-02-28");
  });

  it("encodes bbox or saved AOI, dates, repeatable platforms and extras", () => {
    const bbox = { west: 76.7, south: 12.6, east: 84.8, north: 19.9 };
    const p = areaParams(
      { area: { kind: "bbox", bbox }, start: "2026-11-01", end: "2026-11-14", platforms: ["NOAA-20", "Aqua"] },
      { page: 2, confidence: ["high", "nominal"], skip: undefined },
    );
    expect(p.get("bbox")).toBe(bboxText(bbox));
    expect(p.getAll("platform")).toEqual(["NOAA-20", "Aqua"]);
    expect(p.getAll("confidence")).toEqual(["high", "nominal"]);
    expect(p.get("page")).toBe("2");
    expect(p.has("skip")).toBe(false);
    const saved = areaParams({ area: { kind: "aoi", id: 3, name: "x", bbox }, start: "a", end: "b", platforms: [] });
    expect(saved.get("aoi_id")).toBe("3");
    expect(saved.has("bbox")).toBe(false);
  });
});
