import { useMemo, useState } from "react";
import { fmt } from "../components/Status";
import { STATE_LABELS, binEdges, cellStyle } from "../lib/colors";
import { compareWithHistory, latestCompleteMonth, latestMonth, monthlyClimatology, sourceTag } from "../lib/harmonized";
import type { ConversionFit, HarmonizedCalendar as HarmonizedData, HarmonizedCell } from "../types/api";
import { CalendarLegend } from "./CalendarHeatmap";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const HATCH = "repeating-linear-gradient(45deg, transparent 0 4px, #383835 4px 6px)";

function describe(cell: HarmonizedCell, unit: string): string {
  const when = `${MONTHS[cell.month - 1]} ${cell.year}`;
  const value = cell.value === null ? "no value" : `${fmt(cell.value, 1)} ${unit}`;
  const source = cell.source
    ? cell.converted
      ? `from ${cell.source} (${fmt(cell.source_value)} × ${fmt(cell.factor, 3)}, ±${fmt((cell.relative_uncertainty ?? 0) * 100)}% validation error)`
      : `measured by ${cell.source} (reference sensor)`
    : cell.note;
  const anomaly =
    cell.anomaly_status === "assessed"
      ? `; ${cell.anomaly} (modified z ${fmt(cell.modified_z, 2)})`
      : cell.anomaly_status
        ? `; anomaly not assessed (${cell.anomaly_status.replace(/_/g, " ")})`
        : "";
  return `Harmonized, ${when}: ${STATE_LABELS[cell.state]}; ${value}; ${source}${anomaly}`;
}

