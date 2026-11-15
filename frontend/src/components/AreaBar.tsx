import { useEffect, useState, type FormEvent } from "react";
import {
  EXAMPLE_AREAS,
  bboxText,
  circleName,
  circlePolygon,
  crossesAntimeridian,
  daysBefore,
  isoDay,
  parseBBox,
  validateDates,
  type AreaQuery,
} from "../lib/area";
import { PLATFORM_COLORS, PLATFORM_ORDER } from "../lib/colors";
import { createAOI } from "../services/api";
import type { SavedAOI } from "../types/api";

interface Props {
  query: AreaQuery | null;
  onApply: (q: AreaQuery) => void;
  savedAois: SavedAOI[];
  today?: Date;
  /** Saves a polygon area (injectable for tests). */
  createArea?: (body: { name: string; geojson: unknown }) => Promise<SavedAOI>;
}

/** Area, period and platform filters, in one row above every view. */
export function AreaBar({ query, onApply, savedAois, today = new Date(), createArea = createAOI }: Props) {
  const todayIso = isoDay(today);
  const [bbox, setBbox] = useState(
    query?.area.kind === "bbox" ? bboxText(query.area.bbox) : "",
  );
  const [aoiId, setAoiId] = useState<number | null>(query?.area.kind === "aoi" ? query.area.id : null);
  const [start, setStart] = useState(query?.start ?? daysBefore(today, 30));
  const [end, setEnd] = useState(query?.end ?? todayIso);
  const [platforms, setPlatforms] = useState<string[]>(query?.platforms ?? []);
  const [country, setCountry] = useState(query?.country ?? "");
  const [circleMode, setCircleMode] = useState(false);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [radius, setRadius] = useState("50");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Follow external changes (e.g. a bbox drawn on the map).
  useEffect(() => {
    if (!query) return;
    if (query.area.kind === "bbox") {
      setBbox(bboxText(query.area.bbox));
      setAoiId(null);
    } else {
      setAoiId(query.area.id);
    }
    setStart(query.start);
    setEnd(query.end);
    setPlatforms(query.platforms);
    setCountry(query.country ?? "");
    setCircleMode(false); // an applied circle is a saved area from now on
  }, [query]);

  function choosePreset(value: string) {
    setCircleMode(value === "circle");
    if (value === "circle") {
      setAoiId(null);
      return;
    }
    if (value.startsWith("aoi:")) {
      setAoiId(Number(value.slice(4)));
      return;
    }
    const preset = EXAMPLE_AREAS[Number(value)];
    if (preset) {
      setAoiId(null);
      setBbox(bboxText(preset.bbox));
      setCountry(preset.country ?? "");
    }
  }

  async function submitCircle(extra: { country?: string }) {
    const circle = circlePolygon(Number(lat), Number(lon), Number(radius));
    if (lat.trim() === "" || lon.trim() === "" || !circle.ok) {
      return setError(circle.ok ? "Enter latitude and longitude" : circle.error);
    }
    const name = circleName(Number(lat), Number(lon), Number(radius));
    setBusy(true);
    try {
      const saved = savedAois.find((a) => a.name === name) ?? (await createArea({ name, geojson: circle.value }));
      const [west, south, east, north] = saved.bbox;
      setError(null);
      onApply({ area: { kind: "aoi", id: saved.id, name: saved.name, bbox: { west, south, east, north } }, start, end, platforms, ...extra });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const dates = validateDates(start, end, todayIso);
    if (!dates.ok) return setError(dates.error);
    if (circleMode) return void submitCircle(country.trim() ? { country: country.trim() } : {});
    if (aoiId !== null) {
      const saved = savedAois.find((a) => a.id === aoiId);
      if (!saved) return setError("Saved area not found");
      const [west, south, east, north] = saved.bbox;
      setError(null);
      return onApply({ area: { kind: "aoi", id: saved.id, name: saved.name, bbox: { west, south, east, north } }, start, end, platforms, ...(country.trim() ? { country: country.trim() } : {}) });
    }
    const parsed = parseBBox(bbox);
    if (!parsed.ok) return setError(parsed.error);
    setError(null);
    onApply({ area: { kind: "bbox", bbox: parsed.value }, start, end, platforms, ...(country.trim() ? { country: country.trim() } : {}) });
  }

  const togglePlatform = (p: string) =>
    setPlatforms((current) => (current.includes(p) ? current.filter((x) => x !== p) : [...current, p]));

  const parsed = parseBBox(bbox);
  // noValidate: the browser's built-in checks (e.g. date max) would block submit before
  // FIRETRACE's own validation, hiding its specific, accessible messages.
  return (
    <form
      onSubmit={submit}
      noValidate
      aria-label="Area and period"
      className="flex flex-wrap items-end gap-3 border-b border-[var(--border)] px-6 py-3 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-[var(--text-secondary)]">Area</span>
        <select
          aria-label="Saved or example area"
          className="field"
          value={aoiId !== null ? `aoi:${aoiId}` : circleMode ? "circle" : ""}
          onChange={(e) => choosePreset(e.target.value)}
        >
          <option value="">Custom bbox…</option>
          <option value="circle">Point + radius (km)…</option>
          {savedAois.length > 0 && (
            <optgroup label="Saved areas">
              {savedAois.map((a) => (
                <option key={a.id} value={`aoi:${a.id}`}>
                  {a.name} ({a.kind})
                </option>
              ))}
            </optgroup>
          )}
          <optgroup label="Examples (optional)">
            {EXAMPLE_AREAS.map((a, i) => (
              <option key={a.label} value={String(i)}>
                {a.label}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      {circleMode ? (
        <>
          <label className="flex flex-col gap-1">
            <span className="text-[var(--text-secondary)]">Latitude</span>
            <input aria-label="Latitude" className="field w-24 font-mono" placeholder="e.g. 15.9" value={lat} onChange={(e) => setLat(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[var(--text-secondary)]">Longitude</span>
            <input aria-label="Longitude" className="field w-24 font-mono" placeholder="e.g. 79.7" value={lon} onChange={(e) => setLon(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[var(--text-secondary)]">Radius (km)</span>
            <input aria-label="Radius in km" className="field w-20 font-mono" value={radius} onChange={(e) => setRadius(e.target.value)} />
          </label>
        </>
      ) : (
      <label className="flex flex-col gap-1">
        <span className="text-[var(--text-secondary)]">Bounding box (west,south,east,north)</span>
        <input
          aria-label="Bounding box"
          className="field w-64 font-mono"
          placeholder="e.g. -65,-15,-45,-3"
          value={bbox}
          disabled={aoiId !== null}
          onChange={(e) => setBbox(e.target.value)}
        />
      </label>
      )}
      <label className="flex flex-col gap-1" title="Only for country downloads: enter the country the WHOLE area lies inside (e.g. India). Its imported coverage then counts for this area. Leave empty otherwise.">
        <span className="text-[var(--text-secondary)]">Inside country (optional)</span>
        <input
          aria-label="Inside country"
          className="field w-32"
          placeholder="e.g. India"
          value={country}
          onChange={(e) => setCountry(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[var(--text-secondary)]">From (UTC)</span>
        <input aria-label="Start date" type="date" className="field" value={start} max={todayIso} onChange={(e) => setStart(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[var(--text-secondary)]">To (UTC)</span>
        <input aria-label="End date" type="date" className="field" value={end} max={todayIso} onChange={(e) => setEnd(e.target.value)} />
      </label>
      <fieldset className="flex flex-wrap items-center gap-2">
        <legend className="sr-only">Platforms (none selected = all)</legend>
        {PLATFORM_ORDER.map((p) => (
          <label key={p} className="flex items-center gap-1">
            <input type="checkbox" checked={platforms.includes(p)} onChange={() => togglePlatform(p)} />
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: PLATFORM_COLORS[p] }} aria-hidden />
            {p}
          </label>
        ))}
        <span className="text-xs text-[var(--text-secondary)]">(none = all)</span>
      </fieldset>
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? "Saving area…" : "Apply"}
      </button>
      {!circleMode && aoiId === null && parsed.ok && crossesAntimeridian(parsed.value) && (
        <span className="text-xs text-[var(--text-secondary)]">Crosses the 180° meridian.</span>
      )}
      {error && (
        <p role="alert" className="w-full text-red-300">
          {error}
        </p>
      )}
    </form>
  );
}
