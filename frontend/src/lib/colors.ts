// Colour encodings. Values are the dark-mode steps of the validated reference palette;
// each set was checked with the dataviz palette validator (2026-11-14):
// - PLATFORM_COLORS (charts, adjacent pairs, dark surface #1a1a19): all checks pass,
//   worst adjacent CVD ΔE 8.4, normal-vision ΔE 19.3. Always shown with a legend.
// - SENSOR_COLORS (map scatter, all pairs): pass, ΔE 26.8 CVD / 31.8 normal. MODIS is
//   also drawn as a ring and VIIRS as a filled dot, so identity is not colour-only.
// - CALENDAR_RAMP (one hue, ordinal check): pass; darkest step clears 2:1 vs surface.
// Colour follows the entity: a platform keeps its colour whatever is filtered.

import type { CellState, Platform, Sensor } from "../types/api";

export const SURFACE = "#1a1a19";
export const TEXT_PRIMARY = "#f0efec";
export const TEXT_SECONDARY = "#c3c2b7";
export const NEUTRAL = "#383835";

export const PLATFORM_ORDER: Platform[] = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20", "NOAA-21"];

export const PLATFORM_COLORS: Record<Platform, string> = {
  Terra: "#3987e5",
  Aqua: "#d95926",
  "Suomi-NPP": "#199e70",
  "NOAA-20": "#c98500",
  "NOAA-21": "#d55181",
};

export const PLATFORM_SENSOR: Record<Platform, Sensor> = {
  Terra: "MODIS",
  Aqua: "MODIS",
  "Suomi-NPP": "VIIRS",
  "NOAA-20": "VIIRS",
  "NOAA-21": "VIIRS",
};

export const SENSOR_COLORS: Record<Sensor, string> = { MODIS: "#d95926", VIIRS: "#3987e5" };

// Light → dark is low → high on a light surface; on the dark dashboard the darkest step
// (closest to the surface) is the lowest bin, so higher activity reads brighter.
export const CALENDAR_RAMP = ["#184f95", "#256abf", "#3987e5", "#86b6ef", "#cde2fb"];

/** Quantile bin edges (upper bounds) for positive values; ≤ ramp length bins. */
export function binEdges(values: number[], bins = CALENDAR_RAMP.length): number[] {
  const positive = values.filter((v) => Number.isFinite(v) && v > 0).sort((a, b) => a - b);
  if (positive.length === 0) return [];
  const edges: number[] = [];
  for (let i = 1; i <= bins; i++) {
    const idx = Math.min(positive.length - 1, Math.ceil((i / bins) * positive.length) - 1);
    const edge = positive[idx];
    if (edges.length === 0 || edge > edges[edges.length - 1]) edges.push(edge);
  }
  return edges;
}

export function binIndex(value: number, edges: number[]): number {
  for (let i = 0; i < edges.length; i++) if (value <= edges[i]) return i;
  return edges.length - 1;
}

function luminance(hex: string): number {
  const channel = (i: number) => {
    const c = parseInt(hex.slice(1 + 2 * i, 3 + 2 * i), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
}

/** WCAG 2 contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** Dark or light text, whichever contrasts more with the background. */
export function bestText(background: string): string {
  return contrast(background, "#0b0b0b") >= contrast(background, TEXT_PRIMARY)
    ? "#0b0b0b"
    : TEXT_PRIMARY;
}

export interface CellStyle {
  background: string;
  text: string;
  border: string; // CSS border shorthand
  pattern: "none" | "hatch";
  marker: string; // short text shown in the cell besides the value
}

/** Visual encoding of one calendar cell. Never colour alone: borders, hatch and text. */
export function cellStyle(state: CellState, value: number | null, edges: number[]): CellStyle {
  const rampColor = (v: number) => CALENDAR_RAMP[binIndex(v, edges)];
  const textOn = bestText;
  switch (state) {
    case "value": {
      const bg = rampColor(value ?? 0);
      return { background: bg, text: textOn(bg), border: "1px solid transparent", pattern: "none", marker: "" };
    }
    case "zero":
      return { background: NEUTRAL, text: TEXT_PRIMARY, border: "1px solid transparent", pattern: "none", marker: "" };
    case "partial": {
      const bg = value && value > 0 ? rampColor(value) : NEUTRAL;
      return { background: bg, text: textOn(bg), border: `2px dashed ${TEXT_SECONDARY}`, pattern: "none", marker: "partial" };
    }
    case "uncovered": {
      const bg = rampColor(value ?? 0);
      return { background: bg, text: textOn(bg), border: `2px dotted ${TEXT_SECONDARY}`, pattern: "none", marker: "≥" };
    }
    default:
      return { background: SURFACE, text: TEXT_SECONDARY, border: `1px solid ${NEUTRAL}`, pattern: "hatch", marker: "—" };
  }
}

export const STATE_LABELS: Record<CellState, string> = {
  value: "Covered, detections",
  zero: "Covered, no detections (real zero)",
  partial: "Partly covered — value covers covered days only",
  uncovered: "Detections, but area not fully covered — lower bound",
  missing: "No data — unknown, not zero",
};

/** Map marker radius (px) from FRP; missing FRP gets the minimum size. */
export function frpRadius(frp: number | null): number {
  if (frp === null || !Number.isFinite(frp) || frp <= 0) return 3;
  return Math.min(12, 3 + Math.sqrt(frp));
}
