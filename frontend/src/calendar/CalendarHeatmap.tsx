import { useMemo, useState } from "react";
import { fmt } from "../components/Status";
import { CALENDAR_RAMP, PLATFORM_COLORS, STATE_LABELS, binEdges, cellStyle } from "../lib/colors";
import type { CalendarCell, CellState, Metric, Platform } from "../types/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const HATCH = "repeating-linear-gradient(45deg, transparent 0 4px, #383835 4px 6px)";
const METRIC_LABEL: Record<Metric, string> = {
  detections: "detections",
  unique_cells: "unique active 1 km cells",
  cell_days: "active cell-days",
};

function describe(cell: CalendarCell, metric: Metric): string {
  const when = `${MONTHS[cell.month - 1]} ${cell.year}`;
  const value = cell.value === null ? "no value" : `${fmt(cell.value)} ${METRIC_LABEL[metric]}`;
  const coverage = `${cell.days_covered}/${cell.days_in_range} days covered`;
  const anomaly =
    cell.anomaly_status === "assessed"
      ? `; ${cell.anomaly} (modified z ${fmt(cell.modified_z, 2)})`
      : cell.anomaly_status
        ? `; anomaly not assessed (${cell.anomaly_status.replace(/_/g, " ")})`
        : "";
  return `${cell.platform}, ${when}: ${STATE_LABELS[cell.state]}; ${value}; ${coverage}${anomaly}`;
}

/** Years × months heatmap for one platform. A table, so it is also the table view. */
export function PlatformCalendar({
  platform,
  cells,
  metric,
  edges,
  onSelect,
  selected,
}: {
  platform: Platform;
  cells: CalendarCell[];
  metric: Metric;
  edges: number[];
  onSelect: (cell: CalendarCell) => void;
  selected: CalendarCell | null;
}) {
  const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b);
  const byKey = new Map(cells.map((c) => [`${c.year}-${c.month}`, c]));
  return (
    <section aria-label={`${platform} activity calendar`} className="mb-6">
      <h3 className="mb-2 flex items-center gap-2 font-medium">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: PLATFORM_COLORS[platform] }} aria-hidden />
        {platform}
      </h3>
      <table className="border-separate border-spacing-[2px] text-xs">
        <caption className="sr-only">
          {platform} {METRIC_LABEL[metric]} by year and month
        </caption>
        <thead>
          <tr>
            <th scope="col" className="w-12 text-left font-normal text-[var(--text-secondary)]">
              Year
            </th>
            {MONTHS.map((m) => (
              <th key={m} scope="col" className="w-14 font-normal text-[var(--text-secondary)]">
                {m}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((year) => (
            <tr key={year}>
              <th scope="row" className="text-left font-normal text-[var(--text-secondary)]">
                {year}
              </th>
              {MONTHS.map((_, i) => {
                const cell = byKey.get(`${year}-${i + 1}`);
                if (!cell) {
                  return (
                    <td key={i} className="h-9 text-center text-[var(--text-muted)]" title="Outside the selected period">
                      ·
                    </td>
                  );
                }
                const style = cellStyle(cell.state, cell.value, edges);
                const label = describe(cell, metric);
                const isSelected = selected === cell;
                const anomalyMark =
                  cell.anomaly === "unusually high" ? "▲" : cell.anomaly === "unusually low" ? "▼" : "";
                return (
                  <td key={i} className="p-0">
                    <button
                      type="button"
                      title={label}
                      aria-label={label}
                      aria-pressed={isSelected}
                      data-state={cell.state}
                      onClick={() => onSelect(cell)}
                      className="h-9 w-14 rounded text-[11px] leading-tight focus:outline-2 focus:outline-offset-1 focus:outline-white"
                      style={{
                        background: style.pattern === "hatch" ? `${HATCH}, ${style.background}` : style.background,
                        color: style.text,
                        border: isSelected ? "2px solid #f0efec" : style.border,
                      }}
                    >
                      {cell.state === "missing" ? style.marker : `${style.marker === "≥" ? "≥" : ""}${fmt(cell.value)}`}
                      {anomalyMark && <span aria-hidden> {anomalyMark}</span>}
                      {cell.state === "partial" && <span className="block text-[9px] opacity-90">partial</span>}
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export function CalendarLegend({ edges }: { edges: number[] }) {
  const states: CellState[] = ["value", "zero", "partial", "uncovered", "missing"];
  return (
    <div aria-label="Calendar legend" className="mb-4 space-y-2 text-xs text-[var(--text-secondary)]">
      <div className="flex flex-wrap items-center gap-1">
        <span className="mr-1">Value bins:</span>
        {edges.length === 0 && <span>no positive values in view</span>}
        {edges.map((edge, i) => (
          <span key={edge} className="flex items-center gap-1">
            <span className="inline-block h-3 w-6 rounded-sm" style={{ background: CALENDAR_RAMP[i] }} aria-hidden />
            {i === 0 ? `1–${fmt(edge)}` : `${fmt(edges[i - 1] + 1)}–${fmt(edge)}`}
          </span>
        ))}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {states.map((s) => {
          const style = cellStyle(s, edges.length ? edges[0] : 1, edges.length ? edges : [1]);
          return (
            <li key={s} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-5 rounded-sm"
                style={{
                  background: style.pattern === "hatch" ? `${HATCH}, ${style.background}` : style.background,
                  border: style.border,
                }}
                aria-hidden
              />
              {STATE_LABELS[s]}
            </li>
          );
        })}
        <li>▲ / ▼ unusually high / low vs the platform's own history (experimental)</li>
      </ul>
    </div>
  );
}

/** Calendars for every platform present, sharing one set of value bins. */
export function CalendarHeatmap({ cells, metric }: { cells: CalendarCell[]; metric: Metric }) {
  const [selected, setSelected] = useState<CalendarCell | null>(null);
  const edges = useMemo(() => binEdges(cells.map((c) => c.value ?? 0)), [cells]);
  const platforms = [...new Set(cells.map((c) => c.platform))];
  if (cells.length === 0) {
    return <p className="text-sm text-[var(--text-secondary)]">No months in the selected period.</p>;
  }
  return (
    <div>
      <CalendarLegend edges={edges} />
      {platforms.map((p) => (
        <PlatformCalendar
          key={p}
          platform={p}
          cells={cells.filter((c) => c.platform === p)}
          metric={metric}
          edges={edges}
          onSelect={setSelected}
          selected={selected}
        />
      ))}
      {selected && (
        <aside aria-live="polite" className="rounded border border-[var(--border)] p-3 text-sm">
          <h4 className="mb-1 font-medium">Selected month</h4>
          <p>{describe(selected, metric)}</p>
        </aside>
      )}
    </div>
  );
}
