// Colour-encoding tests. Values are SYNTHETIC TEST DATA.
import { describe, expect, it } from "vitest";
import {
  CALENDAR_RAMP,
  NEUTRAL,
  PLATFORM_COLORS,
  PLATFORM_ORDER,
  SURFACE,
  binEdges,
  binIndex,
  cellStyle,
  contrast,
  frpRadius,
} from "./colors";

describe("calendar encoding", () => {
  it("bins positive values by quantile and ignores zeros", () => {
    const edges = binEdges([0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(edges).toEqual([2, 4, 6, 8, 10]);
    expect(binIndex(1, edges)).toBe(0);
    expect(binIndex(10, edges)).toBe(4);
    expect(binEdges([0, 0])).toEqual([]);
    expect(binEdges([5, 5, 5])).toEqual([5]);
  });

  it("gives every state a non-colour cue", () => {
    const edges = [10];
    expect(cellStyle("zero", 0, edges).background).toBe(NEUTRAL);
    expect(cellStyle("missing", null, edges)).toMatchObject({ pattern: "hatch", marker: "—", background: SURFACE });
    expect(cellStyle("partial", 5, edges).border).toContain("dashed");
    expect(cellStyle("partial", 5, edges).marker).toBe("partial");
    expect(cellStyle("uncovered", 5, edges)).toMatchObject({ marker: "≥" });
    expect(cellStyle("uncovered", 5, edges).border).toContain("dotted");
    expect(CALENDAR_RAMP).toContain(cellStyle("value", 5, edges).background);
  });

  it("keeps cell text readable (WCAG ≥ 4.5:1)", () => {
    const edges = [1, 2, 3, 4, 5];
    for (const v of [1, 2, 3, 4, 5]) {
      const style = cellStyle("value", v, edges);
      expect(contrast(style.background, style.text)).toBeGreaterThanOrEqual(4.5);
    }
  });
});

describe("platform colours", () => {
  it("assigns one fixed colour per platform", () => {
    const colors = PLATFORM_ORDER.map((p) => PLATFORM_COLORS[p]);
    expect(new Set(colors).size).toBe(5);
  });
});

describe("FRP marker size", () => {
  it("grows with FRP, capped, minimum for missing", () => {
    expect(frpRadius(null)).toBe(3);
    expect(frpRadius(16)).toBe(7);
    expect(frpRadius(10_000)).toBe(12);
  });
});
