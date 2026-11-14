import { useState } from "react";
import { CalendarHeatmap } from "../calendar/CalendarHeatmap";
import { AsyncView } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { fetchCalendar } from "../services/api";
import { useArea } from "../state/AreaContext";
import type { Metric } from "../types/api";

export function CalendarPage() {
  const { query, key } = useArea();
  const [metric, setMetric] = useState<Metric>("detections");
  const state = useAsync(key && `${key}|${metric}`, (signal) => fetchCalendar(query!, metric, signal));
  return (
    <div>
      <div className="mb-4 flex items-center gap-3 text-sm">
        <h2 className="text-lg font-medium">Burning activity calendar</h2>
        <label className="flex items-center gap-2">
          <span className="text-[var(--text-secondary)]">Measure</span>
          <select aria-label="Measure" className="field" value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
            <option value="detections">Detections</option>
            <option value="unique_cells">Unique active 1 km cells</option>
            <option value="cell_days">Active cell-days</option>
          </select>
        </label>
      </div>
      <p className="mb-4 max-w-3xl text-xs text-[var(--text-secondary)]">
        One calendar per satellite; counts from different satellites are not comparable and are never added.
        Blank/hatched months have no imported coverage — unknown, not zero. Anomaly marks compare each satellite
        only with its own history and are experimental.
      </p>
      <AsyncView state={state} what="the calendar">
        {(data) => <CalendarHeatmap cells={data.cells} metric={metric} />}
      </AsyncView>
    </div>
  );
}
