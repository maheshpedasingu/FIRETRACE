import "leaflet/dist/leaflet.css";
import { useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Polygon,
  Polyline,
  Rectangle,
  TileLayer,
  Tooltip,
  useMapEvents,
} from "react-leaflet";
import { AsyncView, fmt } from "../components/Status";
import { useAsync } from "../hooks/useAsync";
import {
  bboxFromCorners,
  bboxText,
  crossesAntimeridian,
  daysBefore,
  isoDay,
  polygonFromVertices,
  type BBox,
} from "../lib/area";
import { PLATFORM_ORDER, PLATFORM_SENSOR, SENSOR_COLORS, frpRadius } from "../lib/colors";
import { createAOI, fetchHotspots } from "../services/api";
import { useArea } from "../state/AreaContext";
import type { Platform } from "../types/api";

const MAX_POINTS = 5000;
type Mode = "pan" | "bbox" | "polygon";

/** Rectangles for a bbox; two when it crosses the antimeridian. */
function bboxRects(b: BBox): [[number, number], [number, number]][] {
  if (!crossesAntimeridian(b)) return [[[b.south, b.west], [b.north, b.east]]];
  return [
    [[b.south, b.west], [b.north, 180]],
    [[b.south, -180], [b.north, b.east]],
  ];
}

function ClickCapture({ onClick }: { onClick: (latlng: [number, number]) => void }) {
  useMapEvents({
    click(event) {
      onClick([event.latlng.lat, event.latlng.lng]);
    },
  });
  return null;
}

