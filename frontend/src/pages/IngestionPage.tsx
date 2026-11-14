import { useState, type FormEvent } from "react";
import { ErrorBox, Loading, fmt } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import { daysBefore, isoDay, parseBBox, validateDates } from "../lib/area";
import { formatUtc } from "../lib/time";
import { fetchAvailability, fetchFirms, fetchHistory, uploadFile } from "../services/api";

const SOURCES = [
  "MODIS_NRT", "MODIS_SP", "VIIRS_SNPP_NRT", "VIIRS_SNPP_SP",
  "VIIRS_NOAA20_NRT", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_NRT", "VIIRS_NOAA21_SP",
];

function Result({ value }: { value: unknown }) {
  return <pre className="mt-2 max-h-64 overflow-auto rounded bg-black/30 p-2 text-xs">{JSON.stringify(value, null, 2)}</pre>;
}

function UploadForm({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [bbox, setBbox] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!file) return setError("Choose a FIRMS .csv or .zip file");
    const form = new FormData();
    form.append("file", file);
    if (bbox) {
      const parsed = parseBBox(bbox);
      if (!parsed.ok) return setError(parsed.error);
      if (!start || !end) return setError("Coverage needs start and end dates");
      form.append("bbox", bbox);
      form.append("start", start);
      form.append("end", end);
    }
    setBusy(true);
    try {
      setResult(await uploadFile(form));
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Upload FIRMS file" className="space-y-2 text-sm">
      <input aria-label="FIRMS file" type="file" accept=".csv,.zip" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <p className="text-xs text-[var(--text-secondary)]">
        Optional coverage — only if you know the exact area and dates the file was requested for. Without it, zero
        activity is never inferred from this file. Yearly FIRMS country archives get country/year coverage from
        their file names.
      </p>
      <div className="flex flex-wrap gap-2">
        <input aria-label="Coverage bbox" className="field w-56 font-mono" placeholder="west,south,east,north" value={bbox} onChange={(e) => setBbox(e.target.value)} />
        <input aria-label="Coverage start" type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} />
        <input aria-label="Coverage end" type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} />
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Importing…" : "Upload and import"}
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      {result !== null && <Result value={result} />}
    </form>
  );
}

function FirmsForm({ onDone }: { onDone: () => void }) {
  const today = new Date();
  const [sources, setSources] = useState<string[]>(["VIIRS_NOAA20_NRT"]);
  const [bbox, setBbox] = useState("");
  const [start, setStart] = useState(daysBefore(today, 3));
  const [end, setEnd] = useState(daysBefore(today, 1));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const parsed = parseBBox(bbox);
    if (!parsed.ok) return setError(parsed.error);
    const dates = validateDates(start, end, isoDay(today));
    if (!dates.ok) return setError(dates.error);
    if (sources.length === 0) return setError("Choose at least one source");
    setBusy(true);
    try {
      setResult(await fetchFirms({ sources, bbox, start, end }));
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-label="Fetch from FIRMS" className="space-y-2 text-sm">
      <fieldset className="flex flex-wrap gap-3">
        <legend className="mb-1 text-[var(--text-secondary)]">Sources</legend>
        {SOURCES.map((s) => (
          <label key={s} className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={sources.includes(s)}
              onChange={() => setSources(sources.includes(s) ? sources.filter((x) => x !== s) : [...sources, s])}
            />
            {s}
          </label>
        ))}
      </fieldset>
      <div className="flex flex-wrap gap-2">
        <input aria-label="FIRMS bbox" className="field w-56 font-mono" placeholder="west,south,east,north" value={bbox} onChange={(e) => setBbox(e.target.value)} />
        <input aria-label="FIRMS start" type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} />
        <input aria-label="FIRMS end" type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} />
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? "Fetching…" : "Fetch and import"}
        </button>
      </div>
      <p className="text-xs text-[var(--text-secondary)]">
        Up to 31 days per request, split into 5-day windows. Uses the server's MAP_KEY; the key never reaches the
        browser. For long histories use the FIRMS archive and the import command.
      </p>
      {error && <ErrorBox message={error} />}
      {result !== null && <Result value={result} />}
    </form>
  );
}

export function IngestionPage() {
  const [refresh, setRefresh] = useState(0);
  const availability = useAsync(`availability-${refresh}`, (s) => fetchAvailability(s));
  const history = useAsync(`history-${refresh}`, (s) => fetchHistory(1, s));
  const done = () => setRefresh((n) => n + 1);

  return (
    <div className="space-y-8">
      <section aria-label="FIRMS availability">
        <h2 className="mb-2 text-lg font-medium">FIRMS data availability</h2>
        {availability.kind === "loading" && <Loading what="availability" />}
        {availability.kind === "error" && <ErrorBox message={availability.message} />}
        {availability.kind === "ok" &&
          (availability.data.firms.available ? (
            <table className="text-sm">
              <thead className="text-left text-[var(--text-secondary)]">
                <tr>
                  <th scope="col" className="pr-6">Source</th>
                  <th scope="col" className="pr-6">From</th>
                  <th scope="col">To</th>
                </tr>
              </thead>
              <tbody>
                {(availability.data.firms.products ?? []).map((p) => (
                  <tr key={p.data_id} className="border-t border-[var(--border)]">
                    <td className="pr-6">{p.data_id}</td>
                    <td className="pr-6">{p.min_date}</td>
                    <td>{p.max_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-[var(--text-secondary)]">
              Live availability unavailable: {availability.data.firms.error ?? "unknown reason"}
            </p>
          ))}
      </section>

      <section aria-label="Upload">
        <h2 className="mb-2 text-lg font-medium">Upload FIRMS archive / CSV</h2>
        <UploadForm onDone={done} />
      </section>

      <section aria-label="Fetch">
        <h2 className="mb-2 text-lg font-medium">Fetch recent data from the FIRMS API</h2>
        <FirmsForm onDone={done} />
      </section>

      <section aria-label="Import history">
        <h2 className="mb-2 text-lg font-medium">Import history</h2>
        {history.kind === "loading" && <Loading what="history" />}
        {history.kind === "error" && <ErrorBox message={history.message} />}
        {history.kind === "ok" && (
          <table className="w-full text-xs">
            <thead className="text-left text-[var(--text-secondary)]">
              <tr>
                {["Started", "Status", "File", "Read", "Valid", "Invalid", "Dup. in file", "Already stored", "Written", "Message"].map((h) => (
                  <th key={h} scope="col" className="px-1">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.data.items.map((r) => (
                <tr key={r.run_id} className="border-t border-[var(--border)] tabular-nums">
                  <td className="px-1">{formatUtc(r.started_utc)}</td>
                  <td className="px-1">{r.status}</td>
                  <td className="px-1" title={`SHA-256 ${r.sha256}`}>{r.file}</td>
                  <td className="px-1">{fmt(r.rows_read)}</td>
                  <td className="px-1">{fmt(r.rows_valid)}</td>
                  <td className="px-1">{fmt(r.rows_invalid)}</td>
                  <td className="px-1">{fmt(r.rows_duplicate_in_file)}</td>
                  <td className="px-1">{fmt(r.rows_already_stored)}</td>
                  <td className="px-1">{fmt(r.rows_written)}</td>
                  <td className="px-1 text-[var(--text-secondary)]">{r.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
