import { useEffect, useState, type FormEvent } from "react";
import {
  EXAMPLE_AREAS,
  bboxText,
  crossesAntimeridian,
  daysBefore,
  isoDay,
  parseBBox,
  validateDates,
  type AreaQuery,
} from "../lib/area";
import { PLATFORM_COLORS, PLATFORM_ORDER } from "../lib/colors";
import type { SavedAOI } from "../types/api";

interface Props {
  query: AreaQuery | null;
  onApply: (q: AreaQuery) => void;
  savedAois: SavedAOI[];
  today?: Date;
}

/** Area, period and platform filters, in one row above every view. */
export function AreaBar({ query, onApply, savedAois, today = new Date() }: Props) {
  const todayIso = isoDay(today);
  const [bbox, setBbox] = useState(
    query?.area.kind === "bbox" ? bboxText(query.area.bbox) : "",
  );
  const [aoiId, setAoiId] = useState<number | null>(query?.area.kind === "aoi" ? query.area.id : null);
  const [start, setStart] = useState(query?.start ?? daysBefore(today, 30));
  const [end, setEnd] = useState(query?.end ?? todayIso);
  const [platforms, setPlatforms] = useState<string[]>(query?.platforms ?? []);
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
  }, [query]);

  function choosePreset(value: string) {
    if (value.startsWith("aoi:")) {
      setAoiId(Number(value.slice(4)));
      return;
    }
    const preset = EXAMPLE_AREAS[Number(value)];
    if (preset) {
      setAoiId(null);
      setBbox(bboxText(preset.bbox));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    const dates = validateDates(start, end, todayIso);
    if (!dates.ok) return setError(dates.error);
    if (aoiId !== null) {
      const saved = savedAois.find((a) => a.id === aoiId);
      if (!saved) return setError("Saved area not found");
      const [west, south, east, north] = saved.bbox;
      setError(null);
      return onApply({ area: { kind: "aoi", id: saved.id, name: saved.name, bbox: { west, south, east, north } }, start, end, platforms });
    }
    const parsed = parseBBox(bbox);
    if (!parsed.ok) return setError(parsed.error);
    setError(null);
    onApply({ area: { kind: "bbox", bbox: parsed.value }, start, end, platforms });
  }

  const togglePlatform = (p: string) =>
    setPlatforms((current) => (current.includes(p) ? current.filter((x) => x !== p) : [...current, p]));

  const parsed = parseBBox(bbox);
  return (
    <form onSubmit={submit} aria-label="Area and period" className="flex flex-wrap items-end gap-3 border-b border-[var(--border)] px-6 py-3 text-sm">
      <label className="flex flex-col gap-1">
        <span className="text-[var(--text-secondary)]">Area</span>
        <select
          aria-label="Saved or example area"
          className="field"
          value={aoiId !== null ? `aoi:${aoiId}` : ""}
          onChange={(e) => choosePreset(e.target.value)}
        >
          <option value="">Custom bbox…</option>
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
      <button type="submit" className="btn-primary">
        Apply
      </button>
      {aoiId === null && parsed.ok && crossesAntimeridian(parsed.value) && (
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
