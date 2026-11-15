import { describe, expect, it } from "vitest";
import { compareWithHistory, latestMonth, monthlyClimatology, sourceTag } from "./harmonized";
import type { HarmonizedCell } from "../types/api";

// SYNTHETIC TEST DATA
function cell(year: number, month: number, value: number | null, state: HarmonizedCell["state"] = "value"): HarmonizedCell {
  return {
    platform: "Harmonized", year, month, state, value, coverage_status: state === "missing" ? "missing" : "complete",
    days_covered: 30, days_in_range: 30, source: "MODIS (Terra+Aqua)", source_value: value, factor: 1,
    relative_uncertainty: 0, converted: false, note: "", modified_z: null, anomaly: null, anomaly_status: null,
  };
}

describe("harmonized helpers", () => {
  it("compares a month with the median of earlier complete years only", () => {
    const cells = [cell(2020, 3, 10), cell(2021, 3, 20), cell(2022, 3, null, "missing"), cell(2023, 3, 30), cell(2024, 3, 60)];
    const c = compareWithHistory(cells, 2024, 3);
    expect(c.historyYears).toEqual([2020, 2021, 2023]);
    expect(c.median).toBe(20);
    expect(c.ratio).toBe(3);
  });
  it("gives no ratio when the target month is not completely covered", () => {
    const cells = [cell(2020, 3, 10), cell(2021, 3, 5, "partial")];
    expect(compareWithHistory(cells, 2021, 3).ratio).toBe(null);
  });
  it("finds the latest month and builds a climatology", () => {
    const cells = [cell(2020, 12, 4), cell(2021, 1, 2), cell(2021, 2, null, "missing")];
    expect(latestMonth(cells)).toEqual({ year: 2021, month: 2 });
    const clim = monthlyClimatology(cells);
    expect(clim[0]).toEqual({ month: 1, median: 2, years: 1 });
    expect(clim[1]).toEqual({ month: 2, median: null, years: 0 });
  });
  it("labels sources briefly", () => {
    expect(sourceTag("MODIS (Terra+Aqua)")).toBe("T+A");
    expect(sourceTag("Suomi-NPP")).toBe("S");
    expect(sourceTag(null)).toBe("");
  });
});
