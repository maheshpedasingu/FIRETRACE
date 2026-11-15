import { useState } from "react";
import { downloadPng, downloadSvg } from "../lib/exportImage";

/** "PNG" / "SVG" download buttons for an image built on demand. */
export function DownloadImage({
  label,
  filename,
  build,
}: {
  label: string;
  filename: string;
  build: () => { svg: string; width: number; height: number } | null;
}) {
  const [error, setError] = useState<string | null>(null);
  async function save(kind: "png" | "svg") {
    setError(null);
    try {
      const image = build();
      if (!image) return setError("Nothing to download yet");
      if (kind === "svg") downloadSvg(image.svg, `${filename}.svg`);
      else await downloadPng(image.svg, image.width, image.height, `${filename}.png`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs">
      <span className="text-[var(--text-secondary)]">Download</span>
      <button type="button" className="btn text-xs" aria-label={`Download ${label} as PNG`} onClick={() => save("png")}>
        PNG
      </button>
      <button type="button" className="btn text-xs" aria-label={`Download ${label} as SVG`} onClick={() => save("svg")}>
        SVG
      </button>
      {error && (
        <span role="alert" className="text-red-300">
          {error}
        </span>
      )}
    </span>
  );
}
