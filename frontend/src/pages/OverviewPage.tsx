import { AsyncView, ErrorBox, Loading, fmt } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { bboxText } from "../lib/area";
import { PLATFORM_COLORS } from "../lib/colors";
import { formatUtc } from "../lib/time";
import { fetchAvailability, fetchHistory, fetchSummary } from "../services/api";
import { useArea } from "../state/AreaContext";

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[var(--border)] p-4">
      <div className="text-xs text-[var(--text-secondary)]">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--text-secondary)]">{hint}</div>}
    </div>
  );
}

export function OverviewPage() {
  const { query, key } = useArea();
  const summary = useAsync(key, (signal) => fetchSummary(query!, signal));
  const availability = useAsync("availability", (signal) => fetchAvailability(signal));
  const history = useAsync("history", (signal) => fetchHistory(1, signal));

  return (
    <div className="space-y-6">
      <section aria-label="Selected area summary">
        <h2 className="mb-3 text-lg font-medium">Selected area</h2>
        <AsyncView state={summary} what="the area summary">
          {(s) => (
            <>
              <p className="mb-3 text-sm text-[var(--text-secondary)]">
                Area {query?.area.kind === "aoi" ? `"${query.area.name}" ` : ""}
                <span className="font-mono">{bboxText(s.area)}</span> · {s.period.start} → {s.period.end} (UTC)
              </p>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                <Tile label="Satellite detections" value={fmt(s.total_detections)} hint="not individual fires" />
                <Tile
                  label="First / last detection"
                  value={s.first_detection_date ? `${s.first_detection_date}` : "—"}
                  hint={s.last_detection_date ? `to ${s.last_detection_date}` : undefined}
                />
              </div>
              <table className="mt-4 w-full text-sm">
                <caption className="mb-1 text-left text-xs text-[var(--text-secondary)]">
                  Per platform — MODIS and VIIRS are never summed. Months: complete / partial / missing coverage.
                </caption>
                <thead className="text-left text-[var(--text-secondary)]">
                  <tr>
                    <th scope="col" className="py-1">Platform</th>
                    <th scope="col" className="text-right">Detections</th>
                    <th scope="col" className="text-right">Unique 1 km cells</th>
                    <th scope="col" className="text-right">Months complete / partial / missing</th>
                  </tr>
                </thead>
                <tbody>
                  {s.platforms.map((p) => (
                    <tr key={p.platform} className="border-t border-[var(--border)]">
                      <th scope="row" className="py-1 text-left font-normal">
                        <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: PLATFORM_COLORS[p.platform] }} aria-hidden />
                        {p.platform}
                      </th>
                      <td className="text-right tabular-nums">{fmt(p.detections)}</td>
                      <td className="text-right tabular-nums">{fmt(p.unique_cells)}</td>
                      <td className="text-right tabular-nums">
                        {p.months_complete} / {p.months_partial} / {p.months_missing}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </AsyncView>
      </section>

      <section aria-label="Data freshness and coverage">
        <h2 className="mb-3 text-lg font-medium">Data freshness and imported coverage</h2>
        {availability.kind === "loading" && <Loading what="availability" />}
        {availability.kind === "error" && <ErrorBox message={availability.message} />}
        {availability.kind === "ok" && (
          <div className="space-y-2 text-sm">
            <p>
              Latest completed import:{" "}
              <strong>
                {availability.data.latest_completed_import_utc
                  ? formatUtc(availability.data.latest_completed_import_utc)
                  : "none yet"}
              </strong>
            </p>
            {availability.data.imported_coverage.length === 0 ? (
              <p className="text-[var(--text-secondary)]">No data imported yet — no coverage is claimed.</p>
            ) : (
              <table className="w-full">
                <caption className="mb-1 text-left text-xs text-[var(--text-secondary)]">{availability.data.note}</caption>
                <thead className="text-left text-[var(--text-secondary)]">
                  <tr>
                    <th scope="col">Platform</th>
                    <th scope="col">Processing</th>
                    <th scope="col">Extent</th>
                    <th scope="col">First date</th>
                    <th scope="col">Last date</th>
                    <th scope="col" className="text-right">Imports</th>
                  </tr>
                </thead>
                <tbody>
                  {availability.data.imported_coverage.map((c, i) => (
                    <tr key={i} className="border-t border-[var(--border)]">
                      <td>{c.platform ?? "unknown"}</td>
                      <td>{c.processing_status ?? "—"}</td>
                      <td>{c.extent_type}</td>
                      <td>{c.first_date ?? "—"}</td>
                      <td>{c.last_date ?? "—"}</td>
                      <td className="text-right">{c.coverage_records}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
        {history.kind === "ok" && history.data.items[0] && (
          <p className="mt-2 text-sm">
            Last import run: <strong>{history.data.items[0].status}</strong> — {history.data.items[0].file} (
            {fmt(history.data.items[0].rows_written)} rows written)
          </p>
        )}
      </section>
    </div>
  );
}