export default function MapPage() {
  const { query, key, setQuery } = useArea();
  const [mode, setMode] = useState<Mode>("pan");
  const [corner, setCorner] = useState<[number, number] | null>(null);
  const [vertices, setVertices] = useState<[number, number][]>([]);
  const [hidden, setHidden] = useState<Platform[]>([]);
  const [polygonName, setPolygonName] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const hotspots = useAsync(key, (signal) => fetchHotspots(query!, { page: 1, pageSize: MAX_POINTS }, signal));

  function applyBBox(bbox: BBox) {
    const today = new Date();
    setQuery({
      area: { kind: "bbox", bbox },
      start: query?.start ?? daysBefore(today, 30),
      end: query?.end ?? isoDay(today),
      platforms: query?.platforms ?? [],
    });
  }

  function onMapClick(latlng: [number, number]) {
    if (mode === "bbox") {
      if (!corner) setCorner(latlng);
      else {
        applyBBox(bboxFromCorners(corner, latlng));
        setCorner(null);
        setMode("pan");
      }
    } else if (mode === "polygon") {
      setVertices((v) => [...v, latlng]);
    }
  }

  async function savePolygon() {
    const polygon = polygonFromVertices(vertices);
    if (!polygon.ok) return setMessage(polygon.error);
    if (!polygonName.trim()) return setMessage("Name the polygon to save it");
    try {
      const saved = await createAOI({ name: polygonName.trim(), geojson: polygon.value });
      const [west, south, east, north] = saved.bbox;
      const today = new Date();
      setQuery({
        area: { kind: "aoi", id: saved.id, name: saved.name, bbox: { west, south, east, north } },
        start: query?.start ?? daysBefore(today, 30),
        end: query?.end ?? isoDay(today),
        platforms: query?.platforms ?? [],
      });
      setVertices([]);
      setPolygonName("");
      setMode("pan");
      setMessage(`Saved area "${saved.name}" and selected it.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <h2 className="text-lg font-medium">Map</h2>
        <div role="radiogroup" aria-label="Map tool" className="flex gap-1">
          {(["pan", "bbox", "polygon"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={mode === m}
              className={mode === m ? "btn-primary" : "btn"}
              onClick={() => {
                setMode(m);
                setCorner(null);
                if (m !== "polygon") setVertices([]);
              }}
            >
              {m === "pan" ? "Pan" : m === "bbox" ? "Draw box" : "Draw polygon"}
            </button>
          ))}
        </div>
        {mode === "bbox" && <span>{corner ? "Click the opposite corner." : "Click the first corner."}</span>}
        {mode === "polygon" && (
          <span className="flex items-center gap-2">
            {vertices.length} points
            <input aria-label="Polygon name" className="field" placeholder="Name" value={polygonName} onChange={(e) => setPolygonName(e.target.value)} />
            <button type="button" className="btn-primary" onClick={savePolygon}>
              Save area
            </button>
          </span>
        )}
        <fieldset className="flex flex-wrap items-center gap-2">
          <legend className="sr-only">Show platforms</legend>
          {PLATFORM_ORDER.map((p) => (
            <label key={p} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={!hidden.includes(p)}
                onChange={() => setHidden(hidden.includes(p) ? hidden.filter((x) => x !== p) : [...hidden, p])}
              />
              {p}
            </label>
          ))}
        </fieldset>
      </div>
      {message && <p className="text-sm text-[var(--text-secondary)]">{message}</p>}

      <div className="flex flex-wrap gap-4 text-xs text-[var(--text-secondary)]" aria-label="Map legend">
        <span className="flex items-center gap-1">
          <svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="5" fill="none" stroke={SENSOR_COLORS.MODIS} strokeWidth="2" /></svg>
          MODIS (Terra, Aqua) — ring
        </span>
        <span className="flex items-center gap-1">
          <svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="5" fill={SENSOR_COLORS.VIIRS} /></svg>
          VIIRS (Suomi-NPP, NOAA-20, NOAA-21) — dot
        </span>
        <span>Marker size: FRP (MW). Points are detection pixel centres, not fire perimeters.</span>
      </div>

      <div className="h-[560px] overflow-hidden rounded-lg border border-[var(--border)]">
        <MapContainer center={[15, 0]} zoom={2} minZoom={1} worldCopyJump className="h-full w-full" style={{ background: "#1a1a19" }}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickCapture onClick={onMapClick} />
          {query &&
            (query.area.kind === "bbox" || query.area.kind === "aoi") &&
            bboxRects(query.area.bbox).map((bounds, i) => (
              <Rectangle key={i} bounds={bounds} pathOptions={{ color: "#f0efec", weight: 2, fill: false, dashArray: "6 4" }} />
            ))}
          {vertices.length >= 2 && <Polyline positions={vertices} pathOptions={{ color: "#f0efec", weight: 2 }} />}
          {vertices.length >= 3 && <Polygon positions={vertices} pathOptions={{ color: "#f0efec", weight: 1, fillOpacity: 0.1 }} />}
          {hotspots.kind === "ok" &&
            hotspots.data.items
              .filter((h) => !hidden.includes(h.platform))
              .map((h) => {
                const sensor = PLATFORM_SENSOR[h.platform];
                const color = SENSOR_COLORS[sensor];
                return (
                  <CircleMarker
                    key={h.observation_id}
                    center={[h.latitude, h.longitude]}
                    radius={frpRadius(h.frp_mw)}
                    pathOptions={
                      sensor === "MODIS"
                        ? { color, weight: 2, fill: false }
                        : { color: "#1a1a19", weight: 1, fillColor: color, fillOpacity: 0.85 }
                    }
                  >
                    <Tooltip>
                      {h.platform} ({sensor}) · {h.acquisition_date} {h.acquisition_time_utc} UTC
                      <br />
                      FRP {fmt(h.frp_mw, 2)} MW · confidence {h.confidence_class ?? "—"} · {h.processing_status}
                    </Tooltip>
                  </CircleMarker>
                );
              })}
        </MapContainer>
      </div>

      <AsyncView state={hotspots} what="map detections">
        {(data) => (
          <p className="text-sm text-[var(--text-secondary)]">
            Showing {fmt(Math.min(data.items.length, MAX_POINTS))} of {fmt(data.total)} detections in{" "}
            <span className="font-mono">{query ? bboxText(query.area.bbox) : ""}</span>
            {data.total > MAX_POINTS && " — narrow the area or period to see all; exports always include every row."}
          </p>
        )}
      </AsyncView>
    </div>
  );
}
