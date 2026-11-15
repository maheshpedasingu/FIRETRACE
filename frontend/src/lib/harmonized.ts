/** Pure helpers for the harmonized calendar (testable without a browser). */
import type { HarmonizedCell } from "../types/api";

/** Short label of the source that supplied a harmonized month. */
export const SOURCE_TAGS: Record<string, string> = {
  "MODIS (Terra+Aqua)": "T+A",
  Terra: "T",
  Aqua: "A",
  "Suomi-NPP": "S",
  "NOAA-20": "N20",
  "NOAA-21": "N21",
};

export function sourceTag(source: string | null): string {
  return source ? (SOURCE_TAGS[source] ?? source) : "";
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

export interface HistoryComparison {
  year: number;
  month: number;
  value: number | null;
  state: HarmonizedCell["state"];
  historyYears: number[];
  median: number | null;
  /** value / median; null when either is missing or the median is 0 */
  ratio: number | null;
}

/**
 * Compare one month with the same calendar month in EARLIER years. Only completely
 * covered months (states "value" or "zero") count, so missing data never pulls the
 * median down.
 */
export function compareWithHistory(cells: HarmonizedCell[], year: number, month: number): HistoryComparison {
  const target = cells.find((c) => c.year === year && c.month === month);
  const history = cells.filter(
    (c) => c.month === month && c.year < year && (c.state === "value" || c.state === "zero") && c.value !== null,
  );
  const med = history.length ? median(history.map((c) => c.value as number)) : null;
  const complete = target && (target.state === "value" || target.state === "zero");
  const value = target?.value ?? null;
  return {
    year,
    month,
    value,
    state: target?.state ?? "missing",
    historyYears: history.map((c) => c.year).sort((a, b) => a - b),
    median: med,
    ratio: complete && value !== null && med ? value / med : null,
  };
}

/** The latest month of the calendar (the "current" month of the selected period). */
export function latestMonth(cells: HarmonizedCell[]): { year: number; month: number } | null {
  if (!cells.length) return null;
  const last = cells.reduce((a, b) => (b.year * 12 + b.month > a.year * 12 + a.month ? b : a));
  return { year: last.year, month: last.month };
}

/** Ranking of calendar months by their median value across complete years. */
export function monthlyClimatology(cells: HarmonizedCell[]): { month: number; median: number | null; years: number }[] {
  return Array.from({ length: 12 }, (_, i) => {
    const vals = cells
      .filter((c) => c.month === i + 1 && (c.state === "value" || c.state === "zero") && c.value !== null)
      .map((c) => c.value as number);
    return { month: i + 1, median: vals.length ? median(vals) : null, years: vals.length };
  });
}
