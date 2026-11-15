// Download the calendar and charts as images (SVG or PNG), built from the data so the
// file carries its own title, area, period, units and data credit. Pure SVG builders
// are unit-tested; the PNG/download helpers use browser APIs only.
import { CALENDAR_RAMP, NEUTRAL, STATE_LABELS, SURFACE, TEXT_PRIMARY, TEXT_SECONDARY, cellStyle } from "./colors";
import type { CellState } from "../types/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const FONT = "font-family: 'Segoe UI', Roboto, system-ui, sans-serif";
export const DATA_CREDIT = "Data: NASA FIRMS (LANCE / MODAPS). Detections are not fire incidents; missing data is not zero.";

export function escapeXml(text: string): string {
  return text.replace(/[<>&"']/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" })[c]!);
}

export interface ImageCell {
  year: number;
  month: number;
  state: CellState;
  value: number | null;
  /** short source tag, e.g. "T+A" (harmonized) or "" */
  tag?: string;
  converted?: boolean;
  anomaly?: string | null;
}

const fmtInt = (v: number) => Math.round(v).toLocaleString("en-US");

/** A years × months calendar as a standalone SVG document. */
export function calendarSvg(opts: {
  title: string;
  subtitle: string;
  cells: ImageCell[];
  edges: number[];
  footer?: string;
}): { svg: string; width: number; height: number } {
  const cellW = 74, cellH = 40, gap = 3, left = 64, top = 96;
  const years = [...new Set(opts.cells.map((c) => c.year))].sort((a, b) => a - b);
  const byKey = new Map(opts.cells.map((c) => [`${c.year}-${c.month}`, c]));
  const width = left + 12 * (cellW + gap) + 24;
  const legendTop = top + 22 + years.length * (cellH + gap) + 16;
  const height = legendTop + 96;
  const out: string[] = [];
  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`,
    `<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">` +
      `<rect width="6" height="6" fill="${SURFACE}"/><line x1="0" y1="0" x2="0" y2="6" stroke="${NEUTRAL}" stroke-width="2"/></pattern></defs>`,
    `<rect width="${width}" height="${height}" fill="${SURFACE}"/>`,
    `<text x="24" y="34" fill="${TEXT_PRIMARY}" font-size="20" font-weight="600" style="${FONT}">${escapeXml(opts.title)}</text>`,
    `<text x="24" y="58" fill="${TEXT_SECONDARY}" font-size="13" style="${FONT}">${escapeXml(opts.subtitle)}</text>`,
  );
  MONTHS.forEach((m, i) => {
    out.push(
      `<text x="${left + i * (cellW + gap) + cellW / 2}" y="${top + 8}" text-anchor="middle" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">${m}</text>`,
    );
  });
  years.forEach((year, row) => {
    const y = top + 22 + row * (cellH + gap);
    out.push(`<text x="24" y="${y + cellH / 2 + 4}" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">${year}</text>`);
    for (let m = 1; m <= 12; m++) {
      const c = byKey.get(`${year}-${m}`);
      const x = left + (m - 1) * (cellW + gap);
      if (!c) {
        out.push(`<text x="${x + cellW / 2}" y="${y + cellH / 2 + 4}" text-anchor="middle" fill="${NEUTRAL}" font-size="12">·</text>`);
        continue;
      }
      const s = cellStyle(c.state, c.value, opts.edges);
      const fill = s.pattern === "hatch" ? "url(#hatch)" : s.background;
      const dash = c.state === "partial" ? ' stroke-dasharray="4 3"' : c.state === "uncovered" ? ' stroke-dasharray="1 3"' : "";
      const stroke = c.state === "partial" || c.state === "uncovered" ? TEXT_SECONDARY : c.state === "missing" ? NEUTRAL : "none";
      out.push(`<rect x="${x}" y="${y}" width="${cellW}" height="${cellH}" rx="4" fill="${fill}" stroke="${stroke}" stroke-width="2"${dash}/>`);
      const mark = c.anomaly === "unusually high" ? " ▲" : c.anomaly === "unusually low" ? " ▼" : "";
      const label =
        c.state === "missing" || c.value === null
          ? "—"
          : `${c.converted ? "≈" : ""}${c.state === "uncovered" ? "≥" : ""}${fmtInt(c.value)}${mark}`;
      out.push(
        `<text x="${x + cellW / 2}" y="${y + (c.tag ? 17 : 24)}" text-anchor="middle" fill="${s.text}" font-size="12" style="${FONT}">${escapeXml(label)}</text>`,
      );
      const small = [c.tag ?? "", c.state === "partial" ? "partial" : ""].filter(Boolean).join(" · ");
      if (small) {
        out.push(
          `<text x="${x + cellW / 2}" y="${y + 32}" text-anchor="middle" fill="${s.text}" font-size="9" style="${FONT}">${escapeXml(small)}</text>`,
        );
      }
    }
  });
  // Legend: value bins, then states (never colour alone: hatch / dashes / text).
  let lx = 24;
  out.push(`<text x="${lx}" y="${legendTop + 12}" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">Value bins:</text>`);
  lx += 76;
  opts.edges.forEach((edge, i) => {
    const label = i === 0 ? `1–${fmtInt(edge)}` : `${fmtInt(opts.edges[i - 1] + 1)}–${fmtInt(edge)}`;
    out.push(`<rect x="${lx}" y="${legendTop + 2}" width="22" height="12" rx="2" fill="${CALENDAR_RAMP[i]}"/>`);
    out.push(`<text x="${lx + 28}" y="${legendTop + 12}" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">${escapeXml(label)}</text>`);
    lx += 34 + label.length * 7;
  });
  const states: CellState[] = ["zero", "partial", "uncovered", "missing"];
  let sx = 24;
  states.forEach((st) => {
    const s = cellStyle(st, opts.edges[0] ?? 1, opts.edges.length ? opts.edges : [1]);
    const fill = s.pattern === "hatch" ? "url(#hatch)" : s.background;
    const dash = st === "partial" ? ' stroke-dasharray="4 3"' : st === "uncovered" ? ' stroke-dasharray="1 3"' : "";
    out.push(`<rect x="${sx}" y="${legendTop + 26}" width="22" height="12" rx="2" fill="${fill}" stroke="${TEXT_SECONDARY}" stroke-width="1"${dash}/>`);
    out.push(`<text x="${sx + 28}" y="${legendTop + 36}" fill="${TEXT_SECONDARY}" font-size="11" style="${FONT}">${escapeXml(STATE_LABELS[st])}</text>`);
    sx += 40 + STATE_LABELS[st].length * 6;
  });
  out.push(
    `<text x="24" y="${legendTop + 62}" fill="${TEXT_SECONDARY}" font-size="11" style="${FONT}">${escapeXml(opts.footer ?? "")}</text>`,
    `<text x="24" y="${legendTop + 80}" fill="${TEXT_SECONDARY}" font-size="11" style="${FONT}">${escapeXml(DATA_CREDIT)}</text>`,
    "</svg>",
  );
  return { svg: out.join(""), width, height };
}

