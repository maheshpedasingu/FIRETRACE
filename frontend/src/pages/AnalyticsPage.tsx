import { useState } from "react";
import { MonthlyChart } from "../charts/MonthlyChart";
import { AsyncView, fmt } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { PLATFORM_COLORS } from "../lib/colors";
import {
  fetchAnomalies,
  fetchMonthly,
  fetchSensorComparison,
  fetchSummary,
  fetchYearly,
} from "../services/api";
import { describeQuery } from "../lib/area";
import { useArea } from "../state/AreaContext";
import type { Metric, Platform } from "../types/api";

const Dot = ({ p }: { p: Platform }) => (
  <span className="mr-2 inline-block h-2 w-2 rounded-full" style={{ background: PLATFORM_COLORS[p] }} aria-hidden />
);

export function AnalyticsPage() {
  const { query, key } = useArea();
  const [metric, setMetric] = useState<Metric>("detections");
  const monthly = useAsync(key, (s) => fetchMonthly(query!, s));
  const yearly = useAsync(key && `${key}|${metric}`, (s) => fetchYearly(query!, metric, s));
  const summary = useAsync(key, (s) => fetchSummary(query!, s));
  const anomalies = useAsync(key && `${key}|${metric}`, (s) => fetchAnomalies(query!, metric, undefined, s));
  const comparison = useAsync(key, (s) => fetchSensorComparison(query!, s));

  return (
    <div className="space-y-8">
      <section aria-label="Monthly activity">
        <h2 className="mb-3 text-lg font-medium">Monthly activity per satellite</h2>
        <AsyncView state={monthly} what="monthly analytics">
          {(d) => (
            <div className="grid gap-4 lg:grid-cols-2">
              <MonthlyChart rows={d.months} field="detections" title="Detections per month" subtitle={query ? describeQuery(query) : ""} />
              <MonthlyChart rows={d.months} field="unique_cells" title="Unique active 1 km cells per month" subtitle={query ? describeQuery(query) : ""} />
              <MonthlyChart rows={d.months} field="frp_sum_mw" title="Summed FRP per month (MW)" subtitle={query ? describeQuery(query) : ""} />
            </div>
          )}
        </AsyncView>
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          Gaps mean no imported coverage (unknown), not zero. Satellites differ in sensitivity, so compare each line
          with its own history rather than with other lines.
        </p>
      </section>

      <section aria-label="Yearly totals">
        <div className="mb-3 flex items-center gap-3">
          <h2 className="text-lg font-medium">Yearly totals and year-over-year</h2>
          <select aria-label="Measure" className="field text-sm" value={metric} onChange={(e) => setMetric(e.target.value as Metric)}>
            <option value="detections">Detections</option>
            <option value="unique_cells">Unique active cells</option>
            <option value="cell_days">Active cell-days</option>
          </select>
        </div>
        <AsyncView state={yearly} what="yearly analytics">
          {(d) => (
            <table className="w-full text-sm">
              <thead className="text-left text-[var(--text-secondary)]">
                <tr>
                  <th scope="col">Platform</th>
                  <th scope="col">Year</th>
                  <th scope="col" className="text-right">Complete months</th>
                  <th scope="col" className="text-right">Total</th>
                  <th scope="col" className="text-right">YoY change</th>
                  <th scope="col">Note</th>
                </tr>
              </thead>
              <tbody>
                {d.years.map((y) => (
                  <tr key={`${y.platform}-${y.year}`} className="border-t border-[var(--border)]">
                    <td><Dot p={y.platform} />{y.platform}</td>
                    <td>{y.year}</td>
                    <td className="text-right">{y.complete_months}/12</td>
                    <td className="text-right tabular-nums">
                      {fmt(y.total)}
                      {!y.complete_year && y.total !== null ? " (partial)" : ""}
                    </td>
                    <td className="text-right tabular-nums">
                      {y.yoy_change_pct === null ? "—" : `${fmt(y.yoy_change_pct, 1)}%`}
                    </td>
                    <td className="text-xs text-[var(--text-secondary)]">{y.yoy_note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncView>
      </section>

      <section aria-label="FRP and detection distributions">
        <h2 className="mb-3 text-lg font-medium">FRP, confidence and day/night</h2>
        <AsyncView state={summary} what="distributions">
          {(s) =>
            s.distributions.length === 0 ? (
              <p className="text-sm text-[var(--text-secondary)]">No detections in this area and period.</p>
            ) : (
              <table className="w-full text-sm">
                <caption className="mb-1 text-left text-xs text-[var(--text-secondary)]">
                  FRP is per detected pixel (MW), not burned area; MODIS and VIIRS FRP are not directly comparable.
                  {s.frp_percentile_period && s.frp_percentile_period.start !== s.period.start && (
                    <>
                      {" "}Counts and FRP max cover the whole period; FRP median and p90 use detections from{" "}
                      {s.frp_percentile_period.start} to {s.frp_percentile_period.end} (last 12 months).
                    </>
                  )}
                </caption>
                <thead className="text-left text-[var(--text-secondary)]">
                  <tr>
                    <th scope="col">Platform</th>
                    <th scope="col" className="text-right">Detections</th>
                    <th scope="col" className="text-right">FRP median</th>
                    <th scope="col" className="text-right">FRP p90</th>
                    <th scope="col" className="text-right">FRP max</th>
                    <th scope="col" className="text-right">FRP missing</th>
                    <th scope="col" className="text-right">Conf. low / nom. / high</th>
                    <th scope="col" className="text-right">Day / night</th>
                  </tr>
                </thead>
                <tbody>
                  {s.distributions.map((d) => (
                    <tr key={d.platform} className="border-t border-[var(--border)] tabular-nums">
                      <td><Dot p={d.platform} />{d.platform}</td>
                      <td className="text-right">{fmt(d.detections)}</td>
                      <td className="text-right">{fmt(d.frp_median_mw, 2)}</td>
                      <td className="text-right">{fmt(d.frp_p90_mw, 2)}</td>
                      <td className="text-right">{fmt(d.frp_max_mw, 2)}</td>
                      <td className="text-right">{fmt(d.frp_missing)}</td>
                      <td className="text-right">
                        {fmt(d.confidence_low)} / {fmt(d.confidence_nominal)} / {fmt(d.confidence_high)}
                      </td>
                      <td className="text-right">
                        {fmt(d.day)} / {fmt(d.night)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </AsyncView>
      </section>

      <section aria-label="Anomalies">
        <h2 className="mb-1 text-lg font-medium">Unusual activity (experimental)</h2>
        <p className="mb-3 text-xs text-[var(--text-secondary)]">
          Latest whole month of the period vs the same month in earlier, fully covered years of the same satellite
          (median and MAD; |modified z| ≥ 3.5 is unusual). A month only partly inside the period is never the target.
          This is not a forecast.
        </p>
        <AsyncView state={anomalies} what="anomalies">
          {(a) => (
            <table className="w-full text-sm">
              <caption className="mb-1 text-left text-xs text-[var(--text-secondary)]">Target month {a.target}</caption>
              <thead className="text-left text-[var(--text-secondary)]">
                <tr>
                  <th scope="col">Platform</th>
                  <th scope="col" className="text-right">Value</th>
                  <th scope="col" className="text-right">History years</th>
                  <th scope="col" className="text-right">Median</th>
                  <th scope="col" className="text-right">Modified z</th>
                  <th scope="col">Result</th>
                </tr>
              </thead>
              <tbody>
                {a.assessments.map((r) => (
                  <tr key={r.platform} className="border-t border-[var(--border)] tabular-nums">
                    <td><Dot p={r.platform} />{r.platform}</td>
                    <td className="text-right">{fmt(r.value)}</td>
                    <td className="text-right">{r.history_years}</td>
                    <td className="text-right">{fmt(r.median, 1)}</td>
                    <td className="text-right">{fmt(r.modified_z, 2)}</td>
                    <td>{r.status === "assessed" ? r.label : `not assessed (${r.status.replace(/_/g, " ")})`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </AsyncView>
      </section>

      <section aria-label="Sensor comparison">
        <h2 className="mb-1 text-lg font-medium">MODIS–VIIRS comparison (experimental)</h2>
        <p className="mb-3 max-w-4xl text-xs text-[var(--text-secondary)]">
          Calibration uses monthly totals over the whole period. Matching pairs a MODIS detection with a VIIRS detection
          in the same or a neighbouring 1 km cell within ±15 minutes, over the last 12 months of the period only. Few or
          no matches are expected when the satellites pass at different times of day: Terra passes in the morning,
          Suomi-NPP, NOAA-20, NOAA-21 and Aqua in the early afternoon, and a satellite whose orbit drifts moves away from
          the others. A low match count is therefore not a calibration failure.
        </p>
        <AsyncView state={comparison} what="sensor comparison">
          {(c) => (
            <table className="w-full text-sm">
              <thead className="text-left text-[var(--text-secondary)]">
                <tr>
                  <th scope="col">MODIS</th>
                  <th scope="col">VIIRS</th>
                  <th scope="col">Calibration</th>
                  <th scope="col" className="text-right">Train / validation months</th>
                  <th scope="col" className="text-right">Factor</th>
                  <th scope="col" className="text-right">Matched MODIS detections</th>
                </tr>
              </thead>
              <tbody>
                {c.calibration.map((cal, i) => {
                  const match = c.matching[i] ?? {};
                  return (
                    <tr key={i} className="border-t border-[var(--border)] tabular-nums">
                      <td>{String(cal.modis_platform)}</td>
                      <td>{String(cal.viirs_platform)}</td>
                      <td title={String(cal.reason)}>{String(cal.status)}</td>
                      <td className="text-right">
                        {String(cal.n_train)} / {String(cal.n_validation)}
                      </td>
                      <td className="text-right">{fmt(cal.scale_factor as number | null, 3)}</td>
                      <td className="text-right">
                        {String(match.modis_matched ?? "—")} of {String(match.modis_detections ?? "—")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </AsyncView>
      </section>
    </div>
  );
}
