# Dashboard (frontend)

React 19 + TypeScript + Vite + Tailwind 4, React-Leaflet (map), Recharts (charts).
Run: `npm run dev` in `frontend/` with the backend on port 8000 (Vite proxies `/api`).
The browser never sees the FIRMS MAP_KEY.

## Pages

| Page | Contents |
|---|---|
| Overview | backend status, selected area and period, detections and unique cells per platform, coverage months, latest import, imported coverage |
| Map | detections as points (MODIS = orange ring, VIIRS = blue dot; size = FRP), per-platform toggles, area outline (two rectangles across 180°), tools: draw box (two clicks) or polygon (clicks, then save as AOI) |
| Calendar | years × months heatmap per platform, measure selectable, anomaly marks |
| Analytics | monthly line charts per platform (detections, unique cells, FRP), yearly totals and YoY, FRP / confidence / day-night table, anomalies, sensor comparison |
| Data explorer | paginated detections with confidence / day-night filters and the original source row |
| Ingestion | FIRMS availability, upload (with optional declared coverage), FIRMS API fetch, import history |
| Export | CSV / ZIP-with-provenance / report downloads for the current selection |

There is **no default region**: until an area is chosen (bbox, saved AOI, example preset or
map drawing) pages ask for one. Examples (Andhra Pradesh, Amazon, northern Australia,
Fiji across 180°) are optional presets.

## Visual encoding (validated)

Colours are the dark-mode steps of a validated reference palette, checked with the
dataviz palette validator on 2026-11-14 against the dark surface `#1a1a19`:

- **Platforms (charts):** Terra `#3987e5`, Aqua `#d95926`, Suomi-NPP `#199e70`, NOAA-20
  `#c98500`, NOAA-21 `#d55181` — passes all adjacent-pair checks (worst CVD ΔE 8.4,
  normal ΔE 19.3). Always with a legend; colour follows the platform under any filter.
  A warm-MODIS/cool-VIIRS reordering was tested and rejected (CVD ΔE 1.6).
- **Map:** the five platform colours fail the all-pairs check needed for a scatter map
  (worst CVD ΔE 1.6), so the map encodes the sensor instead: MODIS `#d95926` ring, VIIRS
  `#3987e5` dot (all-pairs ΔE 26.8 CVD / 31.8 normal), plus per-platform toggles and
  tooltips. Shape carries identity as well as colour.
- **Calendar:** one-hue blue ramp (ordinal check passes), quantile bins of positive
  values. States are never colour-only: zero = grey with "0", partial = dashed border and
  "partial", uncovered = dotted border and "≥", missing = hatching and "—", anomalies ▲/▼.
  Cell text is chosen by computed WCAG contrast (minimum 4.69:1). Each cell has a full
  text description (tooltip and screen-reader label); the heatmap is an HTML table, which
  also serves as the table view.
- Charts use one y-axis per chart (no dual axes) and leave gaps where coverage is missing.

## Tests

Vitest + Testing Library (jsdom): pure helpers (`lib/*.test.ts`), the area bar, the
calendar heatmap, and the app shell (backend status, no default region, calendar states).
The map is lazy-loaded and not rendered in jsdom.