/** Put a chart's SVG markup on a solid background with a title and the data credit. */
export function wrapChartSvg(
  inner: string,
  innerWidth: number,
  innerHeight: number,
  title: string,
  subtitle: string,
  legend: { label: string; color: string }[] = [],
) {
  const width = Math.round(innerWidth) + 48;
  const height = Math.round(innerHeight) + 120 + (legend.length ? 24 : 0);
  const chartTop = legend.length ? 96 : 72;
  const body = inner.replace(/^<svg/, `<svg x="24" y="${chartTop}"`);
  let x = 24;
  const legendSvg = legend
    .map(({ label, color }) => {
      const item =
        `<rect x="${x}" y="68" width="14" height="4" fill="${color}"/>` +
        `<text x="${x + 20}" y="74" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">${escapeXml(label)}</text>`;
      x += 34 + label.length * 7;
      return item;
    })
    .join("");
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">` +
    `<rect width="${width}" height="${height}" fill="${SURFACE}"/>` +
    `<text x="24" y="32" fill="${TEXT_PRIMARY}" font-size="18" font-weight="600" style="${FONT}">${escapeXml(title)}</text>` +
    `<text x="24" y="54" fill="${TEXT_SECONDARY}" font-size="12" style="${FONT}">${escapeXml(subtitle)}</text>` +
    legendSvg +
    body +
    `<text x="24" y="${height - 16}" fill="${TEXT_SECONDARY}" font-size="11" style="${FONT}">${escapeXml(DATA_CREDIT)}</text>` +
    `</svg>`;
  return { svg, width, height };
}

/** Safe file name part from free text. */
export function fileSlug(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9.-]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 80);
}

// ---- browser-only helpers ---------------------------------------------------------

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadSvg(svg: string, filename: string): void {
  downloadBlob(new Blob([svg], { type: "image/svg+xml" }), filename);
}

/** Render an SVG document to a PNG (2× for sharp text) and download it. */
export async function downloadPng(svg: string, width: number, height: number, filename: string): Promise<void> {
  const scale = 2;
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  try {
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Could not render the image"));
      img.src = url;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width * scale;
    canvas.height = height * scale;
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is not available in this browser");
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
    if (!blob) throw new Error("Could not create the PNG");
    downloadBlob(blob, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}
