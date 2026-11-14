import type { ReactNode } from "react";
import type { AsyncState } from "../hooks/useAsync";

export function Loading({ what }: { what: string }) {
  return <p className="text-sm text-[var(--text-secondary)]">Loading {what}…</p>;
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded border border-red-700 bg-red-950/40 p-3 text-sm text-red-200">
      {message}
    </p>
  );
}

export function SelectAreaPrompt() {
  return (
    <p className="rounded border border-[var(--border)] p-4 text-sm text-[var(--text-secondary)]">
      Select an area and period above (or draw one on the Map) to see results. FIRETRACE has no
      default region.
    </p>
  );
}

/** Render loading / error / idle states uniformly; children render the data. */
export function AsyncView<T>({
  state,
  what,
  children,
}: {
  state: AsyncState<T>;
  what: string;
  children: (data: T) => ReactNode;
}) {
  if (state.kind === "idle") return <SelectAreaPrompt />;
  if (state.kind === "loading") return <Loading what={what} />;
  if (state.kind === "error") return <ErrorBox message={`Could not load ${what}: ${state.message}`} />;
  return <>{children(state.data)}</>;
}

export function fmt(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}
