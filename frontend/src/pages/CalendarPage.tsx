import { useState } from "react";
import { CalendarHeatmap } from "../calendar/CalendarHeatmap";
import { HarmonizedCalendar } from "../calendar/HarmonizedCalendar";
import { AsyncView } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { fetchCalendar, fetchHarmonizedCalendar } from "../services/api";
import { describeQuery } from "../lib/area";
import { useArea } from "../state/AreaContext";
import type { HarmonizedReference, Metric } from "../types/api";

type View = "harmonized" | "platforms";

export function CalendarPage() {
  const { query, key } = useArea();
  const [metric, setMetric] = useState<Metric>("detections");
  const [view, setView] = useState<View>("harmonized");
  const [reference, setReference] = useState<HarmonizedReference>("modis");
  const perPlatform = useAsync(view === "platforms" && key ? `${key}|${metric}` : null, (signal) =>
    fetchCalendar(query!, metric, signal),
  );
  const harmonized = useAsync(view === "harmonized" && key ? `${key}|${metric}|${reference}` : null, (signal) =>
    fetchHarmonizedCalendar(query!, metric, reference, signal),
  );
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <h2 className="text-lg font-medium">Burning activity calendar</h2>
        <div role="radiogroup" aria-label="Calendar view" className="flex gap-1">
          {(
            [
              ["harmonized", "Harmonized (one calendar)"],
              ["platforms", "Per satellite"],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              role="radio"
              aria-checked={view === v}
              className={view === v ? "btn-primary" : "btn"}
              onClick={() => setView(v)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2">
          <span className="text-[var(--text-secondary)]">Measure</span>
          <select aria-label="Measure" className="field" value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
            <option value="detections">Detections</option>
            <option value="unique_cells">Unique active 1 km cells</option>
            <option value="cell_days">Active cell-days</option>
          </select>
        </label>
        {view === "harmonized" && (
          <label className="flex items-center gap-2">
            <span className="text-[var(--text-secondary)]">Units</span>
            <select
              aria-label="Harmonized units"
              className="field"
              value={reference}
              onChange={(e) => setReference(e.target.value as HarmonizedReference)}
            >
              <option value="modis">MODIS-equivalent (longest record, from 2000)</option>
              <option value="viirs">VIIRS Suomi-NPP-equivalent (finer detail, from 2012)</option>
            </select>
          </label>
        )}
      </div>
      {view === "harmonized" ? (
        <>
          <p className="mb-4 max-w-4xl text-xs text-[var(--text-secondary)]">
            One continuous record: every month is expressed in the units of one reference sensor. Months measured by
            another sensor are converted with a factor fitted where both sensors overlap and tested on held-out years
            (≈ marks converted months). This is a statistical bridge, not a physical correction, and is experimental;
            the per-satellite calendars remain the original record. Hatched months have no data — unknown, not zero.
          </p>
          <AsyncView state={harmonized} what="the harmonized calendar">
            {(data) => <HarmonizedCalendar data={data} subtitle={query ? describeQuery(query) : ""} />}
          </AsyncView>
        </>
      ) : (
        <>
          <p className="mb-4 max-w-3xl text-xs text-[var(--text-secondary)]">
            One calendar per satellite; counts from different satellites are not comparable and are never added.
            Blank/hatched months have no imported coverage — unknown, not zero. Anomaly marks compare each satellite
            only with its own history and are experimental.
          </p>
          <AsyncView state={perPlatform} what="the calendar">
            {(data) => <CalendarHeatmap cells={data.cells} metric={metric} subtitle={query ? describeQuery(query) : ""} />}
          </AsyncView>
        </>
      )}
    </div>
  );
}