function FitsTable({ fits, reference }: { fits: ConversionFit[]; reference: string }) {
  return (
    <table className="mt-2 w-full text-sm">
      <caption className="mb-1 text-left text-xs text-[var(--text-secondary)]">
        Conversion into {reference} units: one factor per source, fitted as a ratio of sums on training years where both
        are completely covered, then tested on held-out years (every third overlap year). Without enough overlap no factor
        is invented and those months stay unharmonized.
      </caption>
      <thead className="text-left text-[var(--text-secondary)]">
        <tr>
          <th scope="col">Source</th>
          <th scope="col">Status</th>
          <th scope="col" className="text-right">Factor</th>
          <th scope="col" className="text-right">Train / validation months</th>
          <th scope="col" className="text-right">Validation error (RMSE, % of mean)</th>
          <th scope="col" className="text-right">Log correlation</th>
          <th scope="col">Note</th>
        </tr>
      </thead>
      <tbody>
        {fits.map((f) => (
          <tr key={f.source} className="border-t border-[var(--border)]">
            <th scope="row" className="py-1 text-left font-normal">{f.source}</th>
            <td>{f.status === "reference" ? "reference" : f.status}</td>
            <td className="text-right tabular-nums">{f.status === "reference" ? "1" : fmt(f.factor, 3)}</td>
            <td className="text-right tabular-nums">{f.status === "reference" ? "—" : `${f.n_train} / ${f.n_validation}`}</td>
            <td className="text-right tabular-nums">
              {f.status === "estimated" ? `${fmt(f.rmse, 1)} (${fmt((f.relative_rmse ?? 0) * 100)}%)` : "—"}
            </td>
            <td className="text-right tabular-nums">{fmt(f.log_correlation, 2)}</td>
            <td className="text-xs text-[var(--text-secondary)]">{f.status === "unavailable" ? f.reason : ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CurrentVsHistory({ cells, unit }: { cells: HarmonizedCell[]; unit: string }) {
  const last = latestMonth(cells);
  if (!last) return null;
  const target = latestCompleteMonth(cells);
  const lastCell = cells.find((c) => c.year === last.year && c.month === last.month);
  const lastWhen = `${MONTHS[last.month - 1]} ${last.year}`;
  const skipped =
    target && (target.year !== last.year || target.month !== last.month) && lastCell
      ? ` (${lastWhen} is not compared: ${STATE_LABELS[lastCell.state].toLowerCase()}, e.g. only part of the month is in the selected period.)`
      : "";
  let text: string;
  if (!target) {
    text = `No completely covered month in the selected period, so nothing is compared with history.`;
  } else {
    const c = compareWithHistory(cells, target.year, target.month);
    const when = `${MONTHS[c.month - 1]} ${c.year}`;
    if (c.median === null) {
      text = `${when}: ${fmt(c.value, 1)} ${unit}; no earlier completely covered ${MONTHS[c.month - 1]} to compare with.`;
    } else {
      const rel = c.ratio === null ? "" : ` — ${fmt(c.ratio, 2)} × the median`;
      text = `${when}: ${fmt(c.value, 1)} ${unit} vs a median of ${fmt(c.median, 1)} over ${c.historyYears.length} earlier ${MONTHS[c.month - 1]}s (${c.historyYears[0]}–${c.historyYears[c.historyYears.length - 1]})${rel}.`;
    }
  }
  return (
    <p className="mb-3 rounded border border-[var(--border)] p-3 text-sm" aria-live="polite">
      <span className="font-medium">Latest complete month vs history: </span>
      {text}
      {skipped}
    </p>
  );
}

function Climatology({ cells, unit }: { cells: HarmonizedCell[]; unit: string }) {
  const clim = monthlyClimatology(cells);
  const ranked = clim.filter((m) => m.median !== null).sort((a, b) => (b.median ?? 0) - (a.median ?? 0));
  if (!ranked.length) return null;
  return (
    <p className="mb-3 text-sm text-[var(--text-secondary)]">
      Typical fire season (median {unit} per month across completely covered years):{" "}
      {ranked.slice(0, 3).map((m, i) => (
        <span key={m.month} className="text-[var(--text-primary)]">
          {i > 0 && ", "}
          {MONTHS[m.month - 1]} {fmt(m.median, 0)}
        </span>
      ))}
      {ranked.length > 3 && " …"}
    </p>
  );
}

/** One harmonized years × months calendar with the conversion fits beneath it. */
export function HarmonizedCalendar({ data }: { data: HarmonizedData }) {
  const [selected, setSelected] = useState<HarmonizedCell | null>(null);
  const cells = data.cells;
  const edges = useMemo(() => binEdges(cells.map((c) => c.value ?? 0)), [cells]);
  const years = [...new Set(cells.map((c) => c.year))].sort((a, b) => a - b);
  const byKey = new Map(cells.map((c) => [`${c.year}-${c.month}`, c]));
  const unit = data.unit;
  if (!cells.length) return <p className="text-sm text-[var(--text-secondary)]">No months in the selected period.</p>;
  return (
    <div>
      <CurrentVsHistory cells={cells} unit={unit} />
      <Climatology cells={cells} unit={unit} />
      <CalendarLegend edges={edges} />
      <p className="mb-2 text-xs text-[var(--text-secondary)]">
        Small letters show the source of each month: T+A = MODIS Terra+Aqua, T = Terra, A = Aqua, S = Suomi-NPP, N20 /
        N21 = NOAA-20 / NOAA-21. ≈ marks a value converted from another sensor (uncertainty in the fits table).
      </p>
      <section aria-label="Harmonized activity calendar" className="mb-6">
        <h3 className="mb-2 font-medium">Harmonized — {unit}</h3>
        <table className="border-separate border-spacing-[2px] text-xs">
          <caption className="sr-only">Harmonized {unit} by year and month</caption>
          <thead>
            <tr>
              <th scope="col" className="w-12 text-left font-normal text-[var(--text-secondary)]">Year</th>
              {MONTHS.map((m) => (
                <th key={m} scope="col" className="w-16 font-normal text-[var(--text-secondary)]">{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((year) => (
              <tr key={year}>
                <th scope="row" className="text-left font-normal text-[var(--text-secondary)]">{year}</th>
                {MONTHS.map((_, i) => {
                  const cell = byKey.get(`${year}-${i + 1}`);
                  if (!cell) {
                    return (
                      <td key={i} className="h-10 text-center text-[var(--text-muted)]" title="Outside the selected period">
                        ·
                      </td>
                    );
                  }
                  const style = cellStyle(cell.state, cell.value, edges);
                  const label = describe(cell, unit);
                  const mark = cell.anomaly === "unusually high" ? " ▲" : cell.anomaly === "unusually low" ? " ▼" : "";
                  return (
                    <td key={i} className="p-0">
                      <button
                        type="button"
                        title={label}
                        aria-label={label}
                        aria-pressed={selected === cell}
                        data-state={cell.state}
                        onClick={() => setSelected(cell)}
                        className="h-10 w-16 rounded text-[11px] leading-tight focus:outline-2 focus:outline-offset-1 focus:outline-white"
                        style={{
                          background: style.pattern === "hatch" ? `${HATCH}, ${style.background}` : style.background,
                          color: style.text,
                          border: selected === cell ? "2px solid #f0efec" : style.border,
                        }}
                      >
                        {cell.state === "missing"
                          ? style.marker
                          : `${cell.converted ? "≈" : ""}${style.marker === "≥" ? "≥" : ""}${fmt(cell.value)}`}
                        {mark && <span aria-hidden>{mark}</span>}
                        {cell.source && (
                          <span className="block text-[9px] opacity-90">
                            {sourceTag(cell.source)}
                            {cell.state === "partial" ? " · partial" : ""}
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {selected && (
        <aside aria-live="polite" className="mb-4 rounded border border-[var(--border)] p-3 text-sm">
          <h4 className="mb-1 font-medium">Selected month</h4>
          <p>{describe(selected, unit)}</p>
        </aside>
      )}
      <FitsTable fits={data.fits} reference={data.reference_source} />
    </div>
  );
}
