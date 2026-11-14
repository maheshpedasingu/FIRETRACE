import { Fragment, useState } from "react";
import { AsyncView, fmt } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { PLATFORM_COLORS } from "../lib/colors";
import { fetchHotspots } from "../services/api";
import { useArea } from "../state/AreaContext";

const PAGE_SIZE = 100;

export function ExplorerPage() {
  const { query, key } = useArea();
  const [page, setPage] = useState(1);
  const [confidence, setConfidence] = useState<string[]>([]);
  const [daynight, setDaynight] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const reloadKey = key && JSON.stringify([key, page, confidence, daynight]);
  const state = useAsync(reloadKey, (signal) =>
    fetchHotspots(query!, { page, pageSize: PAGE_SIZE, confidence, daynight, includeSource: true }, signal),
  );
  const toggle = (list: string[], set: (v: string[]) => void, value: string) => {
    set(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);
    setPage(1);
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <h2 className="text-lg font-medium">Data explorer</h2>
        <fieldset className="flex items-center gap-2">
          <legend className="sr-only">Confidence</legend>
          <span className="text-[var(--text-secondary)]">Confidence:</span>
          {["low", "nominal", "high"].map((c) => (
            <label key={c} className="flex items-center gap-1">
              <input type="checkbox" checked={confidence.includes(c)} onChange={() => toggle(confidence, setConfidence, c)} />
              {c}
            </label>
          ))}
        </fieldset>
        <fieldset className="flex items-center gap-2">
          <legend className="sr-only">Day or night</legend>
          <span className="text-[var(--text-secondary)]">Day/night:</span>
          {[["D", "day"], ["N", "night"]].map(([v, label]) => (
            <label key={v} className="flex items-center gap-1">
              <input type="checkbox" checked={daynight.includes(v)} onChange={() => toggle(daynight, setDaynight, v)} />
              {label}
            </label>
          ))}
        </fieldset>
      </div>
      <AsyncView state={state} what="detections">
        {(data) => {
          const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
          return (
            <>
              <p className="mb-2 text-sm text-[var(--text-secondary)]">
                {fmt(data.total)} detections · page {data.page} of {pages} · NRT rows replaced by SP where available
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead className="text-left text-[var(--text-secondary)]">
                    <tr>
                      {["Date (UTC)", "Time", "Platform", "Lat", "Lon", "FRP (MW)", "Confidence", "D/N", "Version", "Source file", ""].map((h) => (
                        <th key={h} scope="col" className="px-1 py-1">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((h) => (
                      <Fragment key={h.observation_id}>
                        <tr className="border-t border-[var(--border)] tabular-nums">
                          <td className="px-1">{h.acquisition_date}</td>
                          <td className="px-1">{h.acquisition_time_utc}</td>
                          <td className="px-1">
                            <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ background: PLATFORM_COLORS[h.platform] }} aria-hidden />
                            {h.platform}
                          </td>
                          <td className="px-1">{h.latitude.toFixed(5)}</td>
                          <td className="px-1">{h.longitude.toFixed(5)}</td>
                          <td className="px-1">{fmt(h.frp_mw, 2)}</td>
                          <td className="px-1">{h.confidence_class ?? "—"} ({h.confidence_raw ?? "—"})</td>
                          <td className="px-1">{h.day_night ?? "—"}</td>
                          <td className="px-1">{h.collection_version}</td>
                          <td className="px-1" title={`SHA-256 ${h.source_checksum}`}>
                            {h.source_file}
                            {h.source_member ? ` :: ${h.source_member}` : ""} #{h.source_row_number}
                          </td>
                          <td className="px-1">
                            <button
                              type="button"
                              className="underline"
                              aria-expanded={open === h.observation_id}
                              onClick={() => setOpen(open === h.observation_id ? null : h.observation_id)}
                            >
                              {open === h.observation_id ? "hide" : "source row"}
                            </button>
                          </td>
                        </tr>
                        {open === h.observation_id && (
                          <tr>
                            <td colSpan={11} className="bg-black/30 p-2 font-mono">
                              {h.source_attributes}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-3 flex gap-2 text-sm">
                <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                  Previous
                </button>
                <button type="button" className="btn" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                  Next
                </button>
              </div>
            </>
          );
        }}
      </AsyncView>
    </div>
  );
}
