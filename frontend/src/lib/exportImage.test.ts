// Image export tests. Every value is SYNTHETIC TEST DATA.
import { describe, expect, it } from "vitest";
import { calendarSvg, escapeXml, fileSlug, largestByArea, wrapChartSvg } from "./exportImage";

describe("calendar image", () => {
  const cells = [
    { year: 2020, month: 3, state: "value" as const, value: 18691, tag: "T+A" },
    { year: 2020, month: 4, state: "zero" as const, value: 0, tag: "T+A" },
    { year: 2021, month: 3, state: "partial" as const, value: 120, tag: "S", converted: true },
    { year: 2021, month: 4, state: "missing" as const, value: null },
    { year: 2021, month: 5, state: "value" as const, value: 900, anomaly: "unusually high" },
  ];
  const { svg, width, height } = calendarSvg({
    title: "Harmonized <test> & calendar",
    subtitle: "Area 1,2,3,4 · 2020-01-01 → 2021-12-31",
    cells,
    edges: [100, 1000, 20000],
    footer: "Units: MODIS (Terra+Aqua)-equivalent detections",
  });

  it("is a standalone SVG with title, years, values and the data credit", () => {
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true);
    expect(svg.endsWith("</svg>")).toBe(true);
    expect(svg.includes("Harmonized &lt;test&gt; &amp; calendar")).toBe(true);
    expect(svg.includes(">2020<") && svg.includes(">2021<")).toBe(true);
    expect(svg.includes(">18,691<")).toBe(true);
    expect(svg.includes("NASA FIRMS")).toBe(true);
    expect(width > 900 && height > 200).toBe(true);
  });

  it("never shows missing data as a number, and marks converted, partial and anomalies", () => {
    expect(svg.includes("url(#hatch)")).toBe(true);
    expect(svg.includes(">≈120<")).toBe(true);
    expect(svg.includes(">S · partial<")).toBe(true);
    expect(svg.includes('stroke-dasharray="4 3"')).toBe(true);
    expect(svg.includes(">900 ▲<")).toBe(true);
  });
});

describe("helpers", () => {
  it("escapes XML and makes safe file names", () => {
    expect(escapeXml(`a<b>&"c'`)).toBe("a&lt;b&gt;&amp;&quot;c&apos;");
    expect(fileSlug("India 68.1,6.7 → 2026-11-07")).toBe("india_68.1_6.7_2026-11-07");
  });
  it("wraps chart SVG with a background, title and credit", () => {
    const { svg, width, height } = wrapChartSvg('<svg width="400" height="200"></svg>', 400, 200, "Detections", "per month");
    expect(svg.includes('<svg x="24" y="72" font-family="Segoe UI, Roboto, Arial, sans-serif" width="400"')).toBe(true);
    expect(svg.includes(">Detections<") && svg.includes("NASA FIRMS")).toBe(true);
    expect([width, height]).toEqual([448, 320]);
  });
  it("draws the platform legend into the image (the on-screen legend is HTML)", () => {
    const legend = [{ label: "Aqua", color: "#d95926" }, { label: "Suomi-NPP", color: "#199e70" }];
    const { svg, height } = wrapChartSvg('<svg width="400" height="200"></svg>', 400, 200, "D", "s", legend);
    expect(svg.includes('fill="#d95926"') && svg.includes(">Suomi-NPP<")).toBe(true);
    expect(svg.includes('<svg x="24" y="96" font-family=')).toBe(true);
    expect(height).toBe(344);
  });
});

describe("chart element", () => {
  it("picks the plot, not a same-class legend icon (regression)", () => {
    const el = (name: string, width: number, height: number) => ({ name, getBoundingClientRect: () => ({ width, height }) });
    const icon = el("legend icon", 14, 14);
    const plot = el("plot", 820, 280);
    expect(largestByArea([icon, plot, el("icon2", 14, 14)])?.name).toBe("plot");
    expect(largestByArea([])).toBe(null);
  });
});
