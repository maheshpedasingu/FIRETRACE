import { SelectAreaPrompt } from "../components/Status";
import { bboxText } from "../lib/area";
import { exportCsvUrl, reportUrl } from "../services/api";
import { useArea } from "../state/AreaContext";

function Download({ href, label, hint }: { href: string; label: string; hint: string }) {
  return (
    <li className="rounded-lg border border-[var(--border)] p-3">
      <a className="font-medium underline" href={href} download>
        {label}
      </a>
      <p className="mt-1 text-xs text-[var(--text-secondary)]">{hint}</p>
    </li>
  );
}

export function ExportPage() {
  const { query } = useArea();
  if (!query) return <SelectAreaPrompt />;
  return (
    <div>
      <h2 className="mb-1 text-lg font-medium">Export centre</h2>
      <p className="mb-4 text-sm text-[var(--text-secondary)]">
        Area <span className="font-mono">{bboxText(query.area.bbox)}</span>, {query.start} → {query.end}
        {query.platforms.length ? `, platforms ${query.platforms.join(", ")}` : ", all platforms"}.
      </p>
      <ul className="grid gap-3 md:grid-cols-2">
        <Download href={exportCsvUrl(query, "hotspots")} label="Filtered detections (CSV)" hint="One row per satellite detection; NRT replaced by SP where available." />
        <Download href={exportCsvUrl(query, "hotspots", { bundle: true })} label="Detections + provenance (ZIP)" hint="CSV plus a provenance JSON: sources with SHA-256, filters, caveats." />
        <Download href={exportCsvUrl(query, "calendar")} label="Activity calendar (CSV)" hint="Years × months per platform with state (value / zero / partial / uncovered / missing)." />
        <Download href={exportCsvUrl(query, "calendar", { bundle: true })} label="Calendar + provenance (ZIP)" hint="Calendar CSV plus its provenance JSON." />
        <Download href={exportCsvUrl(query, "harmonized_calendar", { bundle: true })} label="Harmonized calendar + provenance (ZIP, experimental)" hint="One MODIS-equivalent calendar: value, source sensor, conversion factor and uncertainty per month; the provenance JSON holds every conversion fit." />
        <Download href={reportUrl(query, "json")} label="Analytics report (JSON)" hint="Monthly series, anomalies, cross-sensor diagnostics — experimental." />
        <Download href={reportUrl(query, "md")} label="Analytics report (Markdown)" hint="Readable version of the report, with limitations." />
      </ul>
    </div>
  );
}
