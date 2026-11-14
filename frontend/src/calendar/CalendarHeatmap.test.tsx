// Calendar heatmap tests. All cells are SYNTHETIC TEST DATA.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CalendarCell } from "../types/api";
import { CalendarHeatmap } from "./CalendarHeatmap";

afterEach(cleanup);

const base = { platform: "Aqua", year: 2021, days_in_range: 31, modified_z: null, anomaly: null, anomaly_status: null } as const;
const CELLS: CalendarCell[] = [
  { ...base, month: 1, state: "value", value: 80, coverage_status: "complete", days_covered: 31,
    modified_z: 6.7, anomaly: "unusually high", anomaly_status: "assessed" },
  { ...base, month: 2, state: "zero", value: 0, coverage_status: "complete", days_covered: 28 },
  { ...base, month: 3, state: "partial", value: 5, coverage_status: "partial", days_covered: 10 },
  { ...base, month: 4, state: "uncovered", value: 3, coverage_status: "missing", days_covered: 0 },
  { ...base, month: 5, state: "missing", value: null, coverage_status: "missing", days_covered: 0 },
];

describe("CalendarHeatmap", () => {
  it("renders a years × months table with every state distinguishable without colour", () => {
    render(<CalendarHeatmap cells={CELLS} metric="detections" />);
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Year", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]);
    const byState = (s: string) => table.querySelector(`[data-state="${s}"]`) as HTMLElement;
    expect(byState("value").textContent).toContain("80");
    expect(byState("value").textContent).toContain("▲");
    expect(byState("zero").textContent).toBe("0");
    expect(byState("partial").textContent).toContain("partial");
    expect(byState("uncovered").textContent).toContain("≥3");
    expect(byState("missing").textContent).toBe("—");
    expect(screen.getAllByText(/Outside the selected period|·/).length).toBeGreaterThan(0);
  });

  it("describes a cell in words and shows details when selected", () => {
    render(<CalendarHeatmap cells={CELLS} metric="detections" />);
    const cell = screen.getByRole("button", { name: /Jan 2021: Covered, detections; 80 detections; 31\/31 days covered; unusually high \(modified z 6\.70\)/ });
    fireEvent.click(cell);
    expect(cell.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("Selected month")).toBeTruthy();
  });

  it("has a legend that explains missing is not zero", () => {
    render(<CalendarHeatmap cells={CELLS} metric="detections" />);
    const legend = screen.getByLabelText("Calendar legend");
    expect(legend.textContent).toContain("No data — unknown, not zero");
    expect(legend.textContent).toContain("Covered, no detections (real zero)");
  });
});
